"""
live/stage_metrics.py — Dashboard metrics engine (background thread).

Computes two families of numbers from live/stage_taps.py's per-stage chunks,
never on the audio path (same discipline as models/dnsmos/dnsmos_infer.py and
models/noise_classifier/classify_chunk.py):

  1. Always available, non-intrusive (no clean reference needed):
       - per-stage RMS level (dBFS) from whichever taps are populated this
         session (capture/pre_filter/dfn_core/residual/output)
       - a 64-band log-spaced "measured per-band suppression" spectrum,
         capture vs output -- reuses demo/spectrogram.py's own _spectrum_db
         so the dashboard's heatmap and the terminal spectrogram agree on
         exactly the same DSP.

  2. Only available in reference-replay mode (pipeline.reference_available):
       true SI-SNR / STOI / PESQ-WB via eval/metrics.py, computed over a
       sliding window (window_sec, default 3.0s -- comfortably above STOI's
       ~384ms minimum and long enough for PESQ-WB to be stable).

Why this needs its own thread and can't just run inline in the WebSocket
loop (demo/webdash/app.py, 4 Hz): STOI is a Python/C hybrid that resamples
48k->10k internally, and PESQ-WB is a C extension that resamples 48k->16k
per call -- both take single-digit-to-tens of milliseconds, which is fine at
this thread's ~1 Hz cadence but would eat directly into the 250ms WebSocket
budget if run there.

Continuous accumulation, not sampled snapshots: the reference-mode buffers
are filled by POLLING pipeline.stage_taps.output faster than the pipeline's
own chunk cadence (poll_sec < chunk_sec) and appending only genuinely NEW
chunks (identity-checked against the last chunk seen) -- unlike a naive
"read whatever's there every N seconds" loop, this guarantees the window is
a real contiguous slice of audio, not disjoint snippets spaced by the poll
interval.

Self-test (Mode A -- no audio hardware, no real pipeline):
    python live/stage_metrics.py --self-test
"""

import os
import sys
import threading
import time

import numpy as np

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from demo.spectrogram import _spectrum_db, _AutoGain, FREQ_BINS, MIN_HZ, MAX_HZ
from live.stage_taps import STAGE_NAMES
from eval.metrics import compute_si_snr, compute_stoi, compute_pesq_wb


def _rms_db(chunk) -> float:
    if chunk is None or len(chunk) == 0:
        return -96.0
    arr = np.asarray(chunk, dtype=np.float32)
    rms = float(np.sqrt(np.mean(arr ** 2)))
    return 20.0 * float(np.log10(max(rms, 1e-8)))


def compute_suppression_db(before: np.ndarray, after: np.ndarray, sr: int,
                            n_bins: int = FREQ_BINS, min_hz: float = MIN_HZ,
                            max_hz: float = MAX_HZ) -> np.ndarray:
    """
    Measured per-band gain: 20*log10(|after|) - 20*log10(|before|) in each of
    n_bins log-spaced bands. Negative = suppressed, ~0 = passed through,
    positive = amplified. This is a DIRECT MEASUREMENT of the two tapped
    signals, not DeepFilterNet3's internal ERB mask (see D7 in the dashboard
    plan for why those are different objects) -- label it as such in the UI.
    """
    before_db = _spectrum_db(before, sr, n_bins, min_hz, max_hz)
    after_db = _spectrum_db(after, sr, n_bins, min_hz, max_hz)
    return after_db - before_db


