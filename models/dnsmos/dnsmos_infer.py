"""
models/dnsmos/dnsmos_infer.py — Phase 4 WOW #3: DNSMOS P.835 quality monitor.

Runs Microsoft's sig_bak_ovr.onnx (MIT licence, see SOURCES.md) in a background
thread to estimate perceptual speech quality (SIG / BAK / OVR in [1, 5]).

Key design points (from phase4_plan.md §5 T5):
  - Background thread at config.dnsmos.cadence_sec (default 2s / 0.5 Hz)
  - 9-second sliding window over pipeline.last_out_chunk audio
  - Window-fill state: mos_valid=False until the first full 9-second window
    accumulates; UI shows "measuring…" rather than an early misleading number
  - Audio resampled from 48 kHz → 16 kHz internally (no external resampler)
  - Mel spectrogram computed with numpy only (no librosa dependency)
  - warn_threshold at OVR < 2.5; auto_bypass is OFF by default (Risk R8)
  - No onnxruntime import at module level: thread initialises lazily so that
    `import dnsmos_infer` never fails even when onnxruntime is absent

Self-test:
    python models/dnsmos/dnsmos_infer.py --self-test
    SKIP if onnxruntime not installed, SKIP if model file absent.

See also: SOURCES.md for model provenance and licence.
"""

import argparse
import os
import sys
import threading
import time

import numpy as np

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# Constants matching the DNSMOS P.835 preprocessing (see SOURCES.md)
# ---------------------------------------------------------------------------
_SR_MODEL = 16_000          # model expects 16 kHz input
_WINDOW_SEC = 9.01
_WINDOW_SAMPLES = int(_WINDOW_SEC * _SR_MODEL)
_N_MELS = 120
_FRAME_SIZE = 320
_HOP_LENGTH = 160
_N_FFT = 512                # next power of 2 above FRAME_SIZE

_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sig_bak_ovr.onnx")


# ---------------------------------------------------------------------------
# Mel spectrogram (numpy only — no librosa)
# ---------------------------------------------------------------------------
def _build_mel_filterbank(sr: int = _SR_MODEL, n_fft: int = _N_FFT,
                           n_mels: int = _N_MELS) -> np.ndarray:
    """Triangular mel filterbank matrix, shape (n_mels, n_fft//2+1)."""
    def _hz_to_mel(hz):
        return 2595.0 * np.log10(1.0 + hz / 700.0)

    def _mel_to_hz(mel):
        return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

    f_max = sr / 2.0
    mel_pts = np.linspace(_hz_to_mel(0.0), _hz_to_mel(f_max), n_mels + 2)
    hz_pts = _mel_to_hz(mel_pts)
    bins = np.floor((n_fft + 1) * hz_pts / sr).astype(int)
    bins = np.clip(bins, 0, n_fft // 2)

    fbank = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, n_mels + 1):
        lo, mid, hi = bins[m - 1], bins[m], bins[m + 1]
        if mid > lo:
            fbank[m - 1, lo:mid] = (np.arange(lo, mid) - lo) / (mid - lo)
        if hi > mid:
            fbank[m - 1, mid:hi] = (hi - np.arange(mid, hi)) / (hi - mid)
    return fbank


_MEL_FBANK = _build_mel_filterbank()  # computed once at import


def _audio_to_melspec(audio: np.ndarray) -> np.ndarray:
    """
    Compute log-mel spectrogram of `audio` (float32, 16 kHz).
    Returns shape (n_frames, N_MELS) matching the DNSMOS model input.
    """
    audio = audio.astype(np.float32)

    # Pad or trim to window length
    if len(audio) < _WINDOW_SAMPLES:
        audio = np.pad(audio, (0, _WINDOW_SAMPLES - len(audio)))
    else:
        audio = audio[:_WINDOW_SAMPLES]

    # Normalize to [-1, 1] to match model training distribution
    peak = np.abs(audio).max()
    if peak > 1e-8:
        audio /= peak

    # STFT frame extraction
    window = np.hanning(_FRAME_SIZE).astype(np.float32)
    n_frames = (_WINDOW_SAMPLES - _FRAME_SIZE) // _HOP_LENGTH + 1
    frames = np.lib.stride_tricks.as_strided(
        audio,
        shape=(n_frames, _FRAME_SIZE),
        strides=(audio.strides[0] * _HOP_LENGTH, audio.strides[0]),
    ).copy()  # copy so windowing doesn't mutate the original

    frames *= window[np.newaxis, :]

    # FFT → power spectrum (shape: n_frames × n_fft//2+1)
    spec = np.fft.rfft(frames, n=_N_FFT).real ** 2 + np.fft.rfft(frames, n=_N_FFT).imag ** 2

    # Mel filterbank → log mel
    mel = np.dot(spec, _MEL_FBANK.T)
    mel = np.maximum(mel, 1e-10)
    mel_db = 10.0 * np.log10(mel)
    mel_db -= mel_db.max()   # ref=max, same as librosa power_to_db
    return mel_db.astype(np.float32)  # (n_frames, N_MELS)


