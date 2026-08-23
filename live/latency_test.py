"""
live/latency_test.py — End-to-end pipeline latency measurement.

Measures round-trip audio latency using a click (impulse) loopback test:
  1. Generate a known impulse (click) at t=0 in a synthetic input buffer.
  2. Route it through InferenceEngine (enhance or bypass mode).
  3. Cross-correlate output against the reference click to find the sample-level lag.
  4. Convert lag to milliseconds and report.

This test does NOT require physical audio hardware (it operates on in-memory
audio arrays, not a sounddevice stream). It is therefore Mode A and can be
verified on both the dev machine and the Pi.

Outputs
-------
  Printed report to stdout.
  Optional JSON summary to --output-json path.

Usage
-----
  # Measure bypass latency (ring buffer + pipeline overhead only):
  python live/latency_test.py --mode bypass

  # Measure enhance latency (full inference):
  python live/latency_test.py --mode enhance

  # Save JSON results:
  python live/latency_test.py --mode enhance --output-json results/latency_pi.json

  # Custom chunk size and repetitions:
  python live/latency_test.py --mode enhance --chunk-sec 0.1 --n-reps 20
"""

import os
import sys
import time
import json
import argparse
import numpy as np

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from live.inference_engine import InferenceEngine

SR = 48000   # Fixed — DeepFilterNet3 only supports 48 kHz


def make_click(chunk_samples: int, amplitude: float = 0.5) -> np.ndarray:
    """
    Returns a float32 array of shape (chunk_samples,) with a unit impulse
    (click) placed at sample 0, scaled by amplitude. All other samples are 0.
    """
    click = np.zeros(chunk_samples, dtype=np.float32)
    click[0] = amplitude
    return click


def measure_latency_samples(
    engine: InferenceEngine,
    chunk_samples: int,
    mode: str,
    n_warmup: int = 5,
    n_reps: int = 10,
) -> dict:
    """
    Measure processing latency in samples using click cross-correlation.

    Parameters
    ----------
    engine : InferenceEngine
    chunk_samples : int
    mode : str  —  "enhance" or "bypass"
    n_warmup : int  —  warm-up reps not included in stats
    n_reps : int  —  measurement reps (post-warmup)

    Returns
    -------
    dict with keys: mode, chunk_samples, lags_samples (list), latencies_ms (list),
                    median_lag_samples, median_latency_ms, p95_latency_ms,
                    median_rtf, p95_rtf
    """
    click = make_click(chunk_samples)

    process_fn = engine.enhance_chunk if mode == "enhance" else engine.bypass_chunk

    # Warm-up
    for _ in range(n_warmup):
        process_fn(click.copy())

    lags_samples = []
    wall_latencies_ms = []

    for _ in range(n_reps):
        c = click.copy()
        t0 = time.perf_counter()
        out = process_fn(c)
        wall_ms = (time.perf_counter() - t0) * 1000.0

        # out shape: (1, n_out)
        out_mono = out[0] if out.ndim == 2 else out

        # Cross-correlate to find the peak position.
        # The cross-correlation peak position relative to the reference gives
        # the sample delay introduced by the pipeline.
        corr = np.correlate(out_mono, click, mode="full")
        lag = int(np.argmax(corr)) - (len(click) - 1)

        lags_samples.append(lag)
        wall_latencies_ms.append(wall_ms)

    audio_dur_ms = chunk_samples / SR * 1000.0
    rtfs = np.array(wall_latencies_ms) / audio_dur_ms

    result = {
        "mode": mode,
        "chunk_samples": chunk_samples,
        "chunk_duration_ms": round(audio_dur_ms, 3),
        "n_reps": n_reps,
        "n_warmup": n_warmup,
        "lags_samples": lags_samples,
        "latencies_ms": [round(x, 3) for x in wall_latencies_ms],
        "median_lag_samples": float(np.median(lags_samples)),
        "median_lag_ms": round(float(np.median(lags_samples)) / SR * 1000.0, 3),
        "median_wall_latency_ms": round(float(np.median(wall_latencies_ms)), 3),
        "p95_wall_latency_ms": round(float(np.percentile(wall_latencies_ms, 95)), 3),
        "max_wall_latency_ms": round(float(np.max(wall_latencies_ms)), 3),
        "median_rtf": round(float(np.median(rtfs)), 5),
        "p95_rtf": round(float(np.percentile(rtfs, 95)), 5),
    }
    return result


def main():
    parser = argparse.ArgumentParser(
        description="PS26052 Phase 5 — Pipeline latency measurement (click loopback)"
    )
    parser.add_argument(
        "--mode",
        choices=["enhance", "bypass"],
        default="enhance",
        help="Pipeline mode to test (default: enhance)",
    )
    parser.add_argument(
        "--chunk-sec",
        type=float,
        default=0.1,
        help="Chunk duration in seconds (default: 0.1)",
    )
    parser.add_argument(
        "--n-reps",
        type=int,
        default=10,
        help="Number of measurement repetitions (default: 10)",
    )
    parser.add_argument(
        "--n-warmup",
        type=int,
        default=5,
        help="Warm-up repetitions before measurement (default: 5)",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Path to save JSON results (optional)",
    )
    args = parser.parse_args()

    chunk_samples = int(round(SR * args.chunk_sec))

    print(f"=== Phase 5 Latency Test ===")
    print(f"Mode         : {args.mode}")
    print(f"Chunk        : {args.chunk_sec*1000:.0f} ms / {chunk_samples} samples @ {SR} Hz")
    print(f"Reps         : {args.n_reps} (+ {args.n_warmup} warmup)")
    print()

    print("Loading InferenceEngine...", flush=True)
    engine = InferenceEngine(
        sample_rate=SR,
        atten_lim_db=100.0,
        warmup_passes=args.n_warmup,
        log_timing=False,
    )

    print(f"Running {args.n_warmup} warmup + {args.n_reps} measurement reps...", flush=True)
    result = measure_latency_samples(
        engine,
        chunk_samples=chunk_samples,
        mode=args.mode,
        n_warmup=args.n_warmup,
        n_reps=args.n_reps,
    )

    # Report
    print()
    print("=== Results ===")
    print(f"  Median lag (cross-correlation): {result['median_lag_samples']:.1f} samples "
          f"= {result['median_lag_ms']:.3f} ms")
    print(f"  Wall-clock latency: "
          f"median={result['median_wall_latency_ms']:.2f} ms, "
          f"p95={result['p95_wall_latency_ms']:.2f} ms, "
          f"max={result['max_wall_latency_ms']:.2f} ms")
    print(f"  RTF: median={result['median_rtf']:.4f}, p95={result['p95_rtf']:.4f}")
    print(f"  Individual lag samples: {result['lags_samples']}")
    print(f"  Individual wall latencies (ms): {result['latencies_ms']}")

    if args.output_json:
        os.makedirs(os.path.dirname(args.output_json) or ".", exist_ok=True)
        result["hostname"] = _hostname()
        result["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(args.output_json, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nSaved results to: {args.output_json}")

    return 0


def _hostname() -> str:
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    sys.exit(main())