class StageMetrics:
    """
    Background thread. Construct with the live pipeline (or any object
    exposing .stage_taps, .current_clean_ref_chunk, .reference_available,
    ._sr, ._chunk_sec) and call start(). Read current values via snapshot().
    """

    def __init__(self, pipeline, cadence_sec: float = 1.0, window_sec: float = 3.0,
                 poll_sec: float = None, spectrum_cadence_sec: float = 0.25):
        self._pipeline = pipeline
        self._cadence_sec = cadence_sec
        self._window_sec = window_sec
        # Spectra drive the dashboard's scrolling waterfall, so they need a
        # faster cadence than the 1 Hz level/metric refresh -- but they are
        # computed HERE, once per tick, rather than once per connected
        # WebSocket client. On the Pi with 3 clients connected the old
        # per-client computation was ~24 _spectrum_db() calls/sec competing
        # with the real-time inference thread; this makes the cost constant
        # in the number of viewers (2 calls per tick, whoever is watching).
        self._spectrum_cadence_sec = spectrum_cadence_sec
        chunk_sec = float(getattr(pipeline, "_chunk_sec", 0.1) or 0.1)
        self._poll_sec = poll_sec if poll_sec is not None else max(0.01, chunk_sec / 2.0)
        self._sr = int(getattr(pipeline, "_sr", 48000) or 48000)
        # One shared auto-gain across BOTH panels, driven by the BEFORE
        # signal -- same principle as demo/spectrogram.py's terminal version,
        # so AFTER visibly darkens under suppression instead of independently
        # re-normalising to look equally loud.
        self._gain = _AutoGain()

        self._window_samples = int(round(window_sec * self._sr))
        self._out_buf = np.zeros(self._window_samples, dtype=np.float32)
        self._ref_buf = np.zeros(self._window_samples, dtype=np.float32)
        self._buf_fill = 0
        self._last_output_seen = None

        self._running = False
        self._thread = threading.Thread(target=self._loop, daemon=True, name="stage_metrics")

        # Public, JSON-safe-after-snapshot() fields. Single-assignment writes
        # only (see module docstring) -- same benign-race convention as
        # live/telemetry.py.
        self.stage_levels_db = {name: None for name in STAGE_NAMES}
        self.suppression_db = None          # list[float], capture -> output
        self.suppression_bins = FREQ_BINS
        # Quantised (uint8 0-255) display spectra, computed here once per
        # tick and read by every WebSocket client -- see __init__'s note.
        self.spectrum_before = None
        self.spectrum_after = None
        self.metrics_mode = "non_intrusive"  # or "reference_backed"
        self.si_snr = None
        self.stoi = None
        self.pesq_wb = None
        self.metrics_window_sec = None
        self.last_updated = time.monotonic()
        self._warned_missing_deps = set()

    def _warn_missing_dep_once(self, package: str, metric_name: str):
        """A missing pystoi/pesq install would otherwise silently leave
        si_snr populated but stoi/pesq_wb permanently None with zero
        diagnostic -- easy to misread as a metrics-engine bug rather than a
        missing package (this bit us finding out pesq/pystoi were never in
        requirements-optional.txt for the Pi at all -- see that file's
        dashboard-rebuild section). Warn exactly once per package, not once
        per window."""
        if package in self._warned_missing_deps:
            return
        self._warned_missing_deps.add(package)
        print(f"[stage_metrics] WARNING: {package!r} is not installed -- {metric_name} will stay "
              f"None for this whole session (not a bug, just a missing dependency). "
              f"Install it: pip install {package}", file=sys.stderr)

    def start(self):
        self._running = True
        self._thread.start()

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------
    def _update_levels(self):
        """Cheap per-stage RMS only (no FFTs) -- runs at cadence_sec."""
        taps = self._pipeline.stage_taps.snapshot()
        for name in STAGE_NAMES:
            chunk = taps.get(name)
            self.stage_levels_db[name] = round(_rms_db(chunk), 1) if chunk is not None else None

    def _update_spectra_and_suppression(self):
        """
        The only place in the whole dashboard that calls _spectrum_db().
        Computes the BEFORE/AFTER spectra ONCE, then derives both the
        suppression map and the quantised display spectra from those same
        two arrays -- so the total cost is 2 FFT+bin passes per tick no
        matter how many browsers are connected.
        """
        capture = self._pipeline.stage_taps.capture
        output = self._pipeline.stage_taps.output
        if capture is None or output is None:
            self.suppression_db = None
            self.spectrum_before = None
            self.spectrum_after = None
            return

        before_db = _spectrum_db(capture, self._sr, FREQ_BINS, MIN_HZ, MAX_HZ)
        after_db = _spectrum_db(output, self._sr, FREQ_BINS, MIN_HZ, MAX_HZ)

        self.suppression_db = np.round(after_db - before_db, 1).tolist()

        self._gain.update(before_db)
        self.spectrum_before = (self._gain.apply(before_db) * 255).astype(int).tolist()
        self.spectrum_after = (self._gain.apply(after_db) * 255).astype(int).tolist()

    def _accumulate_reference_window(self) -> bool:
        """
        Append any newly-seen output/clean-ref chunk pair into the rolling
        buffers. Returns True once the window is full (ready to score).
        """
        out_chunk = self._pipeline.stage_taps.output
        ref_chunk = getattr(self._pipeline, "current_clean_ref_chunk", None)
        if out_chunk is None or ref_chunk is None or out_chunk is self._last_output_seen:
            return False
        self._last_output_seen = out_chunk

        n = min(len(out_chunk), len(ref_chunk))
        remaining = self._window_samples - self._buf_fill
        if n >= remaining:
            self._out_buf[self._buf_fill:self._buf_fill + remaining] = out_chunk[:remaining]
            self._ref_buf[self._buf_fill:self._buf_fill + remaining] = ref_chunk[:remaining]
            self._buf_fill = self._window_samples
            return True

        self._out_buf[self._buf_fill:self._buf_fill + n] = out_chunk[:n]
        self._ref_buf[self._buf_fill:self._buf_fill + n] = ref_chunk[:n]
        self._buf_fill += n
        return False

    def _score_reference_window(self):
        ref, deg = self._ref_buf.copy(), self._out_buf.copy()
        try:
            self.si_snr = round(compute_si_snr(ref, deg), 2)
        except Exception:
            pass  # e.g. a near-silent window -- expected/routine, not worth logging every time
        try:
            self.stoi = round(compute_stoi(ref, deg, fs=self._sr), 3)
        except ModuleNotFoundError:
            self._warn_missing_dep_once("pystoi", "STOI")
        except Exception:
            pass
        try:
            self.pesq_wb = round(compute_pesq_wb(ref, deg, fs=self._sr), 2)
        except ModuleNotFoundError:
            self._warn_missing_dep_once("pesq", "PESQ-WB")
        except Exception:
            pass
        self.metrics_window_sec = self._window_sec
        # Slide: keep the second half, like models/dnsmos/dnsmos_infer.py.
        half = self._window_samples // 2
        self._out_buf[:half] = self._out_buf[half:half * 2]
        self._ref_buf[:half] = self._ref_buf[half:half * 2]
        self._buf_fill = half

    def _loop(self):
        next_level_check = time.monotonic()
        next_spectrum_check = time.monotonic()
        while self._running:
            time.sleep(self._poll_sec)

            reference_on = bool(getattr(self._pipeline, "reference_available", False))
            self.metrics_mode = "reference_backed" if reference_on else "non_intrusive"
            if not reference_on:
                self.si_snr = self.stoi = self.pesq_wb = None
                self.metrics_window_sec = None
            else:
                try:
                    if self._accumulate_reference_window():
                        self._score_reference_window()
                except Exception as exc:
                    print(f"[stage_metrics] reference scoring error: {exc}", file=sys.stderr)

            now = time.monotonic()
            if now >= next_level_check:
                try:
                    self._update_levels()
                except Exception as exc:
                    print(f"[stage_metrics] level error: {exc}", file=sys.stderr)
                next_level_check = now + self._cadence_sec

            if now >= next_spectrum_check:
                try:
                    self._update_spectra_and_suppression()
                except Exception as exc:
                    print(f"[stage_metrics] spectrum/suppression error: {exc}", file=sys.stderr)
                next_spectrum_check = now + self._spectrum_cadence_sec

            self.last_updated = now

    def snapshot(self) -> dict:
        return {
            "stage_levels_db": dict(self.stage_levels_db),
            "suppression_db": self.suppression_db,
            "suppression_bins": self.suppression_bins,
            "spectrum_before": self.spectrum_before,
            "spectrum_after": self.spectrum_after,
            "metrics_mode": self.metrics_mode,
            "reference_available": self.metrics_mode == "reference_backed",
            "si_snr": self.si_snr,
            "stoi": self.stoi,
            "pesq_wb": self.pesq_wb,
            "metrics_window_sec": self.metrics_window_sec,
        }


