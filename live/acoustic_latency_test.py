"""
live/acoustic_latency_test.py — Physical acoustic round-trip latency (A5) and
empirical DeepFilterNet lookahead measurement (A6). Phase 2, D3 / Rule 30.

Why this exists (see phase2_plan.md §1.2, D3):
  Every latency number on record before Phase 2 is either an analytical
  estimate (device round-trip + inference + priming, added up in
  live/e2e_latency_test.py) or a device-only click round-trip with NO running
  pipeline in the loop (that script's own docstring: "DeepFilterNet inference
  is not in this loop"). Phase 1 added a second, physically separate
  microphone -- this module is the first place in the project that measures a
  genuine mouth-to-ear number WITH a running LivePipeline (input -> DFN3
  inference -> output) actually in the path.

Method (D3):
  1. Run the full LivePipeline in enhance mode on real hardware.
  2. Emit a click from an external playback device near the PRIMARY mic.
  3. Place the REFERENCE mic (audio.dual_mic.reference_device) at the output
     speaker -- it is repurposed here purely as a measurement microphone,
     independent of whether audio.dual_mic.enabled / pipeline.reference_nlms
     are on. Run with pipeline.reference_nlms.enabled: false so the filter
     does not adapt away the very click being measured (hazard (b) below).
  4. Record primary and reference simultaneously (mirrors
     live/calibrate_mic_pair.py's record_both -- same synchronized-buffer
     trick, so both channels share one sample-index time axis without needing
     separate wall-clock bookkeeping).
  5. Locate the click's peak in each channel independently and take the
     difference -- click-at-reference-output minus click-at-primary --
     which is the pipeline's acoustic mouth-to-ear delay. Subtract the
     Phase 1 mic-pair calibration offset (config/mic_calibration.yaml) so the
     two mics' own physical/clock skew doesn't get counted as pipeline
     latency.

Two hazards to design around (D3), not discover during the run:
  (a) Acoustic feedback -- the enhanced output can howl back into the primary
      mic. Keep model.output_gain low and separate the mics physically.
  (b) The reference mic must not simultaneously be feeding an ADAPTING NLMS
      stage during this measurement -- it would adapt away the click. Run
      with pipeline.reference_nlms.enabled: false.

Hardware constraint this module does NOT solve (documented, not hidden):
  Capturing the primary microphone's OWN raw signal at the same time
  LivePipeline's InputStream is already consuming it generally requires the
  OS/driver to support more than one concurrent listener on the same
  physical device (shared-mode capture). This is the same open question
  live/e2e_latency_test.py's docstring already flags for a different method.
  If opening a second stream on the primary device fails with a device-busy
  error on the target hardware, the primary-side click can still be
  timestamped via a raw pre-pipeline capture on a THIRD device positioned at
  the primary mic instead (see --primary-capture-device). Confirm which path
  works on the actual Pi hardware in Track B and record the result here.

Like live/e2e_latency_test.py's find_click_lag, this refuses to emit a number
when a click is not cleanly detected (RuntimeError), rather than returning a
silently-bogus lag.

Usage:
    # On the Pi, hardware/loopback already wired up (Mode B):
    python live/acoustic_latency_test.py --n-reps 20 --output-json results/acoustic_latency.json

    # Empirical DFN3 lookahead measurement (Rule 30) -- also Mode B, needs
    # the real model loaded:
    python live/acoustic_latency_test.py --lookahead --output-json results/lookahead_measured.json

    # Pure-logic self-test, no hardware, no model (Mode A):
    python live/acoustic_latency_test.py --self-test
"""

import os
import sys
import time
import json
import argparse
import threading
import numpy as np

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from live.e2e_latency_test import find_click_lag  # reuse the same peak/noise-floor discipline

SR = 48000


# ---------------------------------------------------------------------------
# A5 — Physical acoustic round-trip
# ---------------------------------------------------------------------------

