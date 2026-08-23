import os
import sys
import glob
import csv
import argparse
import time
import numpy as np
import soundfile as sf
from scipy.signal import stft, istft

def spectral_subtraction(
    noisy_signal: np.ndarray,
    sr: int = 48000,
    n_fft: int = 1024,
    hop_length: int = 256,
    alpha: float = 2.0,
    beta: float = 0.02,
    quantile: float = 0.15,
) -> np.ndarray:
    """
    First-principles Spectral Subtraction (Berouti et al. / Boll formulation).

    Parameters:
      noisy_signal : 1D numpy array of float32 samples.
      sr           : Sample rate (Hz). Default 48000.
      n_fft        : STFT window / FFT size (samples). Default 1024 (21.3 ms).
      hop_length   : Hop size (samples). Default 256 (75% overlap).
      alpha        : Over-subtraction factor. Default 2.0.
      beta         : Spectral floor factor. Default 0.02 (-17 dB).
      quantile     : Quantile threshold across frames for noise spectrum estimation. Default 0.15.

    Returns:
      enhanced_signal : 1D numpy array of float32 samples matching input length.
    """
    if noisy_signal.ndim > 1:
        noisy_signal = noisy_signal[:, 0]

    # STFT
    frequencies, times, Zxx = stft(
        noisy_signal,
        fs=sr,
        window="hann",
        nperseg=n_fft,
        noverlap=n_fft - hop_length,
        boundary="zeros",
    )

    magnitude = np.abs(Zxx)
    phase = np.angle(Zxx)

    # Noise spectrum estimation via minimum-statistics / quantile across frames
    # Rationale: Noise is present throughout the mixture duration, so quantile estimation
    # across STFT frames robustly isolates the stationary noise floor without requiring a silent prefix.
    noise_mag_spec = np.quantile(magnitude, quantile, axis=1, keepdims=True)

    # Spectral subtraction formula with over-subtraction and spectral floor
    subtracted_power = magnitude**2 - alpha * (noise_mag_spec**2)
    floor_power = beta * (magnitude**2)

    enhanced_power = np.maximum(subtracted_power, floor_power)
    enhanced_magnitude = np.sqrt(enhanced_power)

    # Reconstruct complex STFT using noisy phase
    Zxx_enhanced = enhanced_magnitude * np.exp(1j * phase)

    # ISTFT
    _, enhanced_signal = istft(
        Zxx_enhanced,
        fs=sr,
        window="hann",
        nperseg=n_fft,
        noverlap=n_fft - hop_length,
        boundary=True,
    )

    # Match original length
    target_len = len(noisy_signal)
    if len(enhanced_signal) > target_len:
        enhanced_signal = enhanced_signal[:target_len]
    elif len(enhanced_signal) < target_len:
        enhanced_signal = np.pad(enhanced_signal, (0, target_len - len(enhanced_signal)))

    return enhanced_signal.astype(np.float32)

def process_batch(
    manifest_path: str = "data/manifest.csv",
    output_dir: str = "results/baselines/spectral_subtraction",
    limit: int = None,
) -> list:
    """
    Batch processing helper for Spectral Subtraction.
    Idempotent / resumable: skips already existing files.
    """
    os.makedirs(output_dir, exist_ok=True)
    with open(manifest_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    if limit is not None and limit < len(rows):
        rows = rows[:limit]

    processed = []
    skipped = 0

    for row in rows:
        mix_path = row["output_path"]
        mix_file = os.path.basename(mix_path)
        out_path = os.path.join(output_dir, mix_file)

        if os.path.exists(out_path):
            skipped += 1
            processed.append((row, out_path, True))
            continue

        audio, sr = sf.read(mix_path, dtype="float32")
        enhanced = spectral_subtraction(audio, sr=sr)

        # Peak protection to avoid clipping
        peak = np.max(np.abs(enhanced))
        if peak > 0.95:
            enhanced = enhanced * (0.95 / peak)

        sf.write(out_path, enhanced, sr)
        processed.append((row, out_path, False))

    return processed

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spectral Subtraction Baseline")
    parser.add_argument("--manifest", default="data/manifest.csv")
    parser.add_argument("--output-dir", default="results/baselines/spectral_subtraction")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    t0 = time.time()
    results = process_batch(args.manifest, args.output_dir, args.limit)
    elapsed = time.time() - t0
    print(f"Spectral Subtraction processed {len(results)} files in {elapsed:.2f}s")
