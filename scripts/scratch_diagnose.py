"""Diagnoses the source of the ~9 dB SNR deviation by checking for peak normalization effects."""
import csv, soundfile as sf, numpy as np, glob, os, sys
sys.path.insert(0, ".")

with open("data/manifest.csv") as f:
    rows = list(csv.DictReader(f))

print("=== Root Cause Diagnosis: Peak Normalization vs. Mix-Minus-Clean Audit ===\n")
for row in rows[:10]:
    clean_id = row["clean_id"]
    mix_path = row["output_path"]
    target_snr = float(row["snr_db"])

    clean_files = glob.glob(os.path.join("data/clean", "**", clean_id), recursive=True)
    if not clean_files:
        continue

    clean, sr_c = sf.read(clean_files[0], dtype="float32")
    mix, sr_m = sf.read(mix_path, dtype="float32")
    if clean.ndim > 1: clean = clean[:, 0]
    if mix.ndim > 1: mix = mix[:, 0]

    min_len = min(len(clean), len(mix))
    c = clean[:min_len]
    m = mix[:min_len]

    noise_est_unscaled = m - c  # incorrect if mix was peak-normalized
    clean_pwr = np.mean(c**2)
    noise_pwr_unscaled = np.mean(noise_est_unscaled**2)
    computed_snr_unscaled = 10*np.log10(clean_pwr / noise_pwr_unscaled) if noise_pwr_unscaled > 1e-10 else 0

    # Now try scaling clean by the same factor the mix normalization would have applied
    # Peak normalization: norm_factor = 0.95 / peak(mix_unnormalized)
    # But we don't know the unnormalized peak. We can ESTIMATE it:
    # If the mix peak == 0.9500 exactly, normalization happened. Otherwise it's the real peak.
    mix_peak = float(np.max(np.abs(m)))
    clean_peak = float(np.max(np.abs(c)))

    # Try: scale clean by same ratio as if mix was normalized (estimate: mix_peak / expected_unnorm_peak)
    # Without knowing the exact unnorm peak, let's just check the ratio approach:
    # The "correct" noise estimate = m - (c * norm_factor_that_was_applied)
    # Since norm_factor is unknown post-hoc, check if clean_pwr relative is off
    fname = os.path.basename(mix_path)
    print(f"  {fname}")
    print(f"    target_snr={target_snr:.1f} dB  | computed (m - c_unscaled) = {computed_snr_unscaled:.4f} dB  | dev={computed_snr_unscaled - target_snr:.4f} dB")
    print(f"    mix_peak={mix_peak:.4f}  clean_peak={clean_peak:.4f}")

    # Duration check: if clean (FLAC) is shorter than mix, that also contributes
    print(f"    len(clean_from_disk)={len(clean)}  len(mix)={len(mix)}  min_len={min_len}")
    if len(clean) < len(mix):
        print(f"    *** CLEAN SHORTER THAN MIX: clean={len(clean)/sr_c:.2f}s mix={len(mix)/sr_m:.2f}s ***")
    print()