# ---------------------------------------------------------------------------
# Polynomial post-processing from the DNSMOS reference implementation
# ---------------------------------------------------------------------------
_P_OVR = np.poly1d([-0.06766283, 1.11546468, 0.04602535])
_P_SIG = np.poly1d([-0.08397278, 1.22083953, 0.00524610])
_P_BAK = np.poly1d([-0.13166888, 1.60915514, -0.39604546])


def _polyfit(sig_raw: float, bak_raw: float, ovr_raw: float):
    sig = float(np.clip(_P_SIG(sig_raw), 1.0, 5.0))
    bak = float(np.clip(_P_BAK(bak_raw), 1.0, 5.0))
    ovr = float(np.clip(_P_OVR(ovr_raw), 1.0, 5.0))
    return sig, bak, ovr


def _resample_to_16k(audio_48k: np.ndarray, sr_in: int = 48_000) -> np.ndarray:
    """Linear-interpolation downsample from sr_in → 16 kHz (stdlib numpy only)."""
    if sr_in == _SR_MODEL:
        return audio_48k.astype(np.float32)
    ratio = sr_in / _SR_MODEL
    n_out = int(len(audio_48k) / ratio)
    x_in = np.arange(n_out, dtype=np.float64) * ratio
    return np.interp(x_in, np.arange(len(audio_48k)), audio_48k).astype(np.float32)


def _infer_window(session, audio_48k: np.ndarray):
    """Run one DNSMOS forward pass on a single ~9.01s window; return (sig, bak, ovr)
    in [1, 5]. Shared by DNSMOSMonitor (live, streaming) and score_file() (offline,
    one-shot) so both use exactly the same preprocessing/postprocessing."""
    audio_16k = _resample_to_16k(audio_48k)
    mel = _audio_to_melspec(audio_16k)  # (n_frames, N_MELS)
    inp = mel[np.newaxis, np.newaxis, :, :]  # (1, 1, n_frames, N_MELS)
    out = session.run(None, {"input_1": inp.astype(np.float32)})[0]
    # out shape: (1, 3) or (1, 1, 3) — flatten to 3 values
    vals = out.flatten()[:3]
    return _polyfit(float(vals[0]), float(vals[1]), float(vals[2]))


def score_file(path: str, model_dir: str = None) -> dict:
    """
    One-shot, non-intrusive DNSMOS scoring of a whole audio file -- no clean
    reference needed. This is the only quality axis available for an ad-hoc
    live recording (demo/webdash/record_compare.py's "Record & Compare" mode):
    a fresh recording has no ground truth to score SI-SNR/STOI/PESQ-WB against,
    but DNSMOS estimates perceptual quality from the signal alone.

    Splits the file into non-overlapping _WINDOW_SEC windows (padding a short
    final window with silence) and averages SIG/BAK/OVR across them, so a
    result reflects the whole clip rather than just its first ~9 seconds.

    Raises ImportError if onnxruntime isn't installed, FileNotFoundError if
    the model hasn't been downloaded (models/dnsmos/download_model.py) --
    callers should catch both and treat DNSMOS as unavailable (grey it out),
    exactly like DNSMOSMonitor._loop() does for the live path.
    """
    import onnxruntime as ort
    import soundfile as sf

    model_dir = model_dir or os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(model_dir, "sig_bak_ovr.onnx")
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"DNSMOS model not found: {model_path}\nRun: python models/dnsmos/download_model.py"
        )
    session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio[:, 0]
    if sr != 48_000:
        # Resample to 48 kHz first (this function's internal pipeline expects
        # 48 kHz windows, then does its own 48k->16k step via _resample_to_16k).
        ratio = sr / 48_000
        n_out = int(len(audio) / ratio)
        audio = np.interp(np.arange(n_out, dtype=np.float64) * ratio,
                           np.arange(len(audio)), audio).astype(np.float32)

    window_samples_48k = int(_WINDOW_SEC * 48_000)
    if len(audio) < window_samples_48k:
        audio = np.pad(audio, (0, window_samples_48k - len(audio)))

    sigs, baks, ovrs = [], [], []
    for start in range(0, len(audio), window_samples_48k):
        window = audio[start:start + window_samples_48k]
        if len(window) < window_samples_48k:
            window = np.pad(window, (0, window_samples_48k - len(window)))
        sig, bak, ovr = _infer_window(session, window)
        sigs.append(sig); baks.append(bak); ovrs.append(ovr)

    return {
        "sig": round(float(np.mean(sigs)), 3),
        "bak": round(float(np.mean(baks)), 3),
        "ovr": round(float(np.mean(ovrs)), 3),
        "n_windows": len(sigs),
    }