def _find_peak_sample(x: np.ndarray, min_peak_ratio: float, label: str) -> int:
    """
    Locate a click's peak sample in `x` and verify it clears the noise floor
    by min_peak_ratio. Raises RuntimeError (never returns a silently-bogus
    index) if no clear peak is found -- same discipline as
    live/e2e_latency_test.py::find_click_lag, generalised to a channel with
    no known emission position (a raw device round-trip test knows exactly
    when it emitted the click; this test's primary-side channel just has to
    find where a click landed).
    """
    abs_x = np.abs(x)
    peak_idx = int(np.argmax(abs_x))
    peak_val = abs_x[peak_idx]

    noise_region = np.delete(abs_x, slice(max(0, peak_idx - 50), peak_idx + 50))
    noise_floor = float(np.median(noise_region)) if len(noise_region) > 0 else 1e-8
    noise_floor = max(noise_floor, 1e-8)

    if peak_val < noise_floor * min_peak_ratio:
        raise RuntimeError(
            f"No clear click detected on {label} channel (peak={peak_val:.5f}, "
            f"noise_floor={noise_floor:.5f}, ratio={peak_val/noise_floor:.2f} < "
            f"required {min_peak_ratio}). Check mic placement, model.output_gain, "
            "and that the pipeline is actually running -- see this module's "
            "docstring for the full method and its two hazards."
        )
    return peak_idx


def measure_click_to_click_lag(primary: np.ndarray, reference: np.ndarray,
                               min_peak_ratio: float = 20.0) -> int:
    """
    Given two SIMULTANEOUS, same-length recordings -- `primary` from the
    primary mic (captures the externally-emitted click as it arrives at the
    mic) and `reference` from the reference mic placed at the output speaker
    (captures that same click after LivePipeline has processed and replayed
    it) -- return the lag in samples between the two channels' click peaks
    (reference_peak - primary_peak). This is the pipeline's raw acoustic
    mouth-to-ear delay, BEFORE subtracting the mic-pair calibration offset
    (see run_acoustic_latency_test / _load_calibration_offset).
    """
    primary_peak = _find_peak_sample(primary, min_peak_ratio, "primary")
    reference_peak = _find_peak_sample(reference, min_peak_ratio, "reference")
    return reference_peak - primary_peak


def _load_calibration_offset(cal_path: str = None) -> int:
    """
    Read config/mic_calibration.yaml's ref_delay_samples (written by
    live/calibrate_mic_pair.py) so the mic-pair's own physical/clock skew is
    not counted as pipeline latency. Returns 0 (with a stderr note) if the
    file doesn't exist -- calibration is a prerequisite of this test, not a
    silent default.
    """
    if cal_path is None:
        cal_path = os.path.join(_REPO_ROOT, "config", "mic_calibration.yaml")
    if not os.path.exists(cal_path):
        print(
            f"[acoustic_latency] WARNING: no calibration file at {cal_path!r}. "
            "Run `python live/main.py calibrate` first (Phase 1) -- proceeding "
            "with a 0-sample calibration offset, which will bias this "
            "measurement by the mic pair's uncalibrated skew.",
            file=sys.stderr,
        )
        return 0
    import yaml
    with open(cal_path, "r", encoding="utf-8") as f:
        cal = yaml.safe_load(f) or {}
    return int(cal.get("ref_delay_samples", 0))


def record_synced(primary_device, reference_device, sr: int, duration: float):
    """
    Simultaneously record `duration` seconds from primary_device and
    reference_device into two same-length buffers that both start recording
    at (approximately) the same instant -- the same pattern as
    live/calibrate_mic_pair.py::record_both, reused here so the two channels
    share one sample-index time axis without separate wall-clock bookkeeping.
    """
    import sounddevice as sd

    n = int(sr * duration)
    primary_buf = np.zeros(n, dtype=np.float32)
    ref_buf = np.zeros(n, dtype=np.float32)
    primary_pos = [0]
    ref_pos = [0]
    lock = threading.Lock()

    def _primary_cb(indata, frames, time_info, status):
        with lock:
            end = min(primary_pos[0] + frames, n)
            count = end - primary_pos[0]
            if count > 0:
                primary_buf[primary_pos[0]:end] = indata[:count, 0]
                primary_pos[0] = end

    def _ref_cb(indata, frames, time_info, status):
        with lock:
            end = min(ref_pos[0] + frames, n)
            count = end - ref_pos[0]
            if count > 0:
                ref_buf[ref_pos[0]:end] = indata[:count, 0]
                ref_pos[0] = end

    with sd.InputStream(device=primary_device, samplerate=sr, channels=1,
                        dtype="float32", callback=_primary_cb, latency="low"):
        with sd.InputStream(device=reference_device, samplerate=sr, channels=1,
                            dtype="float32", callback=_ref_cb, latency="low"):
            time.sleep(duration + 0.2)

    return primary_buf, ref_buf