# ---------------------------------------------------------------------------
# Self-test (Mode A -- synthetic pipeline, no audio hardware)
# ---------------------------------------------------------------------------
def _self_test():
    print("live/stage_metrics.py self-test -- start")

    from live.stage_taps import StageTaps

    class _MockPipeline:
        _sr = 48000
        _chunk_sec = 0.1
        reference_available = False
        current_clean_ref_chunk = None

        def __init__(self):
            self.stage_taps = StageTaps()

    sr = 48000
    n = 4800
    t = np.arange(n) / sr
    rng = np.random.default_rng(0)
    speech = 0.3 * np.sin(2 * np.pi * 300 * t).astype(np.float32)
    noisy = (speech + 0.4 * rng.standard_normal(n)).astype(np.float32)

    # --- Test 1: non-intrusive levels + suppression, no reference ---
    pipe = _MockPipeline()
    pipe.stage_taps.capture = noisy
    pipe.stage_taps.output = speech  # simulates near-total noise removal
    sm = StageMetrics(pipe, cadence_sec=0.05, window_sec=1.0, poll_sec=0.01)
    sm._update_levels()
    sm._update_spectra_and_suppression()
    assert sm.stage_levels_db["capture"] is not None and sm.stage_levels_db["pre_filter"] is None
    assert sm.suppression_db is not None and len(sm.suppression_db) == FREQ_BINS
    assert np.mean(sm.suppression_db) < 0, "output is quieter than input -> suppression should be negative"
    print(f"  [PASS] test 1: non-intrusive levels populate only tapped stages; "
          f"suppression mean={np.mean(sm.suppression_db):.1f} dB (negative, as expected)")

    # --- Test 1b: display spectra are produced HERE (once per tick), quantised
    # to uint8 range, so demo/webdash/app.py never recomputes them per client.
    snap = sm.snapshot()
    for key in ("spectrum_before", "spectrum_after"):
        assert snap[key] is not None and len(snap[key]) == FREQ_BINS, f"{key} missing/wrong length"
        assert all(0 <= v <= 255 for v in snap[key]), f"{key} not quantised into 0-255"
    assert np.mean(snap["spectrum_after"]) < np.mean(snap["spectrum_before"]), (
        "under one SHARED auto-gain, the suppressed AFTER panel must read darker than BEFORE"
    )
    print("  [PASS] test 1b: display spectra computed once in the metrics thread, quantised "
          "to 0-255, AFTER reads darker than BEFORE under the shared auto-gain")

    # --- Test 2: reference_available False -> intrusive metrics stay None, never fabricated ---
    sm._running = True
    reference_on = bool(getattr(pipe, "reference_available", False))
    sm.metrics_mode = "reference_backed" if reference_on else "non_intrusive"
    assert sm.metrics_mode == "non_intrusive"
    assert sm.snapshot()["si_snr"] is None and sm.snapshot()["stoi"] is None
    print("  [PASS] test 2: no clean reference -> metrics_mode='non_intrusive', "
          "SI-SNR/STOI/PESQ all None (never a fabricated live number)")

    # --- Test 3: reference-backed accumulation fills the window and scores real metrics,
    # discriminating a near-clean output from a heavily-degraded one (relative check --
    # STOI's absolute scale is known to behave oddly on a pure-tone synthetic "speech"
    # signal, so this asserts the metric moves the RIGHT DIRECTION, not a fixed threshold) ---
    def _score_after_n_chunks(noise_scale: float):
        pipe = _MockPipeline()
        pipe.reference_available = True
        sm = StageMetrics(pipe, cadence_sec=0.05, window_sec=0.5, poll_sec=0.01)
        filled = False
        for _ in range(6):  # 0.5s window / 100ms chunks = 5 chunks needed
            out_chunk = (speech + noise_scale * rng.standard_normal(n)).astype(np.float32)
            pipe.stage_taps.output = out_chunk
            pipe.current_clean_ref_chunk = speech
            filled = sm._accumulate_reference_window()
            if filled:
                break
        assert filled, "window should fill within 6 chunks for a 0.5s window at 100ms chunks"
        sm._score_reference_window()
        return sm

    sm_clean = _score_after_n_chunks(0.01)
    sm_noisy = _score_after_n_chunks(0.5)
    assert sm_clean.si_snr is not None and sm_noisy.si_snr is not None
    assert sm_clean.si_snr > sm_noisy.si_snr, (
        f"near-clean SI-SNR ({sm_clean.si_snr}) should exceed heavily-degraded ({sm_noisy.si_snr})"
    )
    assert sm_clean.stoi is not None and sm_noisy.stoi is not None
    assert sm_clean.stoi > sm_noisy.stoi, (
        f"near-clean STOI ({sm_clean.stoi}) should exceed heavily-degraded ({sm_noisy.stoi})"
    )
    print(f"  [PASS] test 3: reference-backed window fills from real chunk pairs and scores "
          f"discriminate near-clean (SI-SNR={sm_clean.si_snr} dB, STOI={sm_clean.stoi}) from "
          f"heavily-degraded (SI-SNR={sm_noisy.si_snr} dB, STOI={sm_noisy.stoi})")

    # --- Test 4: identity-based dedup never double-counts the same chunk object ---
    sm3 = StageMetrics(_MockPipeline(), cadence_sec=0.05, window_sec=1.0, poll_sec=0.01)
    same_chunk = speech.copy()
    sm3._pipeline.current_clean_ref_chunk = speech
    sm3._pipeline.stage_taps.output = same_chunk
    r1 = sm3._accumulate_reference_window()
    fill_after_first = sm3._buf_fill
    r2 = sm3._accumulate_reference_window()  # same object again -- must be ignored
    assert sm3._buf_fill == fill_after_first, "re-polling the same chunk object must not double-accumulate"
    print("  [PASS] test 4: polling the same output chunk twice does not double-accumulate the window")

    print("live/stage_metrics.py self-test -- ALL PASSED")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _self_test()
    else:
        print("This module is a library. Use --self-test or import StageMetrics.")
