"""
scripts/preflight_check.py — Phase 5.3(c): pre-demo readiness gate.

Run this ~30s before a judged demo starts. Verifies devices are present,
the model loads, and the self-test suite is green -- red/green terminal
output, single command, non-zero exit on any CRITICAL failure so it
composes cleanly into demo/run_judged_demo.sh (`preflight_check.py || exit 1`).

Checks are split CRITICAL (block the demo, exit non-zero) vs ADVISORY (print
a warning, do not block -- e.g. an optional dependency for a WOW feature
that isn't required for the core enhance/bypass demo path). This mirrors
scripts/run_all_selftests.py's PASS/SKIP distinction: an absent optional
dependency is a known, documented condition, not a broken build.

This is genuinely runnable on the dev machine (Mode A) -- device/hardware
checks will honestly report what's actually attached to THIS machine
(no dual-mic on a dev laptop, for instance), which is the correct behaviour:
a preflight check that fabricates PASS for absent hardware is worse than
useless. Full hardware coverage is Mode B, on the Pi with real demo gear.

Usage:
    python scripts/preflight_check.py
    python scripts/preflight_check.py --skip-selftests   # faster, less coverage
    python scripts/preflight_check.py --self-test         # test the check logic itself
"""

import os
import sys
import time
import argparse
import subprocess

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


class CheckResult:
    def __init__(self, name: str, status: str, message: str, critical: bool):
        self.name = name
        self.status = status      # "PASS" / "FAIL" / "WARN"
        self.message = message
        self.critical = critical  # if True and status=="FAIL", blocks the demo


def _mark(status: str) -> str:
    if status == "PASS":
        return f"{GREEN}[ PASS ]{RESET}"
    if status == "WARN":
        return f"{YELLOW}[ WARN ]{RESET}"
    return f"{RED}[ FAIL ]{RESET}"


# ---------------------------------------------------------------------------
# Individual checks. Each returns a CheckResult, never raises -- a check
# that can't complete is a FAIL/WARN with the real exception message
# (Rule 4: never hide a real error), not a crash of the whole script.
# ---------------------------------------------------------------------------

def check_config_loads(config_path: str) -> CheckResult:
    try:
        from live.pipeline import _load_config
        cfg = _load_config(config_path)
        assert "audio" in cfg and "pipeline" in cfg and "model" in cfg
        return CheckResult("config loads", "PASS", f"{config_path} parsed OK", critical=True)
    except Exception as exc:
        return CheckResult("config loads", "FAIL", str(exc), critical=True)


def check_devices_enumerate() -> CheckResult:
    try:
        import sounddevice as sd
        devs = sd.query_devices()
        n_in = sum(1 for d in devs if d.get("max_input_channels", 0) > 0)
        n_out = sum(1 for d in devs if d.get("max_output_channels", 0) > 0)
        if n_in == 0 or n_out == 0:
            return CheckResult(
                "audio devices enumerate", "FAIL",
                f"{n_in} input / {n_out} output device(s) found -- need at least 1 of each",
                critical=True,
            )
        return CheckResult(
            "audio devices enumerate", "PASS",
            f"{n_in} input, {n_out} output device(s) visible to PortAudio",
            critical=True,
        )
    except Exception as exc:
        return CheckResult("audio devices enumerate", "FAIL", str(exc), critical=True)


def check_configured_devices(config_path: str) -> CheckResult:
    try:
        import sounddevice as sd
        from live.pipeline import _load_config
        cfg = _load_config(config_path)
        audio_cfg = cfg["audio"]
        problems = []
        for key in ("input_device", "output_device"):
            dev = audio_cfg.get(key)
            if dev is None:
                continue  # null = auto-detect, always "valid"
            try:
                sd.query_devices(dev)
            except Exception as exc:
                problems.append(f"{key}={dev!r}: {exc}")
        if audio_cfg.get("dual_mic", {}).get("enabled"):
            ref_dev = audio_cfg["dual_mic"].get("reference_device")
            if ref_dev is not None:
                try:
                    sd.query_devices(ref_dev)
                except Exception as exc:
                    problems.append(f"dual_mic.reference_device={ref_dev!r}: {exc}")
        if problems:
            return CheckResult(
                "configured device indices valid", "WARN",
                "stale index (will auto-detect instead, see live/pipeline.py::_resolve_device): "
                + "; ".join(problems),
                critical=False,
            )
        return CheckResult("configured device indices valid", "PASS",
                            "all configured device indices resolve on this machine", critical=True)
    except Exception as exc:
        return CheckResult("configured device indices valid", "FAIL", str(exc), critical=True)


