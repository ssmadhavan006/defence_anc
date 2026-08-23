import os
import sys
import glob
import csv
import argparse
import time
import numpy as np
import soundfile as sf
from scipy.signal import stft, istft

def wiener_filter(
    noisy_signal: np.ndarray,
    sr: int = 48000,
    n_fft: int = 1024,
    hop_length: int = 256,
    alpha_dd: float = 0.98,
    quantile: float = 0.15,
) -> np.ndarray:
    """
    First-principles Wiener Filter with Decision-Directed (DD) a priori SNR estimation
    (Ephraim & Malah / Scalart & Vieira-Filho formulation).

    Parameters:
      noisy_signal : 1D numpy array of float32 samples.
      sr           : Sample rate (Hz). Default 48000.
      n_fft        : STFT window / FFT size (samples). Default 1024 (21.3 ms).
      hop_length   : Hop size (samples). Default 256 (75% overlap).
      alpha_dd     : Decision-directed smoothing factor. Default 0.98.
      quantile     : Quantile threshold across frames for noise power spectrum estimation. Default 0.15.

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
    n_bins, n_frames = Zxx.shape

    # Noise power spectrum estimation via quantile across frames
    noise_mag_spec = np.quantile(magnitude, quantile, axis=1, keepdims=True)
    noise_power_spec = noise_mag_spec ** 2

    # A posteriori SNR: gamma(m, k) = |Y(m, k)|^2 / P_n(k)
    gamma = (magnitude ** 2) / np.maximum(noise_power_spec, 1e-10)

    # Decision-Directed (DD) a priori SNR estimation and Wiener Gain computation frame by frame
    xi = np.zeros((n_bins, n_frames), dtype=np.float32)
    gain = np.zeros((n_bins, n_frames), dtype=np.float32)

    # First frame initialization
    prev_enhanced_power = np.maximum(magnitude[:, 0] ** 2 - noise_power_spec[:, 0], 0.0)

    for m in range(n_frames):
        # A posteriori SNR for current frame
        gamma_m = gamma[:, m]

        if m == 0:
            xi_m = (1.0 - alpha_dd) * np.maximum(gamma_m - 1.0, 0.0)
        else:
            # Decision-Directed formula: xi = alpha_dd * (P_s_prev / P_n) + (1 - alpha_dd) * max(gamma - 1, 0)
            xi_m = alpha_dd * (prev_enhanced_power / np.maximum(noise_power_spec[:, 0], 1e-10)) + (1.0 - alpha_dd) * np.maximum(gamma_m - 1.0, 0.0)

        # Wiener Gain: H = xi / (xi + 1)
        gain_m = xi_m / (xi_m + 1.0)
        gain[:, m] = gain_m

        # Store enhanced power for next frame's DD estimation
        enhanced_mag_m = gain_m * magnitude[:, m]
        prev_enhanced_power = enhanced_mag_m ** 2

    # Apply Wiener Gain to noisy complex spectrum
    Zxx_enhanced = gain * Zxx

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
    output_dir: str = "results/baselines/wiener",
    limit: int = None,
) -> list:
    """
    Batch processing helper for Wiener Filter.
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
        enhanced = wiener_filter(audio, sr=sr)

        # Peak protection
        peak = np.max(np.abs(enhanced))
        if peak > 0.95:
            enhanced = enhanced * (0.95 / peak)

        sf.write(out_path, enhanced, sr)
        processed.append((row, out_path, False))

    return processed

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wiener Filter Baseline")
    parser.add_argument("--manifest", default="data/manifest.csv")
    parser.add_argument("--output-dir", default="results/baselines/wiener")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    t0 = time.time()
    results = process_batch(args.manifest, args.output_dir, args.limit)
    elapsed = time.time() - t0
    print(f"Wiener Filter processed {len(results)} files in {elapsed:.2f}s")