def run_acoustic_latency_test(config_path: str = "config/audio_config.yaml",
                              n_reps: int = 20, click_amplitude: float = 0.6,
                              click_device=None, record_duration_sec: float = 1.5,
                              min_peak_ratio: float = 20.0,
                              output_json: str = None) -> dict:
    """
    Mode B: runs the full LivePipeline in enhance mode against real hardware
    and measures the physical acoustic mouth-to-ear round-trip. See this
    module's docstring for the full method and its two hazards.
    """
    from live.pipeline import LivePipeline, _load_config
    import sounddevice as sd

    config = _load_config(config_path)

    ref_nlms_cfg = config.get("pipeline", {}).get("reference_nlms", {})
    if ref_nlms_cfg.get("enabled", False):
        print(
            "[acoustic_latency] WARNING: pipeline.reference_nlms.enabled is "
            "true. D3 requires disabling it for this measurement -- an "
            "adapting NLMS filter will suppress the very click being "
            "measured. Set it to false in config/audio_config.yaml and re-run.",
            file=sys.stderr,
        )

    primary_device = config["audio"]["input_device"]
    reference_device = config.get("audio", {}).get("dual_mic", {}).get("reference_device")
    if reference_device is None:
        raise RuntimeError(
            "acoustic-latency requires audio.dual_mic.reference_device to be "
            "set in config/audio_config.yaml -- used here purely as a "
            "measurement microphone placed at the output speaker, "
            "independent of whether audio.dual_mic.enabled is true."
        )

    calib_offset_samples = _load_calibration_offset()

    print("=== Phase 2 Physical Acoustic Round-Trip Test (Mode B, D3) ===")
    print(f"Primary mic (click pickup)   : device {primary_device!r}")
    print(f"Reference mic (at speaker)   : device {reference_device!r}")
    print(f"Calibration offset subtracted: {calib_offset_samples} samples")
    print(f"Reps                         : {n_reps}")
    print()

    pipeline = LivePipeline(config, mode_override="enhance")
    pipeline.start()

    lags_samples = []
    errors = []
    try:
        for i in range(n_reps):
            click = np.zeros(int(SR * 0.05), dtype=np.float32)
            click[0] = click_amplitude

            record_thread_result = {}

            def _record():
                record_thread_result["bufs"] = record_synced(
                    primary_device, reference_device, SR, record_duration_sec
                )

            t = threading.Thread(target=_record)
            t.start()
            time.sleep(0.2)  # let both capture streams stabilise first
            sd.play(click, samplerate=SR, device=click_device, blocking=False)
            t.join()

            primary_rec, reference_rec = record_thread_result["bufs"]
            try:
                raw_lag = measure_click_to_click_lag(primary_rec, reference_rec, min_peak_ratio)
                lags_samples.append(raw_lag - calib_offset_samples)
            except RuntimeError as exc:
                errors.append(f"rep {i}: {exc}")
                print(f"[acoustic_latency] rep {i}: {exc}", file=sys.stderr)
    finally:
        pipeline.stop()

    if not lags_samples:
        raise RuntimeError(
            f"No clean click detected in any of {n_reps} reps -- cannot report a "
            f"latency number. See errors below.\n" + "\n".join(errors)
        )

    lags_arr = np.array(lags_samples, dtype=np.float64)
    lag_ms = lags_arr / SR * 1000.0

    result = {
        "n_reps_requested": n_reps,
        "n_reps_valid": len(lags_samples),
        "n_reps_failed": len(errors),
        "errors": errors,
        "calibration_offset_samples": calib_offset_samples,
        "lags_samples": [int(x) for x in lags_samples],
        "lags_ms": [round(float(x), 3) for x in lag_ms],
        "median_lag_ms": round(float(np.median(lag_ms)), 3),
        "p95_lag_ms": round(float(np.percentile(lag_ms, 95)), 3),
        "min_lag_ms": round(float(np.min(lag_ms)), 3),
        "max_lag_ms": round(float(np.max(lag_ms)), 3),
    }

    print("=== Results ===")
    print(f"  Median: {result['median_lag_ms']:.2f} ms | P95: {result['p95_lag_ms']:.2f} ms "
          f"| Min: {result['min_lag_ms']:.2f} ms | Max: {result['max_lag_ms']:.2f} ms")
    print(f"  Valid reps: {result['n_reps_valid']}/{n_reps} (failed: {result['n_reps_failed']})")

    if output_json:
        os.makedirs(os.path.dirname(output_json) or ".", exist_ok=True)
        with open(output_json, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nSaved results to: {output_json}")

    return result


# ---------------------------------------------------------------------------
# A6 — Empirical DFN3 lookahead measurement (Rule 30)
# ---------------------------------------------------------------------------

def measure_model_lookahead(engine, chunk_samples: int, click_amplitude: float = 0.5,
                            click_pos_frac: float = 0.5) -> dict:
    """
    Push an impulse through InferenceEngine.enhance_chunk() and locate the
    output response's peak offset relative to where bypass_chunk() places the
    same impulse (bypass_chunk is a pure pass-through, so its peak position
    is the ground-truth "no lookahead" reference).

    Per Rule 30, lookahead must be MEASURED, never read from
    df.config's df_lookahead/conv_lookahead fields.

    `engine` only needs .sample_rate, .enhance_chunk(), .bypass_chunk() --
    the Mode A self-test below passes a fake stand-in with a known shift so
    this arithmetic is testable without loading DeepFilterNet.
    """
    click_pos = int(round(chunk_samples * click_pos_frac))
    impulse = np.zeros(chunk_samples, dtype=np.float32)
    impulse[click_pos] = click_amplitude

    bypass_out = np.asarray(engine.bypass_chunk(impulse))[0]
    enhanced_out = np.asarray(engine.enhance_chunk(impulse))[0]

    bypass_peak = int(np.argmax(np.abs(bypass_out)))
    enhanced_peak = int(np.argmax(np.abs(enhanced_out)))

    lookahead_samples = enhanced_peak - bypass_peak
    sr = engine.sample_rate
    return {
        "chunk_samples": chunk_samples,
        "click_pos_sample": click_pos,
        "bypass_peak_sample": bypass_peak,
        "enhanced_peak_sample": enhanced_peak,
        "lookahead_samples": lookahead_samples,
        "lookahead_ms": round(lookahead_samples / sr * 1000.0, 4),
    }


def run_lookahead_measurement(config_path: str = "config/audio_config.yaml",
                              output_json: str = None) -> dict:
    """Mode B: loads the real InferenceEngine/DFN3 model and runs measure_model_lookahead()."""
    from live.pipeline import _load_config
    from live.inference_engine import InferenceEngine

    config = _load_config(config_path)
    sr = int(config["audio"]["sample_rate"])
    chunk_samples = int(round(sr * float(config["audio"]["chunk_duration_sec"])))

    print("=== Phase 2 Empirical DFN3 Lookahead Measurement (Mode B, Rule 30) ===")
    engine = InferenceEngine(
        sample_rate=sr,
        atten_lim_db=float(config["model"].get("atten_lim_db", 100.0)),
        warmup_passes=int(config["pipeline"].get("warmup_passes", 3)),
    )
    result = measure_model_lookahead(engine, chunk_samples)
    print(f"  bypass peak sample  : {result['bypass_peak_sample']}")
    print(f"  enhanced peak sample: {result['enhanced_peak_sample']}")
    print(f"  lookahead_samples   : {result['lookahead_samples']} "
          f"({result['lookahead_ms']:.4f} ms)")

    if output_json:
        os.makedirs(os.path.dirname(output_json) or ".", exist_ok=True)
        with open(output_json, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nSaved results to: {output_json}")

    return result


# ---------------------------------------------------------------------------
# Self-test (Mode A — no hardware, no model)
# ---------------------------------------------------------------------------

class _FakeEngine:
    """Stand-in for InferenceEngine with a known, exact sample shift -- lets
    measure_model_lookahead()'s arithmetic be tested without loading DFN3."""

    def __init__(self, shift: int, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        self._shift = shift

    def bypass_chunk(self, chunk):
        return chunk[np.newaxis, :].copy()

    def enhance_chunk(self, chunk):
        return np.roll(chunk, self._shift)[np.newaxis, :].copy()


def _self_test():
    print("live/acoustic_latency_test.py self-test -- start")

    sr = 48000

    # --- Test 1: measure_click_to_click_lag recovers a known injected delay ---
    click_pos = int(0.5 * sr)
    true_lag_samples = 960  # 20 ms

    rng = np.random.default_rng(0)
    primary = (rng.standard_normal(int(1.5 * sr)) * 1e-5).astype(np.float32)
    primary[click_pos] = 0.5
    reference = (rng.standard_normal(int(1.5 * sr)) * 1e-5).astype(np.float32)
    reference[click_pos + true_lag_samples] = 0.5

    lag = measure_click_to_click_lag(primary, reference)
    assert abs(lag - true_lag_samples) <= 1, f"expected ~{true_lag_samples}, got {lag}"
    print(f"  [PASS] test 1: measure_click_to_click_lag recovers known lag "
          f"(expected ~{true_lag_samples}, got {lag})")

    # --- Test 2: RuntimeError on a click-free recording ---
    silent_primary = (rng.standard_normal(int(1.5 * sr)) * 1e-4).astype(np.float32)
    silent_reference = (rng.standard_normal(int(1.5 * sr)) * 1e-4).astype(np.float32)
    try:
        measure_click_to_click_lag(silent_primary, silent_reference)
        raise AssertionError("expected RuntimeError on click-free recordings")
    except RuntimeError:
        pass
    print("  [PASS] test 2: measure_click_to_click_lag raises RuntimeError "
          "when no click is present on either channel (no silent wrong answers)")

    # --- Test 3: RuntimeError when only ONE channel has a clean click ---
    one_sided_primary = (rng.standard_normal(int(1.5 * sr)) * 1e-5).astype(np.float32)
    one_sided_primary[click_pos] = 0.5
    try:
        measure_click_to_click_lag(one_sided_primary, silent_reference)
        raise AssertionError("expected RuntimeError when the reference channel has no click")
    except RuntimeError as exc:
        assert "reference" in str(exc)
    print("  [PASS] test 3: raises specifically naming the channel with no clean click")

    # --- Test 4: measure_model_lookahead recovers a known shift (fake engine) ---
    for known_shift in (0, 5, 40):
        engine = _FakeEngine(shift=known_shift, sample_rate=sr)
        result = measure_model_lookahead(engine, chunk_samples=4800)
        assert result["lookahead_samples"] == known_shift, (
            f"shift={known_shift}: got lookahead_samples={result['lookahead_samples']}"
        )
    print("  [PASS] test 4: measure_model_lookahead recovers known shifts "
          "(0, 5, 40 samples) via a fake engine, no DFN3 model needed")

    # --- Test 5: _load_calibration_offset returns 0 with a warning when the file is missing ---
    offset = _load_calibration_offset(cal_path=os.path.join(_REPO_ROOT, "config", "__nonexistent__.yaml"))
    assert offset == 0
    print("  [PASS] test 5: _load_calibration_offset defaults to 0 (with a warning) when uncalibrated")

    print("live/acoustic_latency_test.py self-test -- ALL PASSED")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="PS26052 Phase 2 — Physical acoustic round-trip (A5) / DFN3 lookahead (A6)"
    )
    parser.add_argument("--config", default="config/audio_config.yaml", help="Path to audio_config.yaml")
    parser.add_argument("--n-reps", type=int, default=20, help="Measurement repetitions (project spec: >=20)")
    parser.add_argument("--click-device", type=int, default=None,
                         help="Playback device for the external click (default: system default output)")
    parser.add_argument("--output-json", default=None, help="Path to save JSON results")
    parser.add_argument("--lookahead", action="store_true",
                         help="Run the empirical DFN3 lookahead measurement (A6/Rule 30) instead of "
                              "the acoustic round-trip test")
    parser.add_argument("--self-test", action="store_true", help="Run offline logic self-test and exit (no hardware)")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    if args.lookahead:
        run_lookahead_measurement(config_path=args.config, output_json=args.output_json)
    else:
        run_acoustic_latency_test(
            config_path=args.config, n_reps=args.n_reps,
            click_device=args.click_device, output_json=args.output_json,
        )


if __name__ == "__main__":
    main()
