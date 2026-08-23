import os
import sys
import csv
import glob
import random
import numpy as np
import soundfile as sf
from scipy.signal import correlate

sys.path.insert(0, ".")
from baselines.nlms.nlms import load_and_prep_audio, TARGET_SR

def investigate_alignment(manifest_path="data/manifest.csv", noise_base_dir="data/noise"):
    with open(manifest_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    # Pick 5 mixtures across categories
    sample_indices = [0, 40, 100, 150, 200]
    sample_rows = [rows[i] for i in sample_indices if i < len(rows)]

    print("=== NLMS ALIGNMENT INVESTIGATION (Cross-Correlation Audit) ===\n")
    print(f"{'Mixture File':<42} {'Category':<15} {'Subtype':<12} {'Lag (samples)':>13} {'Peak Corr':>10}")
    print("-" * 96)

    for row in sample_rows:
        mix_path = row["output_path"]
        clean_ref_path = row["clean_ref_path"]
        noise_id = row["noise_id"]
        cat = row["category"]
        sub = row["subtype"]
        combo_seed = int(row["seed"])
        mix_file = os.path.basename(mix_path)

        # 1. Load mix and clean_ref
        mix_audio = load_and_prep_audio(mix_path, TARGET_SR)
        clean_ref_audio = load_and_prep_audio(clean_ref_path, TARGET_SR)

        min_len = min(len(mix_audio), len(clean_ref_audio))
        mix_aligned = mix_audio[:min_len]
        clean_aligned = clean_ref_audio[:min_len]

        # Reconstruct actual embedded noise
        embedded_noise = mix_aligned - clean_aligned

        # 2. Load reference noise as nlms.py currently loads it (from sample 0)
        matches = glob.glob(os.path.join(noise_base_dir, cat, sub, "**", noise_id), recursive=True)
        if not matches:
            matches = glob.glob(os.path.join(noise_base_dir, "**", noise_id), recursive=True)
        ref_noise_path = matches[0]
        raw_ref_noise = load_and_prep_audio(ref_noise_path, TARGET_SR)

        # 3. Cross-correlation between embedded noise and raw_ref_noise (sample 0)
        # Use a 1-second segment (48,000 samples) to compute fast correlation
        seg_len = min(48000, len(embedded_noise), len(raw_ref_noise))
        emb_seg = embedded_noise[:seg_len] - np.mean(embedded_noise[:seg_len])
        ref_seg = raw_ref_noise[:seg_len] - np.mean(raw_ref_noise[:seg_len])

        # Cross correlation
        corr = correlate(raw_ref_noise[:seg_len * 2], emb_seg, mode="valid")
        peak_idx = int(np.argmax(corr))
        max_corr = float(corr[peak_idx] / (np.linalg.norm(emb_seg) * np.linalg.norm(raw_ref_noise[peak_idx:peak_idx+seg_len]) + 1e-10))

        # Check what the actual seed-reconstructed start_idx was
        random.seed(combo_seed)
        clean_len_seed = len(clean_aligned)
        noise_len_seed = len(raw_ref_noise)
        if noise_len_seed < clean_len_seed:
            expected_start_idx = 0
        else:
            expected_start_idx = random.randint(0, noise_len_seed - clean_len_seed)

        print(f"{mix_file:<42} {cat:<15} {sub:<12} {peak_idx:>13d} {max_corr:>10.4f}  (Expected start_idx from seed={expected_start_idx})")

if __name__ == "__main__":
    investigate_alignment()
