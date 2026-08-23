import os
import sys
import csv
import glob
import random
import numpy as np
import soundfile as sf
from scipy.signal import correlate

sys.path.insert(0, ".")
from baselines.nlms.nlms import nlms_adaptive_filter, load_and_prep_audio, TARGET_SR
from eval.metrics import compute_si_snr, compute_stoi

def check_impulsive_alignment(manifest_path="data/manifest.csv", noise_base_dir="data/noise"):
    with open(manifest_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    impulsive_rows = [r for r in rows if r["category"] == "impulsive"]
    sample_impulsive = impulsive_rows[:3]

    print("=== IMPULSIVE CATEGORY ALIGNMENT RE-CHECK ===")
    for row in sample_impulsive:
        mix_path = row["output_path"]
        clean_ref_path = row["clean_ref_path"]
        noise_id = row["noise_id"]
        sub = row["subtype"]
        combo_seed = int(row["seed"])
        mix_file = os.path.basename(mix_path)

        mix_audio = load_and_prep_audio(mix_path, TARGET_SR)
        clean_ref_audio = load_and_prep_audio(clean_ref_path, TARGET_SR)
        min_len = min(len(mix_audio), len(clean_ref_audio))
        embedded_noise = mix_audio[:min_len] - clean_ref_audio[:min_len]

        matches = glob.glob(os.path.join(noise_base_dir, "impulsive", sub, "**", noise_id), recursive=True)
        if not matches:
            matches = glob.glob(os.path.join(noise_base_dir, "**", noise_id), recursive=True)
        ref_noise_path = matches[0]

        random.seed(combo_seed)
        np.random.seed(combo_seed)
        raw_ref_noise = load_and_prep_audio(ref_noise_path, TARGET_SR)

        len_clean = min_len
        len_ref = len(raw_ref_noise)
        if len_ref < len_clean:
            repeat_count = int(np.ceil(len_clean / len_ref))
            ref_aligned = np.tile(raw_ref_noise, repeat_count)[:len_clean]
        else:
            start_idx = random.randint(0, len_ref - len_clean)
            ref_aligned = raw_ref_noise[start_idx : start_idx + len_clean]

        # Verify cross-correlation lag between embedded noise and ref_aligned
        corr = correlate(ref_aligned[:24000], embedded_noise[:24000], mode="same")
        mid = len(corr) // 2
        lag = np.argmax(corr) - mid
        max_corr = float(np.max(corr) / (np.linalg.norm(ref_aligned[:24000]) * np.linalg.norm(embedded_noise[:24000]) + 1e-10))

        print(f"  {mix_file} ({sub}): Lag={lag} samples | Normalized Correlation Peak={max_corr:.4f}")

def run_nlms_ablation(manifest_path="data/manifest.csv", noise_base_dir="data/noise"):
    with open(manifest_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    print("\n=== NLMS ABLATION STUDY (Alignment Alone @ mu=0.10 vs. Aligned + mu=0.01) ===")
    
    results_mu010 = []
    results_mu001 = []

    for row in rows:
        mix_path = row["output_path"]
        clean_ref_path = row["clean_ref_path"]
        noise_id = row["noise_id"]
        cat = row["category"]
        sub = row["subtype"]
        combo_seed = int(row["seed"])
        mix_file = os.path.basename(mix_path)

        primary_audio = load_and_prep_audio(mix_path, TARGET_SR)
        clean_ref_audio = load_and_prep_audio(clean_ref_path, TARGET_SR)

        matches = glob.glob(os.path.join(noise_base_dir, cat, sub, "**", noise_id), recursive=True)
        if not matches:
            matches = glob.glob(os.path.join(noise_base_dir, "**", noise_id), recursive=True)
        ref_noise_path = matches[0]

        random.seed(combo_seed)
        np.random.seed(combo_seed)
        ref_audio = load_and_prep_audio(ref_noise_path, TARGET_SR)

        len_clean = len(primary_audio)
        len_ref = len(ref_audio)
        if len_ref < len_clean:
            repeat_count = int(np.ceil(len_clean / len_ref))
            ref_aligned = np.tile(ref_audio, repeat_count)[:len_clean]
        else:
            start_idx = random.randint(0, len_ref - len_clean)
            ref_aligned = ref_audio[start_idx : start_idx + len_clean]

        noisy_si = compute_si_snr(clean_ref_audio, primary_audio)

        # Run mu = 0.10
        enh_010 = nlms_adaptive_filter(primary_audio, ref_aligned, filter_length=64, mu=0.10)
        p1 = np.max(np.abs(enh_010))
        if p1 > 0.95: enh_010 = enh_010 * (0.95 / p1)
        si_010 = compute_si_snr(clean_ref_audio, enh_010)
        stoi_010 = compute_stoi(clean_ref_audio, enh_010, fs=TARGET_SR)

        # Run mu = 0.01
        enh_001 = nlms_adaptive_filter(primary_audio, ref_aligned, filter_length=64, mu=0.01)
        p2 = np.max(np.abs(enh_001))
        if p2 > 0.95: enh_001 = enh_001 * (0.95 / p2)
        si_001 = compute_si_snr(clean_ref_audio, enh_001)
        stoi_001 = compute_stoi(clean_ref_audio, enh_001, fs=TARGET_SR)

        results_mu010.append({"category": cat, "delta_si_snr": si_010 - noisy_si, "stoi": stoi_010})
        results_mu001.append({"category": cat, "delta_si_snr": si_001 - noisy_si, "stoi": stoi_001})

    import pandas as pd
    df10 = pd.DataFrame(results_mu010)
    df01 = pd.DataFrame(results_mu001)

    print("\n--- Category Summary: Aligned @ mu=0.10 (Original Step Size) ---")
    g10 = df10.groupby("category").agg(mean_delta_si_snr=("delta_si_snr", "mean"), mean_stoi=("stoi", "mean"))
    print(g10.to_string())

    print("\n--- Category Summary: Aligned @ mu=0.01 (Retuned Step Size) ---")
    g01 = df01.groupby("category").agg(mean_delta_si_snr=("delta_si_snr", "mean"), mean_stoi=("stoi", "mean"))
    print(g01.to_string())

if __name__ == "__main__":
    check_impulsive_alignment()
    run_nlms_ablation()
