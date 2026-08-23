import os
import glob
import csv
import random
import argparse
from typing import Tuple, List, Dict
import numpy as np
import soundfile as sf
import torch

import sys
sys.path.insert(0, ".")

from models.deepfilternet.df_compat import resample

TARGET_SR = 48000
SNR_LEVELS = [-5.0, 0.0, 5.0, 10.0, 15.0]

CATEGORIES = {
    "stationary": ["engine", "vehicle"],
    "non_stationary": ["helicopter", "crowd"],
    "impulsive": ["gunshot", "explosion", "artillery"]
}

def load_and_resample(filepath: str, target_sr: int = TARGET_SR) -> Tuple[np.ndarray, int]:
    """
    Loads an audio file, converts to float32 mono, and resamples to target_sr if needed.
    """
    data, orig_sr = sf.read(filepath, dtype="float32")
    if data.ndim > 1:
        data = data[:, 0]
        
    if orig_sr != target_sr:
        tensor_data = torch.from_numpy(data).unsqueeze(0)
        resampled_tensor = resample(tensor_data, orig_sr, target_sr)
        data = resampled_tensor.squeeze(0).numpy()
        
    return data, orig_sr

def compute_power(signal: np.ndarray) -> float:
    """
    Computes mean signal power (mean square amplitude).
    """
    return float(np.mean(signal ** 2))

def mix_signals(clean: np.ndarray, noise: np.ndarray, target_snr_db: float) -> Tuple[np.ndarray, np.ndarray, float, float]:
    """
    Mixes clean speech and noise to achieve exact target_snr_db.
    Returns (mixed_signal, scaled_clean, achieved_snr_db, norm_factor).

    norm_factor is the peak-normalization factor applied to the final mix
    (1.0 if no clipping occurred). scaled_clean = clean * norm_factor is
    the correct clean reference for evaluation — it must receive the same
    amplitude scale as the mixture so PESQ/STOI/SI-SNR comparisons are valid.
    """
    # Align lengths: loop or crop noise to match clean duration
    len_clean = len(clean)
    len_noise = len(noise)

    if len_noise < len_clean:
        repeat_count = int(np.ceil(len_clean / len_noise))
        noise_aligned = np.tile(noise, repeat_count)[:len_clean]
    else:
        start_idx = random.randint(0, len_noise - len_clean)
        noise_aligned = noise[start_idx:start_idx + len_clean]

    clean_pwr = compute_power(clean)
    noise_pwr = compute_power(noise_aligned)

    if clean_pwr <= 1e-10 or noise_pwr <= 1e-10:
        return clean.copy(), clean.copy(), target_snr_db, 1.0

    # Scale noise for target SNR
    target_ratio = 10.0 ** (target_snr_db / 10.0)
    scale_factor = np.sqrt(clean_pwr / (noise_pwr * target_ratio))
    scaled_noise = noise_aligned * scale_factor
    mixed = clean + scaled_noise

    # Calculate achieved post-mixing SNR before any normalization (Rule 13)
    achieved_noise_pwr = compute_power(scaled_noise)
    achieved_snr_db = 10.0 * np.log10(clean_pwr / achieved_noise_pwr) if achieved_noise_pwr > 1e-10 else target_snr_db

    # Peak normalization: scale the ENTIRE mix (clean + noise) uniformly.
    # SNR is preserved because both clean and noise are scaled by the same factor.
    # We return the norm_factor so the caller can apply the same scaling to the
    # clean reference written to disk.
    norm_factor = 1.0
    max_peak = np.max(np.abs(mixed))
    if max_peak > 0.95:
        norm_factor = 0.95 / max_peak
        mixed = mixed * norm_factor

    scaled_clean = clean * norm_factor
    return mixed, scaled_clean, float(achieved_snr_db), float(norm_factor)