# ---------------------------------------------------------------------------
# DNSMOSMonitor — background thread
# ---------------------------------------------------------------------------
class DNSMOSMonitor:
    """
    Background thread that updates telemetry.mos_{sig,bak,ovr,valid} at
    0.5 Hz from a sliding 9-second window of the pipeline output audio.

    Parameters
    ----------
    telemetry  : live.telemetry.PipelineTelemetry (written by this thread)
    pipeline   : object with .last_out_chunk (numpy array or None) and ._sr (int)
    model_dir  : directory containing sig_bak_ovr.onnx
    cadence_sec: seconds between inference passes (default 2.0)
    window_sec : audio window fed to DNSMOS (default 9.01)
    warn_threshold : log a warning when OVR < this value (default 2.5)
    auto_bypass: if True, flip pipeline._mode on low MOS (default False — Risk R8)
    """

    def __init__(self, telemetry, pipeline, model_dir: str = None,
                 cadence_sec: float = 2.0, window_sec: float = _WINDOW_SEC,
                 warn_threshold: float = 2.5, auto_bypass: bool = False):
        self._telemetry = telemetry
        self._pipeline = pipeline
        self._model_dir = model_dir or os.path.dirname(os.path.abspath(__file__))
        self._cadence_sec = cadence_sec
        self._window_sec = window_sec
        self._window_samples_48k = int(window_sec * 48_000)
        self._warn_threshold = warn_threshold
        self._auto_bypass = auto_bypass

        self._buf = np.zeros(self._window_samples_48k, dtype=np.float32)
        self._buf_fill = 0   # samples accumulated since last reset
        self._session = None
        self._thread = threading.Thread(target=self._loop, daemon=True, name="dnsmos")

    def start(self):
        self._thread.start()

    def stop(self):
        self._running = False

    def _load_session(self):
        import onnxruntime as ort
        model_path = os.path.join(self._model_dir, "sig_bak_ovr.onnx")
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"DNSMOS model not found: {model_path}\n"
                f"Run: python models/dnsmos/download_model.py"
            )
        self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    def _infer(self, audio_48k: np.ndarray):
        """Run DNSMOS inference; return (sig, bak, ovr) in [1, 5]."""
        return _infer_window(self._session, audio_48k)

    def _loop(self):
        self._running = True
        try:
            self._load_session()
        except (ImportError, FileNotFoundError) as e:
            print(f"[dnsmos] WARN: {e} — DNSMOS monitor will not run.", flush=True)
            return

        chunk_samples_48k = int(0.1 * 48_000)  # assume 100ms chunks
        print("[dnsmos] Monitor started.", flush=True)

        while self._running:
            time.sleep(self._cadence_sec)

            # Accumulate audio from pipeline output display hook
            chunk = getattr(self._pipeline, "last_out_chunk", None)
            if chunk is None:
                continue

            chunk = np.asarray(chunk, dtype=np.float32)
            n = len(chunk)
            remaining = self._window_samples_48k - self._buf_fill

            if n >= remaining:
                # Window is full; run inference
                self._buf[self._buf_fill:self._buf_fill + remaining] = chunk[:remaining]
                self._buf_fill = self._window_samples_48k

                try:
                    sig, bak, ovr = self._infer(self._buf.copy())
                    self._telemetry.mos_sig = sig
                    self._telemetry.mos_bak = bak
                    self._telemetry.mos_ovr = ovr
                    self._telemetry.mos_valid = True

                    if ovr < self._warn_threshold:
                        print(f"[dnsmos] WARN: MOS OVR={ovr:.2f} < {self._warn_threshold} threshold", flush=True)
                        if self._auto_bypass and getattr(self._pipeline, "_mode", "enhance") == "enhance":
                            self._pipeline._mode = "bypass"
                            print("[dnsmos] auto_bypass: switched to BYPASS", flush=True)
                except Exception as e:
                    print(f"[dnsmos] inference error: {e}", flush=True)

                # Slide the window: discard the oldest half, keep the second half
                half = self._window_samples_48k // 2
                self._buf[:half] = self._buf[half:half * 2]
                self._buf_fill = half
            else:
                self._buf[self._buf_fill:self._buf_fill + n] = chunk
                self._buf_fill += n


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
def _run_selftest():
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        print("[SKIP] onnxruntime not installed (see requirements-optional.txt D3-A)")
        sys.exit(0)

    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sig_bak_ovr.onnx")
    if not os.path.exists(model_path):
        print(f"[SKIP] DNSMOS model not found: {model_path}")
        print("       Run: python models/dnsmos/download_model.py")
        sys.exit(0)

    import onnxruntime as ort

    print("Loading DNSMOS model...")
    session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    # Synthetic sine wave at 440 Hz for 9.01 seconds at 16 kHz
    t = np.linspace(0, _WINDOW_SEC, _WINDOW_SAMPLES, endpoint=False, dtype=np.float32)
    audio_16k = np.sin(2 * np.pi * 440 * t) * 0.5

    mel = _audio_to_melspec(audio_16k)
    assert mel.shape == (mel.shape[0], _N_MELS), f"mel shape wrong: {mel.shape}"
    print(f"Mel spectrogram shape: {mel.shape}")

    inp = mel[np.newaxis, np.newaxis, :, :].astype(np.float32)
    try:
        out = session.run(None, {"input_1": inp})[0]
    except Exception as exc:
        print(f"[FAIL] models/dnsmos/dnsmos_infer.py self-test: model at {model_path!r} "
              f"rejected the expected input shape {inp.shape} ({exc}). This means the vendored "
              f"sig_bak_ovr.onnx is NOT the model this module's preprocessing was written for -- "
              f"see the note in models/dnsmos/download_model.py (2026-09-05: the originally-pinned "
              f"upstream commit was permanently lost to a history rewrite; the current commit at "
              f"the same path is a different, incompatible model). Do not use this file until the "
              f"preprocessing is updated to match it or a compatible model is sourced instead.")
        sys.exit(1)
    vals = out.flatten()[:3]
    sig, bak, ovr = _polyfit(float(vals[0]), float(vals[1]), float(vals[2]))

    assert 1.0 <= sig <= 5.0, f"SIG out of range: {sig}"
    assert 1.0 <= bak <= 5.0, f"BAK out of range: {bak}"
    assert 1.0 <= ovr <= 5.0, f"OVR out of range: {ovr}"

    print(f"DNSMOS on 440Hz sine: SIG={sig:.3f} BAK={bak:.3f} OVR={ovr:.3f}")

    # score_file(): whole-file, one-shot scoring for record_compare.py's
    # "Record & Compare" mode (no clean reference exists for a live recording,
    # so DNSMOS is the only quality axis available there).
    import tempfile
    import soundfile as sf

    tmp_dir = tempfile.mkdtemp(prefix="dnsmos_selftest_")
    try:
        t2 = np.linspace(0, 20.0, int(20.0 * 48_000), endpoint=False, dtype=np.float32)
        audio_48k = (np.sin(2 * np.pi * 440 * t2) * 0.5).astype(np.float32)
        clip_path = os.path.join(tmp_dir, "clip.wav")
        sf.write(clip_path, audio_48k, 48_000)

        result = score_file(clip_path)
        assert 1.0 <= result["sig"] <= 5.0 and 1.0 <= result["bak"] <= 5.0 and 1.0 <= result["ovr"] <= 5.0
        # 20s clip / 9.01s windows -> ceil(20/9.01) = 3 windows
        assert result["n_windows"] == 3, f"expected 3 windows for a 20s clip, got {result['n_windows']}"
        print(f"  [PASS] score_file(): {result['n_windows']} windows averaged, "
              f"SIG={result['sig']} BAK={result['bak']} OVR={result['ovr']}")
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print("[PASS] models/dnsmos/dnsmos_infer.py self-test")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        _run_selftest()
    else:
        print("This module is a library. Use --self-test or import DNSMOSMonitor.")
