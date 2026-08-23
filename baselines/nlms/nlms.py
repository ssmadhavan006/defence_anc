import os
import sys
import glob
import csv
import argparse
import time
import random
import numpy as np
import soundfile as sf
import torch
from numba import jit

sys.path.insert(0, ".")
from models.deepfilternet.df_compat import resample

TARGET_SR = 48000

@jit(nopython=True, fastmath=True)
def nlms_adaptive_filter(
    primary: np.ndarray,
    reference: np.ndarray,
    filter_length: int = 64,
    mu: float = 0.01,
    eps: float = 1e-6,
) -> np.ndarray:
    """
    First-principles Normalized Least Mean Squares (NLMS) Adaptive Filter (Widrow / Haykin).

    Parameters:
      primary       : 1D float32 numpy array d[n] (noisy mixture signal).
      reference     : 1D float32 numpy array x[n] (true reference noise signal, perfectly sample-aligned).
      filter_length : Number of adaptive filter taps L. Default 64.
      mu            : Normalized step-size adaptation parameter. Default 0.01.
      eps           : Small regularization constant to prevent division by zero. Default 1e-6.

    Returns:
      enhanced_signal : 1D float32 numpy array e[n] (error signal = speech estimate).
    """
    N = len(primary)
    L = filter_length
    
    weights = np.zeros(L, dtype=np.float32)
    error_signal = np.zeros(N, dtype=np.float32)
    
    # Pre-pad reference with L-1 zeros for initial tap filling
    ref_padded = np.zeros(N + L - 1, dtype=np.float32)
    ref_padded[L - 1 :] = reference[:N]
    
    for n in range(N):
        # Accumulate filter output y[n] = w^T * x[n] and tap energy ||x[n]||^2
        y = 0.0
        pwr = 0.0
        for i in range(L):
            val = ref_padded[n + L - 1 - i]
            y += weights[i] * val
            pwr += val * val
            
        # Error signal: e[n] = d[n] - y[n]
        err = primary[n] - y
        error_signal[n] = err
        
        # Normalized weight update: w[n+1] = w[n] + (mu / (||x[n]||^2 + eps)) * e[n] * x[n]
        adaptation_factor = (mu / (pwr + eps)) * err
        for i in range(L):
            val = ref_padded[n + L - 1 - i]
            weights[i] += adaptation_factor * val
            
    return error_signal

def load_and_prep_audio(filepath: str, target_sr: int = TARGET_SR) -> np.ndarray:
    data, orig_sr = sf.read(filepath, dtype="float32")
    if data.ndim > 1:
        data = data[:, 0]
    if orig_sr != target_sr:
        tensor_data = torch.from_numpy(data).unsqueeze(0)
        resampled_tensor = resample(tensor_data, orig_sr, target_sr)
        data = resampled_tensor.squeeze(0).numpy()
    return data

def process_batch(
    manifest_path: str = "data/manifest.csv",
    noise_base_dir: str = "data/noise",
    output_dir: str = "results/baselines/nlms",
    limit: int = None,
    filter_length: int = 64,
    mu: float = 0.01,
) -> list:
    """
    Batch processing helper for NLMS Adaptive Filter.
    Strictly uses true original noise clip traced via manifest noise_id (Rule 18) AND
    replicates the exact seed-based start_idx offset used during dataset mixing (Hypothesis A Fix).
    Idempotent / resumable: skips already existing files (Rule 20).
    """
    os.makedirs(output_dir, exist_ok=True)
    with open(manifest_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    if limit is not None and limit < len(rows):
        rows = rows[:limit]

    processed = []
    skipped = 0

    # Warmup Numba JIT
    dummy_primary = np.zeros(1000, dtype=np.float32)
    dummy_ref = np.zeros(1000, dtype=np.float32)
    _ = nlms_adaptive_filter(dummy_primary, dummy_ref, filter_length=filter_length, mu=mu)

    for row in rows:
        mix_path = row["output_path"]
        noise_id = row["noise_id"]
        cat = row["category"]
        sub = row["subtype"]
        combo_seed = int(row["seed"])

        mix_file = os.path.basename(mix_path)
        out_path = os.path.join(output_dir, mix_file)

        if os.path.exists(out_path):
            skipped += 1
            processed.append((row, out_path, True))
            continue

        # Rule 18: Trace true original noise reference clip
        matches = glob.glob(os.path.join(noise_base_dir, cat, sub, "**", noise_id), recursive=True)
        if not matches:
            matches = glob.glob(os.path.join(noise_base_dir, "**", noise_id), recursive=True)
        if not matches:
            raise FileNotFoundError(f"Rule 18 Violation! Could not trace reference noise_id '{noise_id}' under {noise_base_dir}")
        
        ref_noise_path = matches[0]

        primary_audio = load_and_prep_audio(mix_path, TARGET_SR)
        ref_audio = load_and_prep_audio(ref_noise_path, TARGET_SR)

        # Replicate exact seed-based alignment logic from data/mix_dataset.py
        random.seed(combo_seed)
        np.random.seed(combo_seed)

        len_clean = len(primary_audio)
        len_ref = len(ref_audio)
        if len_ref < len_clean:
            repeat_count = int(np.ceil(len_clean / len_ref))
            ref_aligned = np.tile(ref_audio, repeat_count)[:len_clean]
        else:
            start_idx = random.randint(0, len_ref - len_clean)
            ref_aligned = ref_audio[start_idx : start_idx + len_clean]

        enhanced = nlms_adaptive_filter(primary_audio, ref_aligned, filter_length=filter_length, mu=mu)

        # Peak protection
        peak = np.max(np.abs(enhanced))
        if peak > 0.95:
            enhanced = enhanced * (0.95 / peak)

        sf.write(out_path, enhanced, TARGET_SR)
        processed.append((row, out_path, False))

    return processed

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NLMS Adaptive Filter Baseline")
    parser.add_argument("--manifest", default="data/manifest.csv")
    parser.add_argument("--noise-dir", default="data/noise")
    parser.add_argument("--output-dir", default="results/baselines/nlms")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--taps", type=int, default=64)
    parser.add_argument("--mu", type=float, default=0.01)
    args = parser.parse_args()

    t0 = time.time()
    results = process_batch(args.manifest, args.noise_dir, args.output_dir, args.limit, args.taps, args.mu)
    elapsed = time.time() - t0
    print(f"NLMS Adaptive Filter processed {len(results)} files in {elapsed:.2f}s")
