"""
live/calibrate_mic_pair.py — Mic-pair delay calibration (Phase 1).

Measures the sample-level delay between a primary mic and a reference mic on
two separate USB devices (Topology B).  Writes the result to
config/mic_calibration.yaml so live/pipeline.py can compensate.

How it works
------------
1. Play a short logarithmic chirp through the speaker so both microphones
   pick up the same stimulus (requires both mics to be within earshot of the
   speaker — move them close for calibration, then back to final positions).
2. Cross-correlate the two recordings to find the time offset where they align.
3. Write ref_delay_samples = -lag to config/mic_calibration.yaml.

If ref_delay_samples > 0: reference is ahead of primary by that many samples;
    the pipeline delays the reference channel by that amount before feeding NLMS.
If ref_delay_samples < 0: primary is ahead of reference; the pipeline delays
    the primary side instead (unusual — verify the device wiring).
If ref_delay_samples == 0: already aligned (or no chirp was heard by either mic).

Usage
-----
    # Default — plays chirp, uses devices from config/audio_config.yaml:
    python live/calibrate_mic_pair.py

    # Specify devices and output device explicitly:
    python live/calibrate_mic_pair.py \\
        --primary-device 1 --reference-device 2 --output-device 0

    # Skip playback (rely on ambient noise correlation — less reliable):
    python live/calibrate_mic_pair.py --no-playback

    # Dry-run mode A self-test (no hardware):
    python live/calibrate_mic_pair.py --self-test

After calibration, update config/audio_config.yaml:
    audio:
      dual_mic:
        ref_delay_samples: <value from calibration>
"""

import os
import sys
import time
import argparse
import threading
import json
import numpy as np

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    import sounddevice as sd
except ImportError:
    print("[calibrate] sounddevice not installed.  Run: pip install sounddevice",
          file=sys.stderr)
    sys.exit(1)

CAL_YAML = os.path.join(_REPO_ROOT, "config", "mic_calibration.yaml")
CONFIG_YAML = os.path.join(_REPO_ROOT, "config", "audio_config.yaml")

SR = 48000
RECORD_DURATION = 3.0   # seconds
CHIRP_DURATION = 2.0    # seconds (chirp inside the record window)
CHIRP_F0 = 200.0        # Hz
CHIRP_F1 = 6000.0       # Hz
CHIRP_AMPLITUDE = 0.25  # linear (avoid clipping)


def _make_chirp(sr: int, duration: float, f0: float, f1: float,
                amplitude: float) -> np.ndarray:
    """Logarithmic chirp from f0 to f1, shape (n,) float32."""
    t = np.linspace(0.0, duration, int(sr * duration), endpoint=False)
    log_ratio = np.log(f1 / f0)
    phase = 2.0 * np.pi * f0 * duration / log_ratio * (np.exp(t / duration * log_ratio) - 1.0)
    sig = amplitude * np.sin(phase)
    # Fade in/out 10 ms to avoid click.
    fade_n = int(0.01 * sr)
    win = np.ones(len(sig))
    win[:fade_n] = np.linspace(0.0, 1.0, fade_n)
    win[-fade_n:] = np.linspace(1.0, 0.0, fade_n)
    return (sig * win).astype(np.float32)


def record_both(primary_device, reference_device, sr: int,
                duration: float, play_signal=None, output_device=None):
    """
    Record `duration` seconds from primary and reference mics simultaneously.
    If `play_signal` is provided, play it through `output_device` at the same
    time (starts 200 ms after recording begins so both mics capture the onset).

    Returns (primary_mono, reference_mono) as 1-D float32 arrays of length
    `int(sr * duration)`.  Samples recorded past the buffer are dropped.
    """
    n = int(sr * duration)
    primary_buf = np.zeros(n, dtype=np.float32)
    ref_buf = np.zeros(n, dtype=np.float32)
    primary_pos = [0]
    ref_pos = [0]
    lock = threading.Lock()

    def _primary_cb(indata, frames, time_info, status):
        if status:
            print(f"[calibrate] primary status: {status}", file=sys.stderr)
        with lock:
            end = min(primary_pos[0] + frames, n)
            count = end - primary_pos[0]
            if count > 0:
                primary_buf[primary_pos[0]:end] = indata[:count, 0]
                primary_pos[0] = end

    def _ref_cb(indata, frames, time_info, status):
        if status:
            print(f"[calibrate] reference status: {status}", file=sys.stderr)
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
            if play_signal is not None and output_device is not None:
                time.sleep(0.2)  # let both input streams stabilise first
                sd.play(play_signal, samplerate=sr, device=output_device, blocking=False)
            time.sleep(duration + 0.2)

    return primary_buf, ref_buf


