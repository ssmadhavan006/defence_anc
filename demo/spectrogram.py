"""
demo/spectrogram.py — Live terminal waterfall spectrogram: raw mic input vs
DeepFilterNet-enhanced output, side by side, updating in real time.

This is the visual centerpiece for the judged demo: results/results.csv shows
DeepFilterNet suppresses broadband noise energy while preserving the speech
band, but a table doesn't sell that. This renders it directly — the BEFORE
panel stays lit up across the spectrum under noise, the AFTER panel goes dark
except where speech energy actually is.

Pure ANSI terminal output (no GUI/X11), so it runs the same over SSH on the
Pi as it does locally — matching how demo/dashboard.py already works.

Both panels share one auto-gain reference driven by the BEFORE (raw) signal,
so the AFTER panel visibly darkens when DeepFilterNet suppresses energy
instead of independently re-normalizing to look equally "loud" either way.

Controls:
    'b' -> toggle ENHANCE / BYPASS (AFTER panel goes flat like BEFORE)
    'q' -> quit

Usage:
    python demo/spectrogram.py
    python demo/spectrogram.py --config config/audio_config.yaml

Self-test (no audio hardware required):
    python demo/spectrogram.py --self-test
"""

import os
import sys
import time
import collections
import numpy as np

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# Rendering config
# ---------------------------------------------------------------------------
FREQ_BINS = 64            # columns per panel (log-spaced 50 Hz .. MAX_HZ)
HISTORY_ROWS = 14         # rows (time) per panel waterfall
MAX_HZ = 8000.0           # speech-relevant band (DFN3 runs at 48 kHz internally)
MIN_HZ = 50.0
REFRESH_SEC = 0.12
DYNAMIC_RANGE_DB = 50.0

RESET = "\033[0m"
CLEAR = "\033[H\033[J"
BOLD = "\033[1m"

# 5-level shading ramp: (char, ANSI 256-color code or None for reset/space)
_LEVELS = [
    (" ", None),
    ("░", 33),    # ░ blue
    ("▒", 51),    # ▒ cyan
    ("▓", 226),   # ▓ yellow
    ("█", 196),   # █ red
]


def _mag_to_level(norm: float) -> int:
    norm = 0.0 if norm < 0.0 else (1.0 if norm > 1.0 else norm)
    return int(norm * (len(_LEVELS) - 1) + 0.5)


# Cache of per-(n, sr, n_bins, min_hz, max_hz) precomputed binning tables.
# In practice this holds 1-2 entries for the life of a process (one chunk
# size, one sample rate), so it is not a growth risk.
_BIN_CACHE = {}


def _spectrum_bins(n: int, sr: int, n_bins: int, min_hz: float, max_hz: float):
    """
    Precompute (and cache) everything about the log-spaced binning that
    doesn't depend on the audio itself: the Hann window, which FFT bins fall
    inside the display range, each one's band index, and the per-band bin
    counts.

    Why this exists: the previous implementation rebuilt the window, the
    freq axis and the band edges on EVERY call, then ran a 64-iteration
    Python loop that allocated ~5 temporaries per band over a 2401-element
    array (~320 numpy dispatches per call). Cheap on a dev x86, but on the
    Pi -- called several times a second, from threads competing with the
    real-time inference thread for the GIL -- it was enough to cause audible
    breakup in the live pipeline (observed on Pi 5, 2026-09-05).
    """
    key = (n, sr, n_bins, min_hz, max_hz)
    cached = _BIN_CACHE.get(key)
    if cached is not None:
        return cached

    window = np.hanning(n)
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    edges = np.geomspace(min_hz, max_hz, n_bins + 1)
    # Band index per FFT bin such that edges[i] <= f < edges[i+1]; -1 or
    # n_bins for bins outside the displayed range (dropped below). This
    # reproduces the old `(freqs >= edges[i]) & (freqs < edges[i+1])` mask
    # semantics exactly, including excluding f == max_hz.
    idx = np.searchsorted(edges, freqs, side="right") - 1
    in_range = (idx >= 0) & (idx < n_bins)
    band_idx = idx[in_range].astype(np.intp)
    counts = np.bincount(band_idx, minlength=n_bins).astype(np.float64)

    cached = (window, in_range, band_idx, counts)
    _BIN_CACHE[key] = cached
    return cached