def generate_dataset(clean_dir: str = "data/clean", noise_base_dir: str = "data/noise", output_dir: str = "data/mixtures", manifest_path: str = "data/manifest.csv", total_target_mixtures: int = 300, seed: int = 42):
    """
    Generates synthetic dataset and updates manifest.csv.
    """
    random.seed(seed)
    np.random.seed(seed)
    
    os.makedirs(output_dir, exist_ok=True)
    # Clear previous mixture and clean_ref wav files to ensure exact file-to-manifest parity (Rule 16)
    for pattern in ["mix_*.wav", "clean_ref_*.wav"]:
        for old_file in glob.glob(os.path.join(output_dir, pattern)):
            try:
                os.remove(old_file)
            except Exception:
                pass
    
    clean_files = glob.glob(os.path.join(clean_dir, "*.flac")) + glob.glob(os.path.join(clean_dir, "*.wav"))
    if not clean_files:
        raise FileNotFoundError(f"No clean speech files found in {clean_dir}")
        
    print(f"Loaded {len(clean_files)} clean speech file candidates.")
    
    # Discover available noise files per category and subtype
    noise_pool = {}
    for cat, subtypes in CATEGORIES.items():
        noise_pool[cat] = {}
        for sub in subtypes:
            sub_dir = os.path.join(noise_base_dir, cat, sub)
            files = glob.glob(os.path.join(sub_dir, "**", "*.wav"), recursive=True) + glob.glob(os.path.join(sub_dir, "**", "*.flac"), recursive=True)
            if files:
                noise_pool[cat][sub] = files
                print(f"  [NOISE] Category '{cat}' / Subtype '{sub}': {len(files)} files")
            else:
                print(f"  [WARNING] Category '{cat}' / Subtype '{sub}': No noise files found in {sub_dir}")
                
    # Balance target count across combinations: 3 categories x 5 SNR levels = 15 combinations
    # ~20 mixtures per combination = 300 total
    combinations = []
    for cat in CATEGORIES.keys():
        for snr in SNR_LEVELS:
            combinations.append((cat, snr))
            
    mixtures_per_combo = int(np.ceil(total_target_mixtures / len(combinations)))
    print(f"\nTargeting ~{total_target_mixtures} mixtures across {len(combinations)} combinations (~{mixtures_per_combo} per combo).")
    
    manifest_rows = []
    achieved_snr_deviations = []
    resampling_log_count = 0
    mixture_idx = 1
    
    for cat, snr_db in combinations:
        available_subtypes = [s for s in CATEGORIES[cat] if s in noise_pool[cat] and noise_pool[cat][s]]
        if not available_subtypes:
            print(f"Skipping combo ({cat}, {snr_db}dB): No noise files in category {cat}")
            continue
            
        for _ in range(mixtures_per_combo):
            clean_path = random.choice(clean_files)
            subtype = random.choice(available_subtypes)
            noise_path = random.choice(noise_pool[cat][subtype])
            
            combo_seed = seed + mixture_idx
            random.seed(combo_seed)
            np.random.seed(combo_seed)
            
            clean_audio, clean_orig_sr = load_and_resample(clean_path, TARGET_SR)
            noise_audio, noise_orig_sr = load_and_resample(noise_path, TARGET_SR)
            
            if clean_orig_sr != TARGET_SR or noise_orig_sr != TARGET_SR:
                resampling_log_count += 1
                
            mixed, scaled_clean, achieved_snr, norm_factor = mix_signals(clean_audio, noise_audio, snr_db)
            snr_dev = abs(achieved_snr - snr_db)
            achieved_snr_deviations.append(snr_dev)

            clean_id = os.path.basename(clean_path)
            noise_id = os.path.basename(noise_path)
            mix_filename = f"mix_{cat}_{subtype}_{int(snr_db)}dB_{mixture_idx:04d}.wav"
            clean_ref_filename = f"clean_ref_{cat}_{subtype}_{int(snr_db)}dB_{mixture_idx:04d}.wav"
            mix_path_out = os.path.join(output_dir, mix_filename)
            clean_ref_path = os.path.join(output_dir, clean_ref_filename)

            sf.write(mix_path_out, mixed, TARGET_SR)
            sf.write(clean_ref_path, scaled_clean, TARGET_SR)
            duration_sec = float(len(mixed) / TARGET_SR)

            manifest_rows.append({
                "clean_id": clean_id,
                "noise_id": noise_id,
                "category": cat,
                "snr_db": snr_db,
                "seed": combo_seed,
                "output_path": mix_path_out,
                "clean_ref_path": clean_ref_path,
                "subtype": subtype,
                "duration_sec": round(duration_sec, 3),
                "achieved_snr_db": round(achieved_snr, 3),
                "snr_dev_db": round(snr_dev, 4),
                "norm_factor": round(norm_factor, 6),
            })
            
            mixture_idx += 1
            
    # Write manifest.csv
    fieldnames = ["clean_id", "noise_id", "category", "snr_db", "seed", "output_path", "clean_ref_path", "subtype", "duration_sec", "achieved_snr_db", "snr_dev_db", "norm_factor"]
    with open(manifest_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)
        
    # Programmatic verification (Rule 16): verify both mix and clean_ref pair counts
    mix_disk = glob.glob(os.path.join(output_dir, "mix_*.wav"))
    ref_disk = glob.glob(os.path.join(output_dir, "clean_ref_*.wav"))
    assert len(mix_disk) == len(manifest_rows), f"Rule 16 Violation! Mix files on disk ({len(mix_disk)}) != Manifest rows ({len(manifest_rows)})"
    assert len(ref_disk) == len(manifest_rows), f"Rule 16 Violation! Clean ref files on disk ({len(ref_disk)}) != Manifest rows ({len(manifest_rows)})"
    
    mean_dev = np.mean(achieved_snr_deviations) if achieved_snr_deviations else 0.0
    max_dev = np.max(achieved_snr_deviations) if achieved_snr_deviations else 0.0
    
    print("\n=== Phase 2 Dataset Generation Complete ===")
    print(f"Total Mixtures Generated: {len(manifest_rows)}")
    print(f"Manifest Row Count Verified: {len(manifest_rows)} == {len(mix_disk)} mix files, {len(ref_disk)} clean ref files")
    print(f"Audio Sample Rate: {TARGET_SR} Hz (All verified)")
    print(f"Resampling Operations Performed: {resampling_log_count}")
    print(f"Achieved SNR Mean Deviation: {mean_dev:.4f} dB | Max Deviation: {max_dev:.4f} dB")
    print(f"Manifest saved to: {manifest_path}")
    
    return manifest_rows

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PS26052 Synthetic Dataset Generator")
    parser.add_argument("--clean-dir", default="data/clean", help="Clean speech directory")
    parser.add_argument("--noise-dir", default="data/noise", help="Base noise directory")
    parser.add_argument("--output-dir", default="data/mixtures", help="Output mixtures directory")
    parser.add_argument("--manifest", default="data/manifest.csv", help="Output manifest.csv path")
    parser.add_argument("--count", type=int, default=300, help="Total target mixtures count")
    parser.add_argument("--seed", type=int, default=42, help="Master random seed")
    
    args = parser.parse_args()
    generate_dataset(
        clean_dir=args.clean_dir,
        noise_base_dir=args.noise_dir,
        output_dir=args.output_dir,
        manifest_path=args.manifest,
        total_target_mixtures=args.count,
        seed=args.seed
    )
