"""
models/dnsmos/download_model.py — Fetch sig_bak_ovr.onnx from the DNS Challenge repo.

Usage:
    python models/dnsmos/download_model.py

The model is MIT-licensed (Microsoft DNS-Challenge, see SOURCES.md).
After downloading, verify the SHA-256 and record it in SOURCES.md.
"""

import hashlib
import os
import sys
import urllib.request

_MODEL_URL = (
    "https://github.com/microsoft/DNS-Challenge/raw/591184a9fcb2cbdec02520fed81a32bbbf9d73ff/"
    "DNSMOS/DNSMOS/sig_bak_ovr.onnx"
)
# NOTE (2026-09-05): the originally-pinned commit 5e8a990 (2022-05-10) no longer
# exists anywhere in the upstream repo's history (GitHub API returns "No commit
# found for SHA" -- confirmed via `curl api.github.com/repos/microsoft/DNS-Challenge/commits/5e8a990`),
# most likely a force-push history rewrite upstream, not something recoverable
# from this side. Re-pinned to the current master HEAD at time of writing.
# IMPORTANT: this file is ~1.1 MB, not the ~4.8 MB originally recorded in
# SOURCES.md for the 2022 commit -- it may be a retrained/updated checkpoint,
# not byte-identical to what this project originally validated against. See
# SOURCES.md for the full note; re-verify DNSMOS output sanity (dnsmos_infer.py
# --self-test's 440Hz-sine in-range check) after ever re-pinning this URL again.
_MODEL_DIR = os.path.dirname(os.path.abspath(__file__))
_MODEL_PATH = os.path.join(_MODEL_DIR, "sig_bak_ovr.onnx")


def download(force: bool = False) -> str:
    if os.path.exists(_MODEL_PATH) and not force:
        print(f"Model already present: {_MODEL_PATH}")
        return _MODEL_PATH

    print(f"Downloading DNSMOS P.835 model from DNS-Challenge repo...")
    print(f"  URL: {_MODEL_URL}")
    os.makedirs(_MODEL_DIR, exist_ok=True)

    with urllib.request.urlopen(_MODEL_URL, timeout=60) as resp:
        data = resp.read()

    sha256 = hashlib.sha256(data).hexdigest()
    with open(_MODEL_PATH, "wb") as f:
        f.write(data)

    print(f"Saved to: {_MODEL_PATH}")
    print(f"SHA-256:  {sha256}")
    print("Record the SHA-256 in models/dnsmos/SOURCES.md.")
    return _MODEL_PATH


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-download even if already present")
    args = parser.parse_args()
    try:
        download(force=args.force)
    except Exception as e:
        print(f"ERROR: {e}")
        print("Download manually from:")
        print(f"  {_MODEL_URL}")
        print(f"and save to: {_MODEL_PATH}")
        sys.exit(1)