def _spectrum_db(chunk: np.ndarray, sr: int, n_bins: int, min_hz: float, max_hz: float) -> np.ndarray:
    """Log-binned magnitude spectrum in dB, shape (n_bins,)."""
    n = len(chunk)
    if n == 0:
        return np.full(n_bins, -100.0)
    window, in_range, band_idx, counts = _spectrum_bins(n, sr, n_bins, min_hz, max_hz)
    spec = np.abs(np.fft.rfft(chunk * window))
    sums = np.bincount(band_idx, weights=spec[in_range], minlength=n_bins)
    # Mean magnitude per band; empty bands fall back to 1e-8 as before.
    out = np.where(counts > 0.0, sums / np.maximum(counts, 1.0), 1e-8)
    return 20.0 * np.log10(out + 1e-8)


class _AutoGain:
    """Self-calibrating peak reference so the display needs no manual gain
    tuning at demo time, regardless of mic sensitivity or room volume."""

    def __init__(self, dynamic_range_db: float = DYNAMIC_RANGE_DB,
                 attack: float = 0.5, release: float = 0.02, init_db: float = -50.0):
        self.dynamic_range_db = dynamic_range_db
        self.attack = attack
        self.release = release
        self.ref_db = init_db

    def update(self, db_row: np.ndarray) -> None:
        peak = float(np.max(db_row)) if db_row.size else self.ref_db
        rate = self.attack if peak > self.ref_db else self.release
        self.ref_db += (peak - self.ref_db) * rate

    def apply(self, db_row: np.ndarray) -> np.ndarray:
        floor = self.ref_db - self.dynamic_range_db
        norm = (db_row - floor) / self.dynamic_range_db
        return np.clip(norm, 0.0, 1.0)


def _render_panel(title: str, history: "collections.deque[np.ndarray]", width: int) -> list:
    lines = [f"{BOLD}{title}{RESET}"]
    for row in history:
        chars = []
        for v in row:
            idx = _mag_to_level(v)
            ch, color = _LEVELS[idx]
            chars.append(ch if color is None else f"\033[38;5;{color}m{ch}{RESET}")
        lines.append("".join(chars))
    while len(lines) - 1 < HISTORY_ROWS:
        lines.append(" " * width)
    return lines


def run_spectrogram(config_path: str):
    from live.pipeline import LivePipeline, _load_config
    from demo.dashboard import KeyListener

    config = _load_config(config_path)
    config["pipeline"]["log_timing"] = False
    pipeline = LivePipeline(config)

    print("Initializing spectrogram demo and loading model...", flush=True)
    pipeline.start()

    before_hist = collections.deque(maxlen=HISTORY_ROWS)
    after_hist = collections.deque(maxlen=HISTORY_ROWS)
    gain = _AutoGain()

    running = True
    start_time = time.time()
    print(CLEAR, end="")

    try:
        with KeyListener() as listener:
            while running:
                key = listener.get_key()
                if key == "q":
                    running = False
                    break
                elif key == "b":
                    pipeline._mode = "bypass" if pipeline._mode == "enhance" else "enhance"

                in_chunk = pipeline.last_in_chunk
                out_chunk = pipeline.last_out_chunk
                sr = pipeline._sr

                if in_chunk is not None:
                    before_db = _spectrum_db(in_chunk, sr, FREQ_BINS, MIN_HZ, MAX_HZ)
                    gain.update(before_db)
                    before_hist.append(gain.apply(before_db))
                if out_chunk is not None:
                    after_db = _spectrum_db(out_chunk, sr, FREQ_BINS, MIN_HZ, MAX_HZ)
                    after_hist.append(gain.apply(after_db))

                mode_disp = "ENHANCE" if pipeline._mode == "enhance" else "BYPASS"
                elapsed = time.time() - start_time

                lines = [
                    f"{BOLD}{'=' * 64}{RESET}",
                    f"{BOLD}  PS26052 Live Spectrogram — Mode: {mode_disp}  ({int(elapsed)}s){RESET}",
                    "  Press 'b' to toggle ENHANCE/BYPASS, 'q' to quit",
                    f"{BOLD}{'=' * 64}{RESET}",
                    "",
                ]
                lines.extend(_render_panel(f"BEFORE (raw mic, {int(MIN_HZ)}-{int(MAX_HZ)} Hz)", before_hist, FREQ_BINS))
                lines.append("")
                lines.extend(_render_panel("AFTER  (DeepFilterNet output)", after_hist, FREQ_BINS))

                sys.stdout.write("\033[H" + "\n".join(lines) + "\n")
                sys.stdout.flush()
                time.sleep(REFRESH_SEC)
    finally:
        print("\nStopping audio stream and shutting down...", flush=True)
        pipeline.stop()
        print("Spectrogram demo stopped. Clean exit.", flush=True)


