"""
live/e2e_latency_test.py — Device-level round-trip latency measurement.

Unlike live/latency_test.py (which is explicitly Mode A: it calls
InferenceEngine.enhance_chunk() directly on in-memory arrays and never
touches sounddevice), THIS test drives real sounddevice.playrec() through
the actual configured input/output devices -- real PortAudio, real ALSA
buffers, real driver/OS scheduling. On the Pi, pointed at the snd-aloop
loopback already used successfully by live/pipeline.py, this measures the
genuine device-I/O round-trip: input block fill + output block drain +
driver/OS buffering overhead. That is most of the ~530 ms standing latency
budget documented in summary/02_NEXT_STEPS_PLAN.md Section 1.

WHAT THIS DOES NOT MEASURE: DeepFilterNet inference is not in this loop --
there is no running InferenceEngine here, just a raw click played and
recorded through the device pair. Combine this test's result with
live/latency_test.py's measured inference time and the configured
priming_chunks to get the full analytical end-to-end estimate (this script
does that arithmetic for you in the report -- see "Full pipeline estimate").
A single physically-measured number that includes a *running* pipeline with
real inference in the loop still requires either a physical mic/speaker
loopback, or independently confirming this Pi's snd-aloop topology supports
a second concurrent listener -- neither of which this script assumes.

Usage:
    # On the Pi, with the loopback already working (same config pipeline.py uses):
    python live/e2e_latency_test.py --n-reps 20

    # Combine with a known inference time to see the full estimate:
    python live/e2e_latency_test.py --n-reps 20 --inference-ms 29.18

    # Pure-logic self-test, no hardware required:
    python live/e2e_latency_test.py --self-test
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

SR = 48000


def find_click_lag(recorded: np.ndarray, click_pos: int, min_peak_ratio: float = 20.0) -> int:
    """
    Locate a click's arrival sample in a recorded buffer relative to where
    it was emitted (click_pos), by finding the peak-magnitude sample and
    checking it clears the noise floor by min_peak_ratio.

    Returns the lag in samples (recorded_peak_index - click_pos). Raises
    RuntimeError if no clear peak is found (e.g. loopback not wired, or
    device opened in the wrong direction) -- this deliberately does not
    return a silently-bogus number.
    """
    abs_rec = np.abs(recorded)
    peak_idx = int(np.argmax(abs_rec))
    peak_val = abs_rec[peak_idx]

    # Noise floor: median absolute amplitude away from the peak.
    noise_region = np.delete(abs_rec, slice(max(0, peak_idx - 50), peak_idx + 50))
    noise_floor = float(np.median(noise_region)) if len(noise_region) > 0 else 1e-8
    noise_floor = max(noise_floor, 1e-8)

    if peak_val < noise_floor * min_peak_ratio:
        raise RuntimeError(
            f"No clear click detected (peak={peak_val:.5f}, noise_floor={noise_floor:.5f}, "
            f"ratio={peak_val/noise_floor:.2f} < required {min_peak_ratio}). "
            "Check that input_device/output_device in audio_config.yaml form a working "
            "loopback -- run `python live/main.py detect` and verify with `aplay`/`arecord` first."
        )

    return peak_idx - click_pos


def measure_device_roundtrip(
    input_device,
    output_device,
    sr: int = SR,
    click_amplitude: float = 0.5,
    pad_sec: float = 0.5,
    tail_sec: float = 1.0,
    n_reps: int = 20,
    n_warmup: int = 3,
) -> dict:
    """
    Play a click through output_device and simultaneously record from
    input_device using sd.playrec() (real device I/O, blocking). Repeats
    n_reps times (after n_warmup discarded reps) and reports the lag
    statistics. Requires a working hardware or loopback audio path.
    """
    import sounddevice as sd

    click_pos = int(pad_sec * sr)
    total_samples = int((pad_sec + tail_sec) * sr)

    def one_rep():
        play_buf = np.zeros((total_samples, 1), dtype=np.float32)
        play_buf[click_pos, 0] = click_amplitude
        rec_buf = sd.playrec(
            play_buf, samplerate=sr, channels=1,
            device=(input_device, output_device), blocking=True, dtype="float32",
        )
        sd.wait()
        return find_click_lag(rec_buf[:, 0], click_pos)

    for _ in range(n_warmup):
        one_rep()

    lags = []
    for i in range(n_reps):
        lag = one_rep()
        lags.append(lag)

    lags_arr = np.array(lags, dtype=np.float64)
    lag_ms = lags_arr / sr * 1000.0

    return {
        "n_reps": n_reps,
        "n_warmup": n_warmup,
        "lags_samples": [int(x) for x in lags],
        "lags_ms": [round(float(x), 3) for x in lag_ms],
        "median_lag_samples": float(np.median(lags_arr)),
        "median_lag_ms": round(float(np.median(lag_ms)), 3),
        "p95_lag_ms": round(float(np.percentile(lag_ms, 95)), 3),
        "max_lag_ms": round(float(np.max(lag_ms)), 3),
        "min_lag_ms": round(float(np.min(lag_ms)), 3),
    }


def _self_test():
    """Mode A: exercise find_click_lag() with synthetic arrays, no hardware."""
    print("e2e_latency_test.py self-test -- start")

    sr = 48000
    click_pos = int(0.5 * sr)
    true_lag_samples = 960  # 20 ms

    rec = np.zeros(int(1.5 * sr), dtype=np.float32)
    rec[click_pos + true_lag_samples] = 0.5
    rec += (np.random.default_rng(0).standard_normal(len(rec)) * 1e-5).astype(np.float32)

    lag = find_click_lag(rec, click_pos)
    assert lag == true_lag_samples, f"expected {true_lag_samples}, got {lag}"
    print(f"  [PASS] test 1: find_click_lag recovers known lag ({true_lag_samples} samples)")

    silent = np.zeros(int(1.5 * sr), dtype=np.float32)
    silent += (np.random.default_rng(1).standard_normal(len(silent)) * 1e-4).astype(np.float32)
    try:
        find_click_lag(silent, click_pos)
        raise AssertionError("expected RuntimeError on a click-free recording")
    except RuntimeError:
        pass
    print("  [PASS] test 2: find_click_lag raises RuntimeError when no click is present (no silent wrong answers)")

    print("e2e_latency_test.py self-test -- ALL PASSED")


def main():
    parser = argparse.ArgumentParser(
        description="PS26052 Phase 5 — Real device-I/O round-trip latency (Mode B, requires hardware/loopback)"
    )
    parser.add_argument("--config", default="config/audio_config.yaml", help="Path to audio_config.yaml")
    parser.add_argument("--n-reps", type=int, default=20, help="Measurement repetitions (project spec: 20)")
    parser.add_argument("--n-warmup", type=int, default=3, help="Warmup repetitions, discarded")
    parser.add_argument("--inference-ms", type=float, default=None,
                         help="Measured inference time (ms) from live/latency_test.py, "
                              "to compute the full analytical pipeline estimate")
    parser.add_argument("--output-json", default=None, help="Path to save JSON results")
    parser.add_argument("--self-test", action="store_true", help="Run offline logic self-test and exit (no hardware)")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    from live.pipeline import _load_config, _resolve_device

    config = _load_config(args.config)
    in_dev = _resolve_device(config["audio"].get("input_device"), kind="input")
    out_dev = _resolve_device(config["audio"].get("output_device"), kind="output")
    sr = int(config["audio"]["sample_rate"])
    chunk_sec = float(config["audio"]["chunk_duration_sec"])
    priming_chunks = int(config["pipeline"].get("priming_chunks", 1))

    print("=== Phase 5 Device-I/O Round-Trip Latency Test (Mode B) ===")
    print(f"Input device : {in_dev!r}")
    print(f"Output device: {out_dev!r}")
    print(f"Reps         : {args.n_reps} (+ {args.n_warmup} warmup)")
    print()
    print("NOTE: this measures the raw device/driver round-trip via a click "
          "loopback. It does NOT run DeepFilterNet inference -- see the "
          "module docstring for what it does and doesn't cover.")
    print()

    result = measure_device_roundtrip(
        in_dev, out_dev, sr=sr, n_reps=args.n_reps, n_warmup=args.n_warmup,
    )

    print("=== Results ===")
    print(f"  Median device round-trip: {result['median_lag_ms']:.2f} ms")
    print(f"  P95: {result['p95_lag_ms']:.2f} ms | Min: {result['min_lag_ms']:.2f} ms | Max: {result['max_lag_ms']:.2f} ms")
    print(f"  Individual lags (ms): {result['lags_ms']}")

    priming_ms = priming_chunks * chunk_sec * 1000.0
    print()
    print(f"  Configured priming: {priming_chunks} chunk(s) x {chunk_sec*1000:.0f} ms = {priming_ms:.0f} ms")

    if args.inference_ms is not None:
        full_estimate = result["median_lag_ms"] + args.inference_ms + priming_ms
        print(f"  Supplied inference time: {args.inference_ms:.2f} ms")
        print()
        print(f"  === Full pipeline ANALYTICAL estimate: {full_estimate:.1f} ms ===")
        print("  (device round-trip + inference + priming -- an engineering estimate")
        print("   combining two real measurements, not one unified physical measurement)")
    else:
        print()
        print("  Pass --inference-ms <value> (from live/latency_test.py's median_wall_latency_ms)")
        print("  to compute the full analytical end-to-end estimate.")

    if args.output_json:
        result["input_device"] = str(in_dev)
        result["output_device"] = str(out_dev)
        result["priming_chunks"] = priming_chunks
        result["priming_ms"] = round(priming_ms, 3)
        if args.inference_ms is not None:
            result["inference_ms"] = args.inference_ms
            result["full_pipeline_estimate_ms"] = round(result["median_lag_ms"] + args.inference_ms + priming_ms, 3)
        os.makedirs(os.path.dirname(args.output_json) or ".", exist_ok=True)
        with open(args.output_json, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nSaved results to: {args.output_json}")


if __name__ == "__main__":
    main()
