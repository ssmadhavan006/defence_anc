import os
import sys
import csv
import glob
import random
import numpy as np
import soundfile as sf

sys.path.insert(0, ".")
from baselines.nlms.nlms import nlms_adaptive_filter, load_and_prep_audio, TARGET_SR
from eval.metrics import compute_si_snr, compute_stoi

def test_fixed_nlms(manifest_path="data/manifest.csv", noise_base_dir="data/noise"):
    with open(manifest_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    sample_indices = [0, 40, 100, 150, 200]
    sample_rows = [rows[i] for i in sample_indices if i < len(rows)]

    print("=== TESTING FIXED ALIGNED NLMS ADAPTIVE FILTER ===\n")
    print(f"{'Mixture File':<42} {'Category':<15} {'Noisy SI-SNR':>12} {'NLMS SI-SNR':>12} {'dSI-SNR':>10} {'STOI':>8}")
    print("-" * 105)

    for row in sample_rows:
        mix_path = row["output_path"]
        clean_ref_path = row["clean_ref_path"]
        noise_id = row["noise_id"]
        cat = row["category"]
        sub = row["subtype"]
        combo_seed = int(row["seed"])
        mix_file = os.path.basename(mix_path)

        primary_audio = load_and_prep_audio(mix_path, TARGET_SR)
        clean_ref_audio = load_and_prep_audio(clean_ref_path, TARGET_SR)

        # 1. Trace noise file
        matches = glob.glob(os.path.join(noise_base_dir, cat, sub, "**", noise_id), recursive=True)
        if not matches:
            matches = glob.glob(os.path.join(noise_base_dir, "**", noise_id), recursive=True)
        ref_noise_path = matches[0]

        # 2. Replicate seed-based noise trimming/alignment exactly as done in mix_dataset.py
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

        # 3. Run NLMS with aligned reference audio
        enhanced = nlms_adaptive_filter(primary_audio, ref_aligned, filter_length=64, mu=0.1)

        # Peak protection
        peak = np.max(np.abs(enhanced))
        if peak > 0.95:
            enhanced = enhanced * (0.95 / peak)

        # 4. Compute metrics
        noisy_si_snr = compute_si_snr(clean_ref_audio, primary_audio)
        nlms_si_snr = compute_si_snr(clean_ref_audio, enhanced)
        delta_si_snr = nlms_si_snr - noisy_si_snr
        stoi_val = compute_stoi(clean_ref_audio, enhanced, fs=TARGET_SR)

        print(f"{mix_file:<42} {cat:<15} {noisy_si_snr:>12.2f} {nlms_si_snr:>12.2f} {delta_si_snr:>+10.2f} {stoi_val:>8.4f}")

if __name__ == "__main__":
    test_fixed_nlms()
