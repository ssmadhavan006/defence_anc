"""
models/noise_classifier/train.py — Train the 3-class noise classifier.

Implements a GROUPED split by noise_id (phase4_plan.md §3.2, DoD-1).
This prevents leakage: the same noise clip cannot appear in both train and
test at different SNRs/clean-speech combinations, which would inflate accuracy
by letting the model memorize noise instances.

Evidence logged per entry in progress.md:
  - Grouped split: zero noise_id overlap between train and test (DoD-1 assertion)
  - Per-class precision / recall / confusion matrix (never accuracy alone)
  - Split method stated alongside every reported number

Usage:
    python models/noise_classifier/train.py
    python models/noise_classifier/train.py --epochs 30 --lr 1e-3
    python models/noise_classifier/train.py --manifest data/manifest.csv

Output:
    models/noise_classifier/model.pt  — trained model weights
    results/classifier_eval.json      — split proof + per-class metrics
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
import soundfile as sf

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from models.noise_classifier.model import NoiseClassifierCNN, CLASSES, N_MELS, N_FRAMES, _N_FFT

_MODEL_OUT = os.path.join(_REPO_ROOT, "models", "noise_classifier", "model.pt")
_EVAL_OUT  = os.path.join(_REPO_ROOT, "results", "classifier_eval.json")
_MANIFEST  = os.path.join(_REPO_ROOT, "data", "manifest.csv")

# ---------------------------------------------------------------------------
# Mel spectrogram preprocessing (numpy only, matches classify_chunk.py)
# ---------------------------------------------------------------------------
_SR = 48_000
_HOP = 512
_WIN = 1024


def _mel_filterbank(sr: int = _SR, n_fft: int = _N_FFT, n_mels: int = N_MELS) -> np.ndarray:
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


_FBANK = _mel_filterbank()


def audio_to_feature(path: str, n_mels: int = N_MELS, n_frames: int = N_FRAMES) -> np.ndarray:
    """Load audio, compute log-mel, return (1, n_mels, n_frames) float32 tensor."""
    audio, sr = sf.read(path, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    if len(audio) == 0:
        return np.zeros((1, n_mels, n_frames), dtype=np.float32)

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
    mel_db = (10.0 * np.log10(mel)).astype(np.float32)  # keep float32
    mel_db -= mel_db.max()

    # Resize time axis to exactly n_frames via linear interpolation
    if mel_db.shape[0] != n_frames:
        x_src = np.linspace(0, 1, mel_db.shape[0])
        x_dst = np.linspace(0, 1, n_frames)
        mel_db = np.stack([np.interp(x_dst, x_src, mel_db[:, k]) for k in range(n_mels)], axis=1).astype(np.float32)

    return mel_db.T[np.newaxis, :, :]  # (1, n_mels, n_frames) float32


# ---------------------------------------------------------------------------
# Grouped split (DoD-1)
# ---------------------------------------------------------------------------
def grouped_split(manifest_rows, test_frac: float = 0.2, seed: int = 42):
    """
    Split `manifest_rows` (list of dicts with 'noise_id', 'category', 'output_path')
    into train/test such that ALL rows sharing a noise_id land in the SAME set.

    Returns (train_rows, test_rows).
    The caller must assert zero noise_id overlap (DoD-1 guard).
    """
    from collections import defaultdict
    rng = np.random.default_rng(seed)

    # Group noise_ids by category to get stratified class split
    cat_to_ids: dict = defaultdict(list)
    id_to_rows: dict = defaultdict(list)
    for row in manifest_rows:
        cat_to_ids[row["category"]].append(row["noise_id"])
        id_to_rows[row["noise_id"]].append(row)

    train_rows, test_rows = [], []
    for cat, ids in cat_to_ids.items():
        unique_ids = sorted(set(ids))
        rng.shuffle(unique_ids)
        n_test = max(1, int(len(unique_ids) * test_frac))
        test_ids = set(unique_ids[:n_test])
        for noise_id in unique_ids:
            bucket = test_rows if noise_id in test_ids else train_rows
            bucket.extend(id_to_rows[noise_id])

    return train_rows, test_rows


def _assert_no_leakage(train_rows, test_rows):
    train_ids = {r["noise_id"] for r in train_rows}
    test_ids = {r["noise_id"] for r in test_rows}
    overlap = train_ids & test_ids
    assert not overlap, (
        f"SPLIT LEAKAGE: {len(overlap)} noise_id(s) appear in both train and test: "
        f"{sorted(overlap)[:5]}..."
    )


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
class MixtureDataset(torch.utils.data.Dataset):
    def __init__(self, rows):
        self._rows = rows
        self._label_map = {c: i for i, c in enumerate(CLASSES)}

    def __len__(self):
        return len(self._rows)

    def __getitem__(self, idx):
        row = self._rows[idx]
        path = os.path.join(_REPO_ROOT, row["output_path"])
        feat = audio_to_feature(path)
        label = self._label_map[row["category"].upper()]
        return torch.from_numpy(feat), label


# ---------------------------------------------------------------------------
# Per-class metrics
# ---------------------------------------------------------------------------
def compute_metrics(all_labels, all_preds, class_names):
    n = len(class_names)
    cm = np.zeros((n, n), dtype=int)
    for t, p in zip(all_labels, all_preds):
        cm[t, p] += 1

    metrics = {}
    for i, cls in enumerate(class_names):
        tp = cm[i, i]
        fp = cm[:, i].sum() - tp
        fn = cm[i, :].sum() - tp
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        metrics[cls] = {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4), "n": int(cm[i].sum())}

    acc = int(np.diag(cm).sum()) / max(int(cm.sum()), 1)
    return {"per_class": metrics, "accuracy": round(acc, 4), "confusion_matrix": cm.tolist()}


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------
def train(manifest_path: str = _MANIFEST, epochs: int = 20, lr: float = 1e-3,
          batch_size: int = 16, seed: int = 42) -> dict:
    """
    Train the classifier and return the evaluation results dict.
    Saves the model checkpoint to models/noise_classifier/model.pt.
    Saves the evaluation JSON to results/classifier_eval.json.
    """
    torch.manual_seed(seed)
    np.random.seed(seed)

    # -- Load manifest --
    import csv
    with open(manifest_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Normalise category to uppercase
    for r in rows:
        r["category"] = r["category"].upper()

    valid_cats = set(CLASSES)
    rows = [r for r in rows if r["category"] in valid_cats]
    print(f"Loaded {len(rows)} rows from {manifest_path}")

    # -- Grouped split (DoD-1) --
    train_rows, test_rows = grouped_split(rows, test_frac=0.2, seed=seed)
    _assert_no_leakage(train_rows, test_rows)
    print(f"Split: {len(train_rows)} train / {len(test_rows)} test (grouped by noise_id)")

    # -- Datasets --
    train_ds = MixtureDataset(train_rows)
    test_ds  = MixtureDataset(test_rows)
    train_dl = torch.utils.data.DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    test_dl  = torch.utils.data.DataLoader(test_ds,  batch_size=batch_size, shuffle=False)

    # -- Model --
    device = torch.device("cpu")
    model = NoiseClassifierCNN(n_classes=3).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    # -- Train --
    for epoch in range(1, epochs + 1):
        model.train()
        losses = []
        for x, y in train_dl:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            logits = model(x)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()
            losses.append(loss.item())
        if epoch % 5 == 0 or epoch == 1:
            print(f"  Epoch {epoch}/{epochs}  loss={np.mean(losses):.4f}")

    # -- Evaluate --
    model.eval()
    all_labels, all_preds = [], []
    with torch.no_grad():
        for x, y in test_dl:
            logits = model(x.to(device))
            preds = logits.argmax(dim=1).cpu().tolist()
            all_preds.extend(preds)
            all_labels.extend(y.tolist())

    metrics = compute_metrics(all_labels, all_preds, CLASSES)
    metrics["split_method"] = "grouped_by_noise_id"
    metrics["train_n"] = len(train_rows)
    metrics["test_n"] = len(test_rows)

    # Noise-id overlap assertion (must be zero; kept as a runtime check)
    train_ids = sorted({r["noise_id"] for r in train_rows})
    test_ids  = sorted({r["noise_id"] for r in test_rows})
    metrics["train_noise_id_count"] = len(train_ids)
    metrics["test_noise_id_count"] = len(test_ids)
    metrics["noise_id_overlap"] = len(set(train_ids) & set(test_ids))
    assert metrics["noise_id_overlap"] == 0, "BUG: leakage detected after training"

    # -- Save --
    os.makedirs(os.path.dirname(_MODEL_OUT), exist_ok=True)
    torch.save({"model_state": model.state_dict(), "classes": CLASSES,
                "n_mels": N_MELS, "n_frames": N_FRAMES}, _MODEL_OUT)
    os.makedirs(os.path.dirname(_EVAL_OUT), exist_ok=True)
    with open(_EVAL_OUT, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print(f"\nModel saved: {_MODEL_OUT}")
    print(f"Eval saved:  {_EVAL_OUT}")
    print(f"Accuracy: {metrics['accuracy']:.4f} (split: {metrics['split_method']})")
    print("Per-class:")
    for cls, m in metrics["per_class"].items():
        print(f"  {cls:<16s}  P={m['precision']:.3f}  R={m['recall']:.3f}  F1={m['f1']:.3f}  n={m['n']}")
    print(f"Noise-id overlap (must be 0): {metrics['noise_id_overlap']}")

    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=_MANIFEST)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    train(args.manifest, args.epochs, args.lr, args.batch_size)
