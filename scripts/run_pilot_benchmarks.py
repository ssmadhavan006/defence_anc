import os
import sys
import time
import shutil
import glob
import csv

sys.path.insert(0, ".")

from baselines.spectral_subtraction.spectral_subtraction import process_batch as run_spec_sub
from baselines.wiener.wiener import process_batch as run_wiener
from baselines.nlms.nlms import process_batch as run_nlms

PILOT_COUNT = 10
TOTAL_FILES = 300
PILOT_TEMP_DIR = "results/temp_pilot_test"

def run_pilot():
    print(f"=== PILOT TIMING RUN ({PILOT_COUNT} files) ===")
    os.makedirs(PILOT_TEMP_DIR, exist_ok=True)
    
    # 1. Spectral Subtraction Pilot
    spec_dir = os.path.join(PILOT_TEMP_DIR, "spec_sub")
    shutil.rmtree(spec_dir, ignore_errors=True)
    t0 = time.time()
    run_spec_sub(manifest_path="data/manifest.csv", output_dir=spec_dir, limit=PILOT_COUNT)
    t_spec = time.time() - t0
    extrap_spec = (t_spec / PILOT_COUNT) * TOTAL_FILES
    print(f"1. Spectral Subtraction: {t_spec:.4f}s for {PILOT_COUNT} files ({t_spec/PILOT_COUNT:.4f}s/file) -> Extrapolated for 300 files: {extrap_spec:.2f}s")

    # 2. Wiener Filter Pilot
    wiener_dir = os.path.join(PILOT_TEMP_DIR, "wiener")
    shutil.rmtree(wiener_dir, ignore_errors=True)
    t0 = time.time()
    run_wiener(manifest_path="data/manifest.csv", output_dir=wiener_dir, limit=PILOT_COUNT)
    t_wiener = time.time() - t0
    extrap_wiener = (t_wiener / PILOT_COUNT) * TOTAL_FILES
    print(f"2. Wiener Filter      : {t_wiener:.4f}s for {PILOT_COUNT} files ({t_wiener/PILOT_COUNT:.4f}s/file) -> Extrapolated for 300 files: {extrap_wiener:.2f}s")

    # 3. NLMS Adaptive Filter Pilot
    nlms_dir = os.path.join(PILOT_TEMP_DIR, "nlms")
    shutil.rmtree(nlms_dir, ignore_errors=True)
    t0 = time.time()
    run_nlms(manifest_path="data/manifest.csv", noise_base_dir="data/noise", output_dir=nlms_dir, limit=PILOT_COUNT)
    t_nlms = time.time() - t0
    extrap_nlms = (t_nlms / PILOT_COUNT) * TOTAL_FILES
    print(f"3. NLMS Adaptive Filter: {t_nlms:.4f}s for {PILOT_COUNT} files ({t_nlms/PILOT_COUNT:.4f}s/file) -> Extrapolated for 300 files: {extrap_nlms:.2f}s")

    total_extrap = extrap_spec + extrap_wiener + extrap_nlms
    print(f"\nTotal Extrapolated Processing Time for All 3 Baselines (300 files each): {total_extrap:.2f}s (~{total_extrap/60:.2f} minutes)")

    shutil.rmtree(PILOT_TEMP_DIR, ignore_errors=True)
    return {
        "spec": (t_spec, extrap_spec),
        "wiener": (t_wiener, extrap_wiener),
        "nlms": (t_nlms, extrap_nlms),
        "total_extrap": total_extrap
    }

if __name__ == "__main__":
    run_pilot()