def _self_test():
    """Mode A test: exercise the DSP/rendering path with synthetic audio,
    no sounddevice hardware or model load required."""
    print("spectrogram.py self-test -- start")
    sr = 48000
    n = 4800
    t = np.arange(n) / sr

    # BEFORE: broadband noise + a 300 Hz speech-like tone.
    rng = np.random.default_rng(0)
    noisy = 0.4 * rng.standard_normal(n) + 0.3 * np.sin(2 * np.pi * 300 * t)
    # AFTER: same tone, noise suppressed (simulates enhancement).
    clean = 0.3 * np.sin(2 * np.pi * 300 * t)

    db_noisy = _spectrum_db(noisy, sr, FREQ_BINS, MIN_HZ, MAX_HZ)
    db_clean = _spectrum_db(clean, sr, FREQ_BINS, MIN_HZ, MAX_HZ)
    assert db_noisy.shape == (FREQ_BINS,), "wrong bin count"
    assert np.all(np.isfinite(db_noisy)), "non-finite dB values"
    print("  [PASS] test 1: _spectrum_db shape and finiteness")

    # --- Test 1b: the cached/vectorised binning is numerically IDENTICAL to
    # the original per-band Python-loop implementation it replaced. This is
    # the guard that the Pi performance fix didn't quietly change what the
    # display (or live/stage_metrics.py's suppression map) actually measures.
    def _spectrum_db_reference(chunk, sr_, n_bins, min_hz, max_hz):
        n = len(chunk)
        if n == 0:
            return np.full(n_bins, -100.0)
        window = np.hanning(n)
        spec = np.abs(np.fft.rfft(chunk * window))
        freqs = np.fft.rfftfreq(n, d=1.0 / sr_)
        edges = np.geomspace(min_hz, max_hz, n_bins + 1)
        out = np.empty(n_bins)
        for i in range(n_bins):
            mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
            out[i] = spec[mask].mean() if mask.any() else 1e-8
        return 20.0 * np.log10(out + 1e-8)

    for name, sig in (("noisy", noisy), ("clean", clean)):
        ref = _spectrum_db_reference(sig, sr, FREQ_BINS, MIN_HZ, MAX_HZ)
        got = _spectrum_db(sig, sr, FREQ_BINS, MIN_HZ, MAX_HZ)
        assert np.allclose(ref, got, rtol=1e-9, atol=1e-9), (
            f"{name}: vectorised _spectrum_db diverged from the reference "
            f"implementation (max abs diff {np.max(np.abs(ref - got)):.3e})"
        )
    print("  [PASS] test 1b: vectorised _spectrum_db matches the original "
          "per-band loop implementation to within 1e-9")

    gain = _AutoGain()
    gain.update(db_noisy)
    norm_noisy = gain.apply(db_noisy)
    norm_clean = gain.apply(db_clean)
    assert norm_noisy.min() >= 0.0 and norm_noisy.max() <= 1.0
    assert norm_clean.mean() < norm_noisy.mean(), "suppressed signal should read quieter under shared gain"
    print(f"  [PASS] test 2: shared auto-gain shows suppression "
          f"(before_mean={norm_noisy.mean():.3f}, after_mean={norm_clean.mean():.3f})")

    hist = collections.deque(maxlen=HISTORY_ROWS)
    hist.append(norm_noisy)
    hist.append(norm_clean)
    panel = _render_panel("TEST", hist, FREQ_BINS)
    assert len(panel) == HISTORY_ROWS + 1, "panel row count mismatch"
    print("  [PASS] test 3: _render_panel produces correct row count")

    for v in (0.0, 0.5, 1.0, -1.0, 2.0):
        idx = _mag_to_level(v)
        assert 0 <= idx < len(_LEVELS)
    print("  [PASS] test 4: _mag_to_level clamps out-of-range input")

    print("spectrogram.py self-test -- ALL PASSED")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="PS26052 Phase 5 — Live terminal spectrogram demo")
    parser.add_argument("--config", default="config/audio_config.yaml")
    parser.add_argument("--self-test", action="store_true", help="Run offline DSP/render self-test and exit")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    run_spectrogram(args.config)


if __name__ == "__main__":
    main()