def check_model_loads(config_path: str) -> CheckResult:
    try:
        from live.pipeline import _load_config
        from live.inference_engine import InferenceEngine
        cfg = _load_config(config_path)
        t0 = time.perf_counter()
        engine = InferenceEngine(
            sample_rate=int(cfg["audio"]["sample_rate"]),
            atten_lim_db=float(cfg["model"].get("atten_lim_db", 30.0)),
            warmup_passes=1,
        )
        elapsed = time.perf_counter() - t0
        import numpy as np
        chunk = np.zeros(int(cfg["audio"]["sample_rate"] * cfg["audio"]["chunk_duration_sec"]), dtype=np.float32)
        out = engine.enhance_chunk(chunk)
        assert out is not None and not np.isnan(out).any(), "enhance_chunk produced NaN on silence"
        return CheckResult("DeepFilterNet model loads + runs", "PASS",
                            f"loaded and produced a valid output in {elapsed:.2f}s", critical=True)
    except Exception as exc:
        return CheckResult("DeepFilterNet model loads + runs", "FAIL", str(exc), critical=True)


def check_optional_dep(mod_name: str, feature: str) -> CheckResult:
    import importlib.util
    try:
        available = importlib.util.find_spec(mod_name) is not None
    except (ImportError, ValueError):
        available = False
    if available:
        return CheckResult(f"optional dep: {mod_name} ({feature})", "PASS",
                            "installed", critical=False)
    return CheckResult(f"optional dep: {mod_name} ({feature})", "WARN",
                        f"not installed -- {feature} will be unavailable this session "
                        f"(see requirements-optional.txt)", critical=False)


def check_backup_clip_present() -> CheckResult:
    path = os.path.join("demo", "backup_audio", "backup_60s.wav")
    if os.path.exists(path):
        return CheckResult("backup demo clip", "PASS", f"{path} present", critical=False)
    return CheckResult(
        "backup demo clip", "WARN",
        f"{path} not found -- build it now: python demo/backup_playback.py --generate "
        f"(so the mic-failure fallback is ready before, not during, the demo)",
        critical=False,
    )


def check_self_tests() -> CheckResult:
    try:
        t0 = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, "scripts/run_all_selftests.py"],
            cwd=_REPO_ROOT, capture_output=True, text=True,
        )
        elapsed = time.perf_counter() - t0
        if proc.returncode == 0:
            return CheckResult("full self-test suite", "PASS",
                                f"all green in {elapsed:.1f}s", critical=True)
        tail = "\n".join(proc.stdout.strip().splitlines()[-15:])
        return CheckResult("full self-test suite", "FAIL",
                            f"exit code {proc.returncode} after {elapsed:.1f}s. Tail:\n{tail}",
                            critical=True)
    except Exception as exc:
        return CheckResult("full self-test suite", "FAIL", str(exc), critical=True)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_preflight(config_path: str = "config/audio_config.yaml", skip_selftests: bool = False) -> list:
    results = []
    results.append(check_config_loads(config_path))
    results.append(check_devices_enumerate())
    results.append(check_configured_devices(config_path))
    results.append(check_model_loads(config_path))
    results.append(check_backup_clip_present())
    for mod, feature in [
        ("fastapi", "web dashboard, WOW #2"),
        ("uvicorn", "web dashboard server, WOW #2"),
        ("qrcode", "web dashboard QR code, WOW #2"),
        ("onnxruntime", "DNSMOS quality monitor, WOW #3"),
        ("numba", "reference NLMS / residual filter / fast_resample"),
    ]:
        results.append(check_optional_dep(mod, feature))
    if not skip_selftests:
        results.append(check_self_tests())
    return results


