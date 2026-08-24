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

TESTS = [
    ("ring_buffer",       [sys.executable, "live/ring_buffer.py"], False),
    ("inference_engine",  [sys.executable, "live/inference_engine.py"], True),
    ("run_inference",     [sys.executable, "models/deepfilternet/run_inference.py", "--self-test"], True),
    ("spectrogram_demo",  [sys.executable, "demo/spectrogram.py", "--self-test"], False),
    ("e2e_latency_logic", [sys.executable, "live/e2e_latency_test.py", "--self-test"], False),
    ("augment",           [sys.executable, "data/augment.py", "--self-test"], False),
    ("residual_filter",   [sys.executable, "live/residual_filter.py", "--self-test"], False),
    ("export_onnx",       [sys.executable, "models/deepfilternet/export_onnx.py", "--self-test"], True),
    ("onnx_infer",        [sys.executable, "models/deepfilternet/onnx_infer.py", "--self-test"], True),
]


def main():
    parser = argparse.ArgumentParser(description="Run all Mode A (no-hardware) self-tests")
    parser.add_argument("--skip-dfn", action="store_true",
                         help="Skip tests that load the DeepFilterNet model (faster, less coverage)")
    args = parser.parse_args()

    results = []
    for name, cmd, needs_model in TESTS:
        if args.skip_dfn and needs_model:
            print(f"[SKIP] {name} (--skip-dfn)")
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
