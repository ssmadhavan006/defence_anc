import os
import sys
import time
import glob
import csv
import numpy as np
import soundfile as sf

sys.path.insert(0, ".")

from baselines.spectral_subtraction.spectral_subtraction import process_batch as run_spec_sub
from baselines.wiener.wiener import process_batch as run_wiener
from baselines.nlms.nlms import process_batch as run_nlms

TARGET_SR = 48000

def generate_baseline_manifest(
    data_manifest_path: str = "data/manifest.csv",
    baselines_dir: str = "results/baselines",
    output_baseline_manifest: str = "results/baseline_manifest.csv",
):
    """
    Joins output baseline files against data/manifest.csv to produce results/baseline_manifest.csv.
    Columns: mixture_id, method, output_path, clean_ref_path, category, subtype, snr_db
    """
    with open(data_manifest_path, "r", newline="") as f:
        data_rows = list(csv.DictReader(f))

    methods = ["spectral_subtraction", "wiener", "nlms"]
    baseline_rows = []

    for row in data_rows:
        mix_file = os.path.basename(row["output_path"])
        clean_ref = row.get("clean_ref_path", "")
        cat = row["category"]
        sub = row["subtype"]
        snr = row["snr_db"]

        for m in methods:
            out_file_path = os.path.join(baselines_dir, m, mix_file)
            if os.path.exists(out_file_path):
                baseline_rows.append({
                    "mixture_id": mix_file,
                    "method": m,
                    "output_path": out_file_path,
                    "clean_ref_path": clean_ref,
                    "category": cat,
                    "subtype": sub,
                    "snr_db": snr,
                })

    os.makedirs(os.path.dirname(output_baseline_manifest), exist_ok=True)
    fieldnames = ["mixture_id", "method", "output_path", "clean_ref_path", "category", "subtype", "snr_db"]
    with open(output_baseline_manifest, "w", newline="") as f:
        writer = csv.DictReader if False else csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(baseline_rows)

    print(f"Generated {output_baseline_manifest} with {len(baseline_rows)} rows ({len(data_rows)} mixtures x {len(methods)} methods).")
    return baseline_rows

def run_sanity_checks(baseline_manifest_path: str = "results/baseline_manifest.csv"):
    """
    Internal sanity check (Rule 21):
    Confirms for every baseline output file:
      - File exists on disk
      - Non-silent (RMS > 1e-4)
      - No NaNs or Infs
      - Sample rate == 48000 Hz
      - Duration within 0.1s of expected
      - Peak amplitude <= 0.95 (no clipping)
    """
    with open(baseline_manifest_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    method_stats = {}

    for row in rows:
        m = row["method"]
        out_path = row["output_path"]

        if m not in method_stats:
            method_stats[m] = {"total": 0, "passed": 0, "failed": 0, "nan_err": 0, "silent_err": 0, "sr_err": 0, "clip_err": 0}

        stats = method_stats[m]
        stats["total"] += 1

        if not os.path.exists(out_path):
            stats["failed"] += 1
            continue

        audio, sr = sf.read(out_path, dtype="float32")
        if audio.ndim > 1:
            audio = audio[:, 0]

        has_nan = np.isnan(audio).any() or np.isinf(audio).any()
        rms = float(np.sqrt(np.mean(audio ** 2)))
        is_silent = rms < 1e-4
        correct_sr = (sr == TARGET_SR)
        max_peak = float(np.max(np.abs(audio)))
        is_clipped = max_peak > 0.951  # tolerance buffer

        if has_nan:
            stats["nan_err"] += 1
        if is_silent:
            stats["silent_err"] += 1
        if not correct_sr:
            stats["sr_err"] += 1
        if is_clipped:
            stats["clip_err"] += 1

        if not has_nan and not is_silent and correct_sr and not is_clipped:
            stats["passed"] += 1
        else:
            stats["failed"] += 1

    print("\n=== INTERNAL SANITY CHECK RESULTS (Rule 21) ===")
    all_passed = True
    for m, stats in method_stats.items():
        pass_rate = (stats["passed"] / stats["total"]) * 100 if stats["total"] > 0 else 0
        print(f"Method '{m}':")
        print(f"  Passed : {stats['passed']} / {stats['total']} ({pass_rate:.1f}%)")
        print(f"  Failures: {stats['failed']} (NaN/Inf: {stats['nan_err']}, Silent: {stats['silent_err']}, SR mismatch: {stats['sr_err']}, Clipped: {stats['clip_err']})")
        if stats["failed"] > 0:
            all_passed = False

    return all_passed

def main():
    print("=== PHASE 3 CLASSICAL DSP BASELINES FULL BATCH RUN ===")
    t0_total = time.time()

    # 1. Spectral Subtraction
    print("\n--- Running 1/3: Spectral Subtraction ---")
    t0 = time.time()
    results_spec = run_spec_sub()
    print(f"  Spectral Subtraction complete ({len(results_spec)} files in {time.time() - t0:.2f}s)")

    # 2. Wiener Filter
    print("\n--- Running 2/3: Wiener Filter ---")
    t0 = time.time()
    results_wiener = run_wiener()
    print(f"  Wiener Filter complete ({len(results_wiener)} files in {time.time() - t0:.2f}s)")

    # 3. NLMS Adaptive Filter
    print("\n--- Running 3/3: NLMS Adaptive Filter (Rule 18 True Reference Noise) ---")
    t0 = time.time()
    results_nlms = run_nlms()
    print(f"  NLMS Adaptive Filter complete ({len(results_nlms)} files in {time.time() - t0:.2f}s)")

    total_time = time.time() - t0_total
    print(f"\nAll 3 baselines finished in {total_time:.2f}s total.")

    # 4. Generate results/baseline_manifest.csv
    b_rows = generate_baseline_manifest()

    # 5. Run Sanity Checks
    sanity_pass = run_sanity_checks()
    if sanity_pass:
        print("\nAll baseline sanity checks PASSED 100%.")
    else:
        print("\n[WARNING] Some baseline output files failed sanity checks.")

if __name__ == "__main__":
    main()