def compute_delay(primary: np.ndarray, reference: np.ndarray,
                  max_lag_samples: int = 4800) -> int:
    """
    Cross-correlate primary and reference to find the integer sample delay.

    Returns ref_delay_samples:
      > 0  → reference is this many samples AHEAD of primary;
             pipeline should delay reference by this amount.
      < 0  → reference is behind primary (unusual).
      = 0  → no detectable offset.

    Only lags within ±max_lag_samples are searched (default ±100 ms at 48 kHz).
    """
    # Normalise to prevent amplitude differences from biasing the peak.
    p = primary - np.mean(primary)
    r = reference - np.mean(reference)
    p_rms = np.sqrt(np.mean(p ** 2))
    r_rms = np.sqrt(np.mean(r ** 2))
    if p_rms < 1e-6 or r_rms < 1e-6:
        print("[calibrate] WARNING: one or both mic signals are nearly silent. "
              "Delay estimate will be unreliable.  Ensure both mics are recording "
              "and the chirp is audible.", file=sys.stderr)
        return 0
    p /= p_rms
    r /= r_rms

    # Full cross-correlation then restrict to ±max_lag_samples.
    corr = np.correlate(p, r, mode="full")
    center = len(r) - 1
    lo = max(0, center - max_lag_samples)
    hi = min(len(corr), center + max_lag_samples + 1)
    peak_idx = lo + int(np.argmax(np.abs(corr[lo:hi])))
    lag = peak_idx - center
    # lag > 0: p[n] correlates with r[n - lag] → r leads by lag (r is ahead)
    # ref_delay_samples = lag means "delay reference by lag samples"
    return lag


