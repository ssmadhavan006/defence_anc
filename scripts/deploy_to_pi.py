"""
scripts/deploy_to_pi.py — Bundles and deploys live pipeline code to the Raspberry Pi 5.

Features:
- Bundles live/, config/, demo/, models/deepfilternet/, models/noise_classifier/,
  models/dnsmos/, eval/, baselines/, requirements.txt.
- Excludes .venv/ and other build/VCS clutter. Excludes the ~1.2 GB corpus +
  baseline audio + eval_raw.csv by default (opt in with --with-corpus) --
  everything else here is small, code-only, and always needed for imports
  to succeed (see bundle_deployment()'s comment for exactly which new
  dashboard modules need which directory).
- Generates a lightweight zip archive (pi_deploy.zip).
- Provides copy instructions or automates via scp.

Usage:
    python scripts/deploy_to_pi.py --host raspberrypi.local --user codefather
    python scripts/deploy_to_pi.py --with-corpus   # also bundle the corpus for Compare Methods
"""

import os
import sys
import zipfile
import argparse
import subprocess

# Ensure repo root is on sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def bundle_deployment(with_corpus: bool = False):
    zip_path = os.path.join(_REPO_ROOT, "pi_deploy.zip")
    print(f"Creating clean deployment bundle: {zip_path}")

    # Files/folders to include. Dashboard rebuild (2026-09-05) added real
    # imports the old lightweight bundle never carried:
    #   - live/stage_metrics.py imports eval/metrics.py (SI-SNR/STOI/PESQ-WB)
    #   - demo/webdash/record_compare.py imports baselines/spectral_subtraction
    #     and baselines/wiener (single-file classical DSP, no manifest needed)
    #   - demo/webdash/app.py's main() imports models/noise_classifier and
    #     models/dnsmos WHEN their config.*.enabled flags are true
    # All four are small code-only dirs (no large audio), so they're in the
    # default bundle now -- a config flag enabling the classifier/DNSMOS on
    # the Pi must not also require a manual "oh, copy this dir too" step.
    includes = ["live", "config", "demo", "models/deepfilternet", "models/noise_classifier",
                "models/dnsmos", "eval", "baselines", "requirements.txt",
                "requirements-optional.txt", "README.md"]

    if with_corpus:
        # The 300-mixture corpus + classical/DFN3 baseline outputs +
        # eval_raw.csv that demo/webdash/compare.py's "Compare Methods" tab
        # needs to serve audio + audited metrics locally on the Pi. ~1.2 GB
        # total (measured 2026-09-05: data/mixtures 304M, results/baselines
        # 901M, eval_raw.csv 484K) -- trivial on a 64GB SD card, opt-in only
        # because it's a slow first copy and irrelevant if Compare Methods
        # is being demoed from the laptop instead.
        includes += ["data/mixtures", "results/baselines", "results/eval_raw.csv",
                     "results/final", "data/manifest.csv"]

    # Files/patterns to exclude
    excludes = ["__pycache__", ".pyc", ".git", ".venv", "results.csv"]
    
    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for item in includes:
            full_path = os.path.join(_REPO_ROOT, item)
            if not os.path.exists(full_path):
                print(f"[Warning] Path {item} does not exist, skipping.")
                continue
                
            if os.path.isfile(full_path):
                zipf.write(full_path, item)
                count += 1
            else:
                for root, dirs, files in os.walk(full_path):
                    # Filter out excluded directories
                    dirs[:] = [d for d in dirs if d not in excludes]
                    
                    for file in files:
                        if any(ext in file for ext in excludes) or any(ext in root for ext in excludes):
                            continue
                        
                        file_path = os.path.join(root, file)
                        archive_name = os.path.relpath(file_path, _REPO_ROOT)
                        zipf.write(file_path, archive_name)
                        count += 1
                        
    print(f"Bundle successfully created with {count} files.")
    return zip_path


def main():
    parser = argparse.ArgumentParser(description="Bundle and deploy code to Raspberry Pi 5")
    parser.add_argument("--host", default="raspberrypi", help="Raspberry Pi hostname or IP address (default: raspberrypi)")
    parser.add_argument("--user", default="codefather", help="Pi SSH username (default: codefather)")
    parser.add_argument("--dest", default="~/Downloads/defence_anc", help="Destination path on Pi (default: ~/Downloads/defence_anc)")
    parser.add_argument("--push", action="store_true", help="Attempt to push the bundle automatically via scp")
    parser.add_argument("--with-corpus", action="store_true",
                         help="Also bundle the 300-mixture corpus + baseline outputs + eval_raw.csv "
                              "(~1.2 GB) so demo/webdash/compare.py's Compare Methods tab works "
                              "locally on the Pi instead of only from the dev machine.")
    args = parser.parse_args()

    zip_path = bundle_deployment(with_corpus=args.with_corpus)
    
    print("\n" + "=" * 60)
    print("                Pi 5 Deployment Instructions                 ")
    print("=" * 60)
    print("1. Transfer the zip bundle to the Pi:")
    print(f"   scp pi_deploy.zip {args.user}@{args.host}:{args.dest}/")
    print()
    print("2. SSH into your Pi, navigate to the folder, and extract it:")
    print(f"   ssh {args.user}@{args.host}")
    print(f"   cd {args.dest}")
    print("   unzip -o pi_deploy.zip")
    print("=" * 60)
    
    if args.push:
        print("\nAttempting automatic push via SCP...")
        cmd = ["scp", zip_path, f"{args.user}@{args.host}:{args.dest}/"]
        try:
            subprocess.run(cmd, check=True)
            print("Successfully pushed bundle to the Pi!")
        except Exception as e:
            print(f"[Error] Failed to automatically transfer bundle: {e}")
            print("Please transfer the file manually using the command above.")

if __name__ == "__main__":
    main()
