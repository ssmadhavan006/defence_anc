"""
scripts/sweep_chunk_size.py — Chunk-size sweep for latency/stability tradeoff.

Run on the Raspberry Pi (Mode B — needs the real device/loopback config to
be already working, same as live/pipeline.py). For each candidate chunk
duration, this:
  1. Temporarily overrides config/audio_config.yaml's chunk_duration_sec
     (writes a scratch copy, does not touch your real config).
  2. Measures inference latency/RTF via live/latency_test.py (Mode A, no
     device I/O -- just how long DeepFilterNet takes at that chunk size).
  3. Runs a short stability check via live/stress_test.py and counts
     dropouts (default 60 s per candidate -- shorter than the full 10-minute
     gate, intended for fast comparison; re-run the full 600 s at whichever
     chunk size you pick).
  4. Measures the real device round-trip via live/e2e_latency_test.py.
  5. Prints one summary table: chunk size, RTF, dropouts, device round-trip,
     and the full analytical end-to-end estimate for each candidate.

Selection rule (see summary/02_NEXT_STEPS_PLAN.md Section 7.3): pick the
smallest chunk size with p95 RTF <= 0.6 and 0 dropouts over the short check,
then confirm with a full 10-minute run before relying on it for the demo.

Usage:
    python scripts/sweep_chunk_size.py
    python scripts/sweep_chunk_size.py --candidates-ms 100,50,20,10 --stress-sec 60
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _make_scratch_config(base_config_path: str, chunk_sec: float, scratch_path: str):
    import yaml
    with open(base_config_path, "r") as f:
        cfg = yaml.safe_load(f)
    cfg["audio"]["chunk_duration_sec"] = chunk_sec
    with open(scratch_path, "w") as f:
        yaml.safe_dump(cfg, f)


def run_one_candidate(base_config_path: str, chunk_ms: int, stress_sec: int, results_dir: str) -> dict:
    chunk_sec = chunk_ms / 1000.0
    scratch_config = os.path.join(results_dir, f"_scratch_config_{chunk_ms}ms.yaml")
    _make_scratch_config(base_config_path, chunk_sec, scratch_config)

    row = {"chunk_ms": chunk_ms}

    # 1. Inference latency (Mode A -- safe to run anywhere, but run here on
    #    the Pi for a real number since InferenceEngine loads the real model).
    lat_json = os.path.join(results_dir, f"_sweep_latency_{chunk_ms}ms.json")
    proc = subprocess.run(
        [sys.executable, "live/latency_test.py", "--mode", "enhance",
         "--chunk-sec", str(chunk_sec), "--n-reps", "10", "--output-json", lat_json],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        row["error"] = f"latency_test failed: {proc.stderr[-500:]}"
        return row
    with open(lat_json) as f:
        lat = json.load(f)
    row["median_inference_ms"] = lat["median_wall_latency_ms"]
    row["p95_inference_ms"] = lat["p95_wall_latency_ms"]
    row["p95_rtf"] = lat["p95_rtf"]

    # 2. Short stability check (Mode B -- needs the real loopback/device).
    stress_json = os.path.join(results_dir, f"_sweep_stress_{chunk_ms}ms.json")
    proc = subprocess.run(
        [sys.executable, "live/stress_test.py", "--duration", str(stress_sec),
         "--config", scratch_config, "--output-json", stress_json],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    try:
        with open(stress_json) as f:
            stress = json.load(f)
        row["dropouts"] = stress["total_dropouts"]
        row["stress_verdict"] = stress["verdict"]
    except Exception as e:
        row["dropouts"] = None
        row["stress_verdict"] = f"UNKNOWN ({e})"

    # 3. Real device round-trip (Mode B).
    e2e_json = os.path.join(results_dir, f"_sweep_e2e_{chunk_ms}ms.json")
    proc = subprocess.run(
        [sys.executable, "live/e2e_latency_test.py", "--config", scratch_config,
         "--n-reps", "10", "--inference-ms", str(row["median_inference_ms"]),
         "--output-json", e2e_json],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    try:
        with open(e2e_json) as f:
            e2e = json.load(f)
        row["device_roundtrip_ms"] = e2e["median_lag_ms"]
        row["full_estimate_ms"] = e2e.get("full_pipeline_estimate_ms")
    except Exception as e:
        row["device_roundtrip_ms"] = None
        row["full_estimate_ms"] = None
        row["e2e_error"] = f"e2e_latency_test failed or device unavailable: {proc.stderr[-300:] if proc.returncode else e}"

    return row


def main():
    parser = argparse.ArgumentParser(description="Sweep chunk size for latency/stability tradeoff (run on Pi)")
    parser.add_argument("--config", default="config/audio_config.yaml", help="Base config to sweep from")
    parser.add_argument("--candidates-ms", default="100,50,20,10", help="Comma-separated chunk sizes in ms")
    parser.add_argument("--stress-sec", type=int, default=60, help="Short stability check duration per candidate")
    parser.add_argument("--output-json", default="results/chunk_sweep_report.json")
    args = parser.parse_args()

    candidates = [int(x) for x in args.candidates_ms.split(",")]
    results_dir = "results"
    os.makedirs(results_dir, exist_ok=True)

    rows = []
    for chunk_ms in candidates:
        print(f"\n{'='*70}\nCandidate: {chunk_ms} ms chunk\n{'='*70}")
        row = run_one_candidate(args.config, chunk_ms, args.stress_sec, results_dir)
        rows.append(row)
        print(json.dumps(row, indent=2))

    def _fmt(v):
        # dict.get(key, default) only applies default when the KEY is
        # missing -- rows store explicit None on failure, which .get()
        # happily returns as-is and then crashes str.format on NoneType.
        return "" if v is None else v

    print(f"\n{'='*70}\nSWEEP SUMMARY\n{'='*70}")
    header = f"{'Chunk(ms)':<10} {'P95 RTF':<10} {'Dropouts':<10} {'DeviceRT(ms)':<14} {'FullEst(ms)':<12}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{_fmt(r.get('chunk_ms')):<10} {_fmt(r.get('p95_rtf')):<10} {_fmt(r.get('dropouts')):<10} "
              f"{_fmt(r.get('device_roundtrip_ms')):<14} {_fmt(r.get('full_estimate_ms')):<12}")
        if r.get("error"):
            print(f"  [error] {r['error']}")
        if r.get("e2e_error"):
            print(f"  [e2e_error] {r['e2e_error'].strip().splitlines()[-1]}")

    print("\nSelection rule: smallest chunk with p95 RTF <= 0.6 AND dropouts == 0.")
    print("Confirm the chosen chunk size with a full 10-minute stress test before the demo:")
    print("  python live/main.py stress --duration 600")

    with open(args.output_json, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"\nFull report saved to: {args.output_json}")


if __name__ == "__main__":
    main()
