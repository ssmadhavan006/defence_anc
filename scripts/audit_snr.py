"""
scripts/audit_snr.py — Independent post-hoc SNR audit of data/mixtures/

This script is intentionally decoupled from data/mix_dataset.py's mixing logic.
It reads the clean and mixed .wav files from disk and computes SNR from the
raw sample values, NOT from any in-memory intermediate computed during mixing.

This rules out:
  1. Circular verification (using same P_s / P_d that derived the scale factor).
  2. File I/O corruption or quantisation error introduced by soundfile write/read.
  3. Signed-deviation cancellation hiding per-file errors in an aggregate mean.

Per Rule 13: log mean, max, min, and sample per-file rows as evidence.
"""

import os
import sys
import csv
import glob
import random
import numpy as np
import soundfile as sf

def independent_snr_from_disk(
    clean_path: str,
    mix_path: str,
    target_sr: int = 48000,
) -> dict:
    """
    Load clean and mixture audio from disk, infer the scaled noise as
        noise_estimate = mixture - clean_resampled_to_target_sr
    then compute SNR independently.

    IMPORTANT: The clean speech is loaded from its native sample rate and
    resampled to target_sr BEFORE the mix-minus-clean subtraction. This is
    necessary because LibriSpeech FLAC files are at 16 kHz, while mixtures
    are at 48 kHz. Without resampling, len(clean) != len(mix) and the subtraction
    would produce wrong noise estimates.
    """
    import torch
    import torchaudio

    # Load clean speech at its native rate
    clean_raw, clean_sr = sf.read(clean_path, dtype="float32")
    if clean_raw.ndim > 1:
        clean_raw = clean_raw[:, 0]

    # Resample clean to target_sr if needed
    resampled = False
    if clean_sr != target_sr:
        resampled = True
        tensor_data = torch.from_numpy(clean_raw).unsqueeze(0)
        resampled_tensor = torchaudio.functional.resample(tensor_data, clean_sr, target_sr)
        clean_raw = resampled_tensor.squeeze(0).numpy()

    # Load mixture (already at target_sr)
    mix_raw, mix_sr = sf.read(mix_path, dtype="float32")
    if mix_raw.ndim > 1:
        mix_raw = mix_raw[:, 0]

    # Align lengths
    min_len = min(len(clean_raw), len(mix_raw))
    clean_aligned = clean_raw[:min_len]
    mix_aligned = mix_raw[:min_len]

    # Estimate noise: noise_estimate = mix - clean (independent of mixing gain)
    noise_est = mix_aligned - clean_aligned

    clean_pwr = float(np.mean(clean_aligned ** 2))
    noise_est_pwr = float(np.mean(noise_est ** 2))

    if clean_pwr <= 1e-10 or noise_est_pwr <= 1e-10:
        reloaded_snr_db = None
    else:
        reloaded_snr_db = 10.0 * np.log10(clean_pwr / noise_est_pwr)

    return {
        "mix_file": os.path.basename(mix_path),
        "clean_peak": float(np.max(np.abs(clean_aligned))),
        "noise_est_peak": float(np.max(np.abs(noise_est))),
        "mix_peak": float(np.max(np.abs(mix_aligned))),
        "reloaded_snr_db": reloaded_snr_db,
        "resampled": resampled,
    }