def write_calibration_yaml(ref_delay_samples: int, primary_device,
                            reference_device, output_path: str = CAL_YAML):
    """Write calibration result to a machine-owned YAML file."""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    content = f"""\
# config/mic_calibration.yaml
# Machine-written by live/calibrate_mic_pair.py -- DO NOT edit by hand.
# Human-readable context lives in config/audio_config.yaml (dual_mic section).
# Run live/calibrate_mic_pair.py again to update after re-plugging devices.

calibrated_at: "{ts}"
primary_device: {primary_device}
reference_device: {reference_device}
ref_delay_samples: {ref_delay_samples}
# ref_delay_samples > 0: reference is ahead; pipeline delays reference channel.
# ref_delay_samples < 0: primary is ahead; pipeline delays primary channel.
# Drift note: Topology B (two USB devices) drifts ~2.4 samples/sec at 50 ppm.
# For sessions >30 s, consider re-calibrating or keeping sessions short.
"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(content)
    print(f"[calibrate] Wrote calibration to: {output_path}")


def _load_devices_from_config(config_path: str):
    """Return (primary_device, reference_device, output_device) from config."""
    primary_device, reference_device, output_device = None, None, None
    try:
        import yaml
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)
        audio = cfg.get("audio", {})
        primary_device = audio.get("input_device", None)
        dual = audio.get("dual_mic", {})
        reference_device = dual.get("reference_device", None)
        output_device = audio.get("output_device", None)
    except Exception as e:
        print(f"[calibrate] Could not read {config_path}: {e}", file=sys.stderr)
    return primary_device, reference_device, output_device


def run_calibration(primary_device, reference_device, output_device,
                    no_playback: bool, output_yaml: str = CAL_YAML):
    """Full calibration flow. Returns ref_delay_samples."""
    print("=== Mic Pair Calibration (Phase 1) ===")
    print(f"Primary device  : {primary_device}")
    print(f"Reference device: {reference_device}")
    print(f"Output device   : {output_device}")
    print(f"Record duration : {RECORD_DURATION} s")
    print()

    play_signal = None
    if not no_playback:
        if output_device is None:
            print("[calibrate] WARNING: no output device specified; "
                  "cannot play chirp.  Proceeding without playback.", file=sys.stderr)
        else:
            chirp = _make_chirp(SR, CHIRP_DURATION, CHIRP_F0, CHIRP_F1, CHIRP_AMPLITUDE)
            # Pad to full record duration with silence
            n_total = int(SR * RECORD_DURATION)
            play_signal = np.zeros(n_total, dtype=np.float32)
            play_signal[:len(chirp)] = chirp
            print("Will play a logarithmic chirp (200 Hz → 6 kHz) while recording.")
            print("Position both mics so they can both hear the speaker.")
            print()

    print(f"Recording for {RECORD_DURATION} s...")
    primary_buf, ref_buf = record_both(
        primary_device, reference_device, SR, RECORD_DURATION,
        play_signal=play_signal, output_device=output_device,
    )
    print("Recording complete.")

    p_rms = float(np.sqrt(np.mean(primary_buf ** 2)))
    r_rms = float(np.sqrt(np.mean(ref_buf ** 2)))
    print(f"Primary RMS  : {p_rms:.5f}")
    print(f"Reference RMS: {r_rms:.5f}")

    ref_delay = compute_delay(primary_buf, ref_buf)
    delay_ms = ref_delay / SR * 1000.0

    print()
    print(f"Measured ref_delay_samples: {ref_delay}  ({delay_ms:.2f} ms)")
    if ref_delay > 0:
        print(f"  → Reference is {delay_ms:.2f} ms AHEAD of primary.")
        print(f"    Pipeline will delay reference by {ref_delay} samples to align.")
    elif ref_delay < 0:
        print(f"  → Reference is {-delay_ms:.2f} ms BEHIND primary.")
        print(f"    Pipeline will delay primary by {-ref_delay} samples to align.")
    else:
        print("  → No detectable offset (or silent recording).")

    write_calibration_yaml(ref_delay, primary_device, reference_device, output_yaml)

    print()
    print("Next step: update config/audio_config.yaml:")
    print("  audio:")
    print("    dual_mic:")
    print(f"      ref_delay_samples: {ref_delay}")
    print()

    return ref_delay


# ---------------------------------------------------------------------------
# Self-test (Mode A — no hardware)
# ---------------------------------------------------------------------------

def _self_test():
    print("live/calibrate_mic_pair.py self-test -- start")

    sr = 48000
    n = int(sr * 3.0)

    # --- Test 1: chirp generation is correct shape and bounded ---
    chirp = _make_chirp(sr, 2.0, 200.0, 6000.0, 0.25)
    assert chirp.dtype == np.float32
    assert len(chirp) == int(sr * 2.0)
    assert np.max(np.abs(chirp)) <= 0.26, "chirp amplitude exceeds limit"
    print(f"  [PASS] test 1: chirp shape={chirp.shape}, max_amp={np.max(np.abs(chirp)):.3f}")

    # --- Test 2: compute_delay finds a known synthetic offset ---
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(n).astype(np.float32)
    KNOWN_DELAY = 120  # reference is 120 samples AHEAD of primary
    # Reference is D samples ahead: reference[n] = noise[n+D], primary[n] = noise[n]
    # → primary[n] = reference[n - D], so correlation peak at lag = D.
    reference = noise[KNOWN_DELAY:]
    primary = noise[:len(reference)]
    lag = compute_delay(primary, reference, max_lag_samples=4800)
    # Allow ±1 sample for numerical reasons
    assert abs(lag - KNOWN_DELAY) <= 1, (
        f"compute_delay returned {lag}, expected ~{KNOWN_DELAY}"
    )
    print(f"  [PASS] test 2: compute_delay found lag={lag} (expected ~{KNOWN_DELAY})")

    # --- Test 3: compute_delay handles nearly-silent inputs gracefully ---
    silent = np.zeros(n, dtype=np.float32)
    lag_sil = compute_delay(silent, silent)
    assert lag_sil == 0, f"silent input should return 0, got {lag_sil}"
    print("  [PASS] test 3: silent input handled gracefully (lag=0)")

    # --- Test 4: write/read calibration YAML round-trip ---
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        tmp_path = f.name
    try:
        write_calibration_yaml(120, 1, 2, output_path=tmp_path)
        assert os.path.exists(tmp_path)
        with open(tmp_path, "r") as f:
            content = f.read()
        assert "ref_delay_samples: 120" in content
        assert "primary_device: 1" in content
        assert "reference_device: 2" in content
        print("  [PASS] test 4: calibration YAML written and verifiable")
    finally:
        os.unlink(tmp_path)

    print("live/calibrate_mic_pair.py self-test -- ALL PASSED")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Measure and record primary/reference mic pair delay"
    )
    parser.add_argument("--primary-device", type=int, default=None,
                        help="Primary mic device index (default: from audio_config.yaml)")
    parser.add_argument("--reference-device", type=int, default=None,
                        help="Reference mic device index (default: from audio_config.yaml)")
    parser.add_argument("--output-device", type=int, default=None,
                        help="Speaker device index for chirp playback (default: from config)")
    parser.add_argument("--no-playback", action="store_true",
                        help="Skip chirp playback; rely on ambient noise correlation")
    parser.add_argument("--output-yaml", default=CAL_YAML,
                        help=f"Where to write calibration result (default: {CAL_YAML})")
    parser.add_argument("--self-test", action="store_true",
                        help="Run Mode A self-test (no hardware) and exit")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    # Load defaults from config if device args not given.
    cfg_primary, cfg_ref, cfg_out = _load_devices_from_config(CONFIG_YAML)
    primary_device = args.primary_device if args.primary_device is not None else cfg_primary
    reference_device = args.reference_device if args.reference_device is not None else cfg_ref
    output_device = args.output_device if args.output_device is not None else cfg_out

    if primary_device is None or reference_device is None:
        print("[calibrate] ERROR: could not determine primary or reference device.", file=sys.stderr)
        print("  Run `python live/main.py detect` to list devices, then pass:", file=sys.stderr)
        print("  --primary-device <N> --reference-device <M>", file=sys.stderr)
        sys.exit(1)

    run_calibration(primary_device, reference_device, output_device,
                    no_playback=args.no_playback, output_yaml=args.output_yaml)


if __name__ == "__main__":
    main()
