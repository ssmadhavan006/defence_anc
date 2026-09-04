"""
models/noise_classifier/classify_chunk.py — Phase 4 WOW #1 inference module.

Loads the trained checkpoint (model.pt) and classifies an audio chunk as:
  STATIONARY / NON_STATIONARY / IMPULSIVE / UNCERTAIN

UNCERTAIN is returned when max softmax confidence < confidence_threshold.
This prevents a confident-looking wrong label from appearing in front of judges.

Background thread cadence: 500ms (configurable via config.noise_classifier.cadence_sec).
Display-only under D1-A: the result is shown but never used to route attenuation.

Self-test (Mode A, no hardware, no trained model needed):
    python models/noise_classifier/classify_chunk.py --self-test
    Verifies: output shape, class range, UNCERTAIN state, and zero noise_id
    overlap in a simulated split (grouped-split leakage guard).

Usage:
    from models.noise_classifier.classify_chunk import NoiseClassifier
    clf = NoiseClassifier("models/noise_classifier/model.pt", threshold=0.6)
    clf.start(pipeline, telemetry)  # starts the background thread
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

try:
    import torch
    import torch.nn.functional as F
    _TORCH_OK = True
except ImportError:
    _TORCH_OK = False

from models.noise_classifier.model import CLASSES, N_MELS, N_FRAMES, _N_FFT, NoiseClassifierCNN

# Mel parameters — must match train.py
_SR = 48_000
_HOP = 512
_WIN = 1024


def _build_fbank(sr: int = _SR, n_fft: int = _N_FFT, n_mels: int = N_MELS) -> np.ndarray:
    def _hz2mel(hz):
        return 2595.0 * np.log10(1.0 + hz / 700.0)

    def _mel2hz(mel):
        return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

    mel_pts = np.linspace(_hz2mel(0), _hz2mel(sr / 2), n_mels + 2)
    hz_pts = _mel2hz(mel_pts)
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


_FBANK = _build_fbank()


def chunk_to_feature(audio: np.ndarray, n_mels: int = N_MELS,
                     n_frames: int = N_FRAMES) -> np.ndarray:
    """Convert a mono float32 audio chunk to (1, 1, n_mels, n_frames) feature tensor."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    win = np.hanning(_WIN).astype(np.float32)
    total = len(audio)
    n_fft_out = _N_FFT // 2 + 1
    n_time = max(1, (total - _WIN) // _HOP + 1)
    spec = np.zeros((n_time, n_fft_out), dtype=np.float32)
    for i in range(n_time):
        frame = audio[i * _HOP: i * _HOP + _WIN]
        if len(frame) < _WIN:
            frame = np.pad(frame, (0, _WIN - len(frame)))
        fft_out = np.fft.rfft(frame * win, n=_N_FFT)
        spec[i] = np.abs(fft_out) ** 2

    mel = np.dot(spec, _FBANK.T)
    mel = np.maximum(mel, 1e-10)
    mel_db = (10.0 * np.log10(mel)).astype(np.float32)  # keep float32; log10 upcasts to float64
    mel_db -= mel_db.max()

    if mel_db.shape[0] != n_frames:
        x_src = np.linspace(0, 1, mel_db.shape[0])
        x_dst = np.linspace(0, 1, n_frames)
        mel_db = np.stack([np.interp(x_dst, x_src, mel_db[:, k]) for k in range(n_mels)], axis=1).astype(np.float32)

    return mel_db.T[np.newaxis, np.newaxis, :, :]  # (1, 1, n_mels, n_frames) float32


def classify_audio(model, audio: np.ndarray,
                   threshold: float = 0.6) -> tuple[str, float]:
    """
    Classify `audio` (mono float32 array) with the given model.

    Returns
    -------
    (category, confidence)
        category: one of CLASSES or "UNCERTAIN"
        confidence: max softmax probability in [0, 1]
    """
    feat = chunk_to_feature(audio)
    with torch.no_grad():
        x = torch.from_numpy(feat)
        logits = model(x)
        probs = F.softmax(logits, dim=1).squeeze(0)
        conf, idx = probs.max(0)
        conf_val = float(conf.item())
        if conf_val < threshold:
            return "UNCERTAIN", conf_val
        return CLASSES[int(idx.item())], conf_val


# ---------------------------------------------------------------------------
# Background classifier thread
# ---------------------------------------------------------------------------
class NoiseClassifier:
    """
    Background thread that classifies pipeline audio at cadence_sec intervals.

    Writes to telemetry.noise_category and telemetry.noise_confidence.
    Also writes to telemetry.impulsive_event_count when IMPULSIVE is detected.

    Display-only (D1-A): result is shown, never used to route attenuation.
    """

    def __init__(self, model_path: str, threshold: float = 0.6,
                 cadence_sec: float = 0.5):
        self._model_path = model_path
        self._threshold = threshold
        self._cadence_sec = cadence_sec
        self._model = None
        self._thread = threading.Thread(target=self._loop, daemon=True, name="noise_clf")

    def start(self, pipeline, telemetry):
        self._pipeline = pipeline
        self._telemetry = telemetry
        self._running = True
        self._thread.start()

    def stop(self):
        self._running = False

    def _load_model(self):
        if not os.path.exists(self._model_path):
            raise FileNotFoundError(
                f"Classifier model not found: {self._model_path}\n"
                f"Train it first: python models/noise_classifier/train.py"
            )
        ckpt = torch.load(self._model_path, map_location="cpu")
        model = NoiseClassifierCNN(n_classes=len(CLASSES))
        model.load_state_dict(ckpt["model_state"])
        model.eval()
        return model

    def _loop(self):
        try:
            self._model = self._load_model()
        except FileNotFoundError as e:
            print(f"[classifier] WARN: {e} — classifier will not run.", flush=True)
            return

        print("[classifier] Noise classifier started.", flush=True)
        while self._running:
            time.sleep(self._cadence_sec)
            chunk = getattr(self._pipeline, "last_in_chunk", None)
            if chunk is None:
                continue

            try:
                cat, conf = classify_audio(self._model, chunk, self._threshold)
                self._telemetry.noise_category = cat
                self._telemetry.noise_confidence = conf
                if cat == "IMPULSIVE":
                    self._telemetry.impulsive_event_count += 1
            except Exception as e:
                print(f"[classifier] inference error: {e}", flush=True)


# ---------------------------------------------------------------------------
# Self-test (Mode A — no hardware, no trained model needed)
# ---------------------------------------------------------------------------
def _run_selftest():
    if not _TORCH_OK:
        print("[SKIP] torch not installed")
        sys.exit(0)

    rng = np.random.default_rng(42)

    # 1. Output shape and class range
    model = NoiseClassifierCNN(n_classes=3)
    model.eval()
    dummy = rng.standard_normal((1, 1, N_MELS, N_FRAMES)).astype(np.float32)
    with torch.no_grad():
        logits = model(torch.from_numpy(dummy))
    assert logits.shape == (1, 3), f"logits shape wrong: {logits.shape}"

    # 2. classify_audio returns a valid (category, confidence) pair
    audio = rng.standard_normal(int(_SR * 0.5)).astype(np.float32)  # 500ms
    cat, conf = classify_audio(model, audio, threshold=0.6)
    assert cat in CLASSES or cat == "UNCERTAIN", f"invalid category: {cat!r}"
    assert 0.0 <= conf <= 1.0, f"confidence out of range: {conf}"

    # 3. UNCERTAIN state fires when all classes near-equal probability
    # Force near-uniform logits → softmax ≈ 0.33 each → below threshold=0.6
    import torch.nn as nn

    class _UniformModel(nn.Module):
        def forward(self, x):
            return torch.zeros(x.shape[0], 3)

    u_model = _UniformModel()
    cat_u, conf_u = classify_audio(u_model, audio, threshold=0.6)
    assert cat_u == "UNCERTAIN", f"expected UNCERTAIN from uniform model, got {cat_u!r}"
    assert conf_u < 0.6

    # 4. Grouped-split leakage assertion: simulate noise_id groups
    #    Create fake rows where 3 noise_ids appear in 2 categories
    sys.path.insert(0, _REPO_ROOT)
    from models.noise_classifier.train import grouped_split, _assert_no_leakage

    fake_rows = []
    for cat in ["STATIONARY", "NON_STATIONARY", "IMPULSIVE"]:
        for nid in [f"n{cat[:3]}{i}" for i in range(10)]:
            for _ in range(3):  # 3 mixtures per noise_id
                fake_rows.append({"noise_id": nid, "category": cat, "output_path": "x"})

    train_rows, test_rows = grouped_split(fake_rows, test_frac=0.2, seed=42)
    _assert_no_leakage(train_rows, test_rows)  # must not raise
    train_ids = {r["noise_id"] for r in train_rows}
    test_ids  = {r["noise_id"] for r in test_rows}
    assert not (train_ids & test_ids), "leakage detected in grouped split"

    print(f"  train noise_ids={len(train_ids)}  test noise_ids={len(test_ids)}  overlap=0 OK")
    print("[PASS] models/noise_classifier/classify_chunk.py self-test")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        _run_selftest()
    else:
        print("This module is a library. Use --self-test or import NoiseClassifier.")