def print_report(results: list) -> bool:
    """Prints the red/green report. Returns True iff safe to demo (no CRITICAL FAIL)."""
    print(f"\n{BOLD}{'=' * 72}\nPS26052 PRE-FLIGHT CHECK\n{'=' * 72}{RESET}")
    safe = True
    for r in results:
        print(f"  {_mark(r.status)} {r.name}")
        if r.status != "PASS":
            for line in r.message.splitlines():
                print(f"           {line}")
        if r.status == "FAIL" and r.critical:
            safe = False

    print(f"{BOLD}{'=' * 72}{RESET}")
    if safe:
        print(f"{GREEN}{BOLD}READY -- safe to start the demo.{RESET}")
    else:
        print(f"{RED}{BOLD}NOT READY -- resolve the FAIL item(s) above before demoing.{RESET}")
    print(f"{'=' * 72}\n")
    return safe


# ---------------------------------------------------------------------------
# Self-test (Mode A -- exercises the check/report logic with synthetic
# results; does NOT require this to run on demo hardware)
# ---------------------------------------------------------------------------

def _self_test():
    print("scripts/preflight_check.py self-test -- start")
    ok = True

    # --- Test 1: a critical FAIL makes print_report return unsafe ---
    fake_results = [
        CheckResult("thing A", "PASS", "", critical=True),
        CheckResult("thing B", "FAIL", "simulated failure", critical=True),
    ]
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        safe = print_report(fake_results)
    if safe is False:
        print("  [PASS] test 1: a critical FAIL correctly makes the overall verdict unsafe")
    else:
        print("  [FAIL] test 1: critical FAIL did not block the verdict")
        ok = False

    # --- Test 2: a non-critical WARN does not block the verdict ---
    fake_results = [
        CheckResult("thing A", "PASS", "", critical=True),
        CheckResult("thing B", "WARN", "simulated advisory", critical=False),
    ]
    with contextlib.redirect_stdout(buf):
        safe = print_report(fake_results)
    if safe is True:
        print("  [PASS] test 2: a non-critical WARN does not block the verdict")
    else:
        print("  [FAIL] test 2: WARN incorrectly blocked the verdict")
        ok = False

    # --- Test 3: all-PASS is safe ---
    fake_results = [CheckResult("thing A", "PASS", "", critical=True)]
    with contextlib.redirect_stdout(buf):
        safe = print_report(fake_results)
    if safe is True:
        print("  [PASS] test 3: all-PASS reports safe")
    else:
        print("  [FAIL] test 3: all-PASS incorrectly reported unsafe")
        ok = False

    # --- Test 4: check_config_loads runs for real against the real config ---
    r = check_config_loads("config/audio_config.yaml")
    if r.status == "PASS":
        print("  [PASS] test 4: check_config_loads() PASSes against the real repo config")
    else:
        print(f"  [FAIL] test 4: real config check failed: {r.message}")
        ok = False

    # --- Test 5: an absent optional dependency reports WARN, not FAIL ---
    r = check_optional_dep("definitely_not_a_real_module_xyz", "nothing")
    if r.status == "WARN" and r.critical is False:
        print("  [PASS] test 5: a missing optional dependency is WARN (non-critical), not FAIL")
    else:
        print(f"  [FAIL] test 5: expected WARN/non-critical, got {r.status}/{r.critical}")
        ok = False

    print("scripts/preflight_check.py self-test -- " + ("ALL PASSED" if ok else "FAILURES PRESENT"))
    return ok


def main():
    parser = argparse.ArgumentParser(description="Phase 5.3(c) -- pre-demo readiness gate")
    parser.add_argument("--config", default="config/audio_config.yaml")
    parser.add_argument("--skip-selftests", action="store_true",
                         help="Skip the full self-test suite (faster, less coverage)")
    parser.add_argument("--self-test", action="store_true",
                         help="Test the preflight check logic itself, not demo hardware")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(0 if _self_test() else 1)

    results = run_preflight(args.config, skip_selftests=args.skip_selftests)
    safe = print_report(results)
    sys.exit(0 if safe else 1)


if __name__ == "__main__":
    main()