def run_audit(
    manifest_path: str = "data/manifest.csv",
    clean_dir: str = "data/clean",
    mix_dir: str = "data/mixtures",
    n_sample: int = None,
    seed: int = 99,
):
    """
    Load manifest, sample rows, and independently recompute SNR from on-disk files.

    Uses `clean_ref_path` from manifest (the peak-scaled clean reference written
    alongside each mixture) rather than the raw source FLAC. This is the correct
    clean reference because it has received the same peak normalization as the
    mixture, making mix - clean_ref a valid noise estimate.
    """
    random.seed(seed)

    with open(manifest_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    print(f"\n=== INDEPENDENT SNR AUDIT (using clean_ref_path) ===")
    print(f"Manifest: {manifest_path}  ({len(rows)} total rows)")

    if n_sample is not None and n_sample < len(rows):
        sampled_rows = random.sample(rows, n_sample)
        print(f"Sampling {n_sample} / {len(rows)} rows for audit.")
    else:
        sampled_rows = rows
        print(f"Auditing ALL {len(rows)} rows.")

    devs = []
    sample_log = []
    normalized_count = 0

    for row in sampled_rows:
        mix_path = row["output_path"]
        clean_ref_path_col = row.get("clean_ref_path", "")
        target_snr = float(row["snr_db"])
        norm_factor = float(row.get("norm_factor", 1.0))

        if norm_factor < 1.0:
            normalized_count += 1

        if not os.path.exists(mix_path):
            print(f"  [SKIP] Mixture file not found: {mix_path}")
            continue
        if not clean_ref_path_col or not os.path.exists(clean_ref_path_col):
            print(f"  [SKIP] clean_ref not found: {clean_ref_path_col}")
            continue

        mix_raw, _ = sf.read(mix_path, dtype="float32")
        ref_raw, _ = sf.read(clean_ref_path_col, dtype="float32")
        if mix_raw.ndim > 1: mix_raw = mix_raw[:, 0]
        if ref_raw.ndim > 1: ref_raw = ref_raw[:, 0]

        min_len = min(len(mix_raw), len(ref_raw))
        m = mix_raw[:min_len]
        r = ref_raw[:min_len]

        noise_est = m - r
        ref_pwr = float(np.mean(r ** 2))
        noise_pwr = float(np.mean(noise_est ** 2))

        if ref_pwr <= 1e-10 or noise_pwr <= 1e-10:
            print(f"  [SKIP] Zero power in {mix_path}")
            continue

        reloaded_snr = 10.0 * np.log10(ref_pwr / noise_pwr)
        dev = reloaded_snr - target_snr
        abs_dev = abs(dev)
        devs.append(abs_dev)

        sample_log.append({
            "mix_file": os.path.basename(mix_path),
            "target_snr_db": target_snr,
            "reloaded_snr_db": round(reloaded_snr, 6),
            "dev_db": round(dev, 6),
            "abs_dev_db": round(abs_dev, 6),
            "mix_peak": round(float(np.max(np.abs(m))), 4),
            "norm_factor": round(norm_factor, 6),
        })

    if not devs:
        print("\n[ERROR] No files could be audited.")
        return

    devs_arr = np.array(devs)

    print(f"\n--- Aggregate SNR Deviation (absolute value, dB) ---")
    print(f"  Files Audited        : {len(devs)}")
    print(f"  Files Peak-Normalized: {normalized_count}")
    print(f"  Mean |dev|           : {np.mean(devs_arr):.6f} dB")
    print(f"  Max  |dev|           : {np.max(devs_arr):.6f} dB")
    print(f"  Min  |dev|           : {np.min(devs_arr):.6f} dB")
    print(f"  Std  |dev|           : {np.std(devs_arr):.6f} dB")
    print(f"  P95  |dev|           : {np.percentile(devs_arr, 95):.6f} dB")

    signed_devs = np.array([r["dev_db"] for r in sample_log])
    print(f"\n--- Signed deviation (non-zero mean => systematic bias) ---")
    print(f"  Mean signed dev : {np.mean(signed_devs):.6f} dB")
    print(f"  Std  signed dev : {np.std(signed_devs):.6f} dB")

    print(f"\n--- Individual file samples (first 10 shown) ---")
    print(f"  {'Mixture File':<45} {'Target':>8} {'Reloaded':>12} {'Dev':>10} {'MixPeak':>9} {'NormFact':>10}")
    print(f"  {'-'*45} {'-'*8} {'-'*12} {'-'*10} {'-'*9} {'-'*10}")
    for r in sample_log[:10]:
        print(f"  {r['mix_file']:<45} {r['target_snr_db']:>8.1f} {r['reloaded_snr_db']:>12.6f} {r['dev_db']:>+10.6f} {r['mix_peak']:>9.4f} {r['norm_factor']:>10.6f}")

    print(f"\n--- Clipping check (mix peak > 0.95 = distortion) ---")
    clipped = [r for r in sample_log if r["mix_peak"] > 0.95]
    print(f"  Files with mix peak > 0.95 : {len(clipped)} / {len(sample_log)}")

    return devs_arr, sample_log


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Independent on-disk SNR audit for PS26052 mixtures")
    parser.add_argument("--manifest", default="data/manifest.csv")
    parser.add_argument("--clean-dir", default="data/clean")
    parser.add_argument("--mix-dir", default="data/mixtures")
    parser.add_argument("--sample", type=int, default=None, help="Number of rows to audit (None = all)")
    parser.add_argument("--seed", type=int, default=99)
    args = parser.parse_args()
    run_audit(
        manifest_path=args.manifest,
        clean_dir=args.clean_dir,
        mix_dir=args.mix_dir,
        n_sample=args.sample,
        seed=args.seed,
    )
