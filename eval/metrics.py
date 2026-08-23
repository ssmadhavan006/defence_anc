import numpy as np
import torch
import torchaudio
from typing import Optional, Tuple

try:
    import pystoi
    PYSTOI_AVAILABLE = True
except ImportError:
    PYSTOI_AVAILABLE = False

try:
    import pesq
    PESQ_AVAILABLE = True
except ImportError:
    PESQ_AVAILABLE = False


def compute_si_snr(ref: np.ndarray, deg: np.ndarray, eps: float = 1e-8) -> float:
    """
    First-principles Scale-Invariant Signal-to-Noise Ratio (SI-SNR / SI-SDR).

    Formulation:
      s_target = (<deg, ref> / ||ref||^2) * ref
      e_noise  = deg - s_target
      SI-SNR   = 10 * log10( ||s_target||^2 / (||e_noise||^2 + eps) )

    Operates directly on 48 kHz float32 1D numpy arrays.
    """
    if ref.ndim > 1:
        ref = ref[:, 0]
    if deg.ndim > 1:
        deg = deg[:, 0]

    min_len = min(len(ref), len(deg))
    s = ref[:min_len].astype(np.float64)
    s_hat = deg[:min_len].astype(np.float64)

    # Zero-mean normalization
    s = s - np.mean(s)
    s_hat = s_hat - np.mean(s_hat)

    s_pwr = np.sum(s ** 2)
    if s_pwr < eps:
        raise ValueError("Clean reference audio has zero/negligible energy.")

    dot_prod = np.sum(s_hat * s)
    s_target = (dot_prod / s_pwr) * s
    e_noise = s_hat - s_target

    target_pwr = np.sum(s_target ** 2)
    noise_pwr = np.sum(e_noise ** 2)

    if noise_pwr < eps:
        return 100.0  # Max upper bound for perfect match

    ratio = target_pwr / (noise_pwr + eps)
    if ratio <= 0:
        return -100.0

    return float(10.0 * np.log10(ratio))


def compute_stoi(ref: np.ndarray, deg: np.ndarray, fs: int = 48000, extended: bool = False) -> float:
    """
    Short-Time Objective Intelligibility (STOI).
    Uses PySTOI library (pystoi.stoi).
    PySTOI accepts 48000 Hz input directly and performs internal resampling to 10 kHz.
    """
    if not PYSTOI_AVAILABLE:
        raise ModuleNotFoundError("pystoi package is not installed.")

    if ref.ndim > 1:
        ref = ref[:, 0]
    if deg.ndim > 1:
        deg = deg[:, 0]

    min_len = min(len(ref), len(deg))
    r = ref[:min_len]
    d = deg[:min_len]

    score = pystoi.stoi(r, d, fs, extended=extended)
    if np.isnan(score) or np.isinf(score):
        raise ValueError("STOI computation returned NaN or Inf.")

    return float(score)


def compute_pesq_wb(ref: np.ndarray, deg: np.ndarray, fs: int = 48000) -> float:
    """
    Perceptual Evaluation of Speech Quality (PESQ) - Wideband Mode (ITU-T P.862.2).

    IMPORTANT (Rule 23):
    PESQ-WB in the 'pesq' C library accepts ONLY 16,000 Hz input.
    Input audio is natively 48,000 Hz. We perform an IN-MEMORY ONLY resample
    from 48,000 Hz to 16,000 Hz for the PESQ call. The 48 kHz files on disk are never modified.
    """
    if not PESQ_AVAILABLE:
        raise ModuleNotFoundError("pesq package is not installed.")

    if ref.ndim > 1:
        ref = ref[:, 0]
    if deg.ndim > 1:
        deg = deg[:, 0]

    min_len = min(len(ref), len(deg))
    r_48k = ref[:min_len]
    d_48k = deg[:min_len]

    # In-memory resampling to 16,000 Hz for PESQ-WB
    target_pesq_sr = 16000
    if fs != target_pesq_sr:
        r_tensor = torch.from_numpy(r_48k).unsqueeze(0)
        d_tensor = torch.from_numpy(d_48k).unsqueeze(0)
        r_16k = torchaudio.functional.resample(r_tensor, fs, target_pesq_sr).squeeze(0).numpy()
        d_16k = torchaudio.functional.resample(d_tensor, fs, target_pesq_sr).squeeze(0).numpy()
    else:
        r_16k = r_48k
        d_16k = d_48k

    score = pesq.pesq(target_pesq_sr, r_16k, d_16k, "wb")
    if np.isnan(score) or np.isinf(score):
        raise ValueError("PESQ computation returned NaN or Inf.")

    return float(score)
