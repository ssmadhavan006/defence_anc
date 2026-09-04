"""
scripts/run_all_selftests.py — Unified Mode A self-test runner.

Every module in this repo carries its own embedded self-test (ring_buffer,
inference_engine, run_inference, the spectrogram demo, ...), run individually
via `python <module>` or `python <module> --self-test`. This script just
invokes each of them in sequence, using the current interpreter, and prints
one PASS/FAIL summary — so "does the whole offline stack still work" is one
command instead of remembering five.

This only covers Mode A (no physical audio hardware required). Mode B tests
(live/detect_devices.py, live/latency_test.py, live/stress_test.py,
demo/dashboard.py, demo/spectrogram.py without --self-test) require the
Raspberry Pi and are intentionally NOT run here — see rules.md Rule 29.

Usage:
    uv run python scripts/run_all_selftests.py
    python scripts/run_all_selftests.py --skip-dfn   # skip model-loading tests (faster)
"""

import argparse
import subprocess
import sys
import time

# (name, command, needs_model, optional_dep)
# optional_dep: if set, this test covers a feature whose dependency lives in
# requirements-optional.txt. When that module isn't importable, the test is
# reported as SKIP rather than FAIL -- the feature is genuinely optional and
# off by default, so its absence is not a broken build. Notably the ONNX
# backend CANNOT be installed on Python 3.13 at all (upstream ml_dtypes
# requires numpy>=2.1 there, deepfilternet requires numpy<2.0) -- see
# requirements-optional.txt for the full explanation.
TESTS = [
    ("ring_buffer",       [sys.executable, "live/ring_buffer.py"], False, None),
    ("inference_engine",  [sys.executable, "live/inference_engine.py"], True, None),
    ("run_inference",     [sys.executable, "models/deepfilternet/run_inference.py", "--self-test"], True, None),
    ("spectrogram_demo",  [sys.executable, "demo/spectrogram.py", "--self-test"], False, None),
    ("e2e_latency_logic", [sys.executable, "live/e2e_latency_test.py", "--self-test"], False, None),
    ("augment",           [sys.executable, "data/augment.py", "--self-test"], False, None),
    ("residual_filter",   [sys.executable, "live/residual_filter.py", "--self-test"], False, "numba"),
    ("reference_nlms",   [sys.executable, "live/reference_nlms.py", "--self-test"], False, "numba"),
    ("calibrate_mic_pair", [sys.executable, "live/calibrate_mic_pair.py", "--self-test"], False, None),
    # Phase 3 (quality validation) self-tests -- all Mode A, no hardware.
    ("sweep_atten_lim",   [sys.executable, "scripts/sweep_atten_lim.py", "--self-test"], False, None),
    ("postproc_experiments", [sys.executable, "scripts/postproc_experiments.py", "--self-test"], False, None),
    ("simulate_reference_channel", [sys.executable, "scripts/simulate_reference_channel.py", "--self-test"], False, None),
    # Phase 2 (latency engineering) self-tests -- all Mode A, no hardware.
    ("latency_budget",    [sys.executable, "live/latency_budget.py"], False, None),
    ("pipeline_logic",    [sys.executable, "live/pipeline.py", "--self-test"], False, None),
    ("cpu_affinity",      [sys.executable, "live/cpu_affinity.py", "--self-test"], False, None),
    ("fast_resample",     [sys.executable, "live/fast_resample.py", "--self-test"], False, "numba"),
    ("acoustic_latency_logic", [sys.executable, "live/acoustic_latency_test.py", "--self-test"], False, None),
    ("export_onnx",       [sys.executable, "models/deepfilternet/export_onnx.py", "--self-test"], True, "onnxscript"),
    ("onnx_infer",        [sys.executable, "models/deepfilternet/onnx_infer.py", "--self-test"], True, "onnxscript"),
    # Phase 4 (WOW factors) self-tests -- all Mode A, no hardware.
    # noise_classifier: torch present, no trained model needed (tests logic + grouped-split guard).
    # webdash: skips if fastapi not installed; uses mock pipeline (no audio hardware).
    # dnsmos: skips if onnxruntime not installed OR model file absent (see download_model.py).
    ("noise_classifier",  [sys.executable, "models/noise_classifier/classify_chunk.py", "--self-test"], False, None),
    ("webdash",           [sys.executable, "demo/webdash/app.py", "--self-test"], False, "fastapi"),
    ("dnsmos",            [sys.executable, "models/dnsmos/dnsmos_infer.py", "--self-test"], False, "onnxruntime"),
]


def _module_available(mod_name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(mod_name) is not None
    except (ImportError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser(description="Run all Mode A (no-hardware) self-tests")
    parser.add_argument("--skip-dfn", action="store_true",
                         help="Skip tests that load the DeepFilterNet model (faster, less coverage)")
    args = parser.parse_args()

    results = []
    for name, cmd, needs_model, optional_dep in TESTS:
        if args.skip_dfn and needs_model:
            print(f"[SKIP] {name} (--skip-dfn)")
            results.append((name, "SKIP", 0.0))
            continue

        if optional_dep and not _module_available(optional_dep):
            print(f"[SKIP] {name} (optional dependency {optional_dep!r} not installed "
                  f"-- see requirements-optional.txt)")
            results.append((name, "SKIP", 0.0))
            continue

        print(f"\n{'=' * 70}\n[RUN]  {name}  ->  {' '.join(cmd)}\n{'=' * 70}")
        t0 = time.perf_counter()
        proc = subprocess.run(cmd, cwd=".")
        elapsed = time.perf_counter() - t0
        status = "PASS" if proc.returncode == 0 else "FAIL"
        results.append((name, status, elapsed))

    print(f"\n{'=' * 70}\nSELF-TEST SUMMARY\n{'=' * 70}")
    all_pass = True
    for name, status, elapsed in results:
        marker = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[status]
        print(f"  {marker} {name:<20s} {elapsed:6.2f}s")
        if status == "FAIL":
            all_pass = False

    print(f"{'=' * 70}")
    if all_pass:
        print("ALL MODE A SELF-TESTS PASSED (Mode B / Pi hardware tests not included)")
        sys.exit(0)
    else:
        print("ONE OR MORE SELF-TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
