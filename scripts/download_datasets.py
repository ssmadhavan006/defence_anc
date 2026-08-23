import os
import sys
import urllib.request
import tarfile
import zipfile
import glob
import shutil

LIBRISPEECH_URL = "http://www.openslr.org/resources/12/dev-clean.tar.gz"
ESC50_URL = "https://github.com/karolpiczak/ESC-50/archive/refs/heads/master.zip"

def download_file(url: str, dest_path: str):
    if os.path.exists(dest_path):
        print(f"[SKIP] Archive already exists at {dest_path}")
        return
    print(f"[DOWNLOADING] {url} -> {dest_path}...")
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    def reporthook(blocknum, blocksize, totalsize):
        readsofar = blocknum * blocksize
        if totalsize > 0:
            percent = readsofar * 100 / totalsize
            sys.stdout.write(f"\r  Progress: {readsofar / 1e6:.1f} MB / {totalsize / 1e6:.1f} MB ({percent:.1f}%)")
            sys.stdout.flush()
    urllib.request.urlretrieve(url, dest_path, reporthook)
    print("\n  Download complete!")

def setup_librispeech(archive_path: str, target_dir: str, max_files: int = 150):
    print("\n=== Extracting LibriSpeech dev-clean ===")
    os.makedirs(target_dir, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        members = [m for m in tar.getmembers() if m.name.endswith(".flac")]
        print(f"Total .flac audio files in archive: {len(members)}")
        selected = members[:max_files]
        for m in selected:
            # Extract to target_dir
            filename = os.path.basename(m.name)
            out_file = os.path.join(target_dir, filename)
            if not os.path.exists(out_file):
                f = tar.extractfile(m)
                if f is not None:
                    with open(out_file, "wb") as out:
                        out.write(f.read())
    flac_files = glob.glob(os.path.join(target_dir, "*.flac"))
    print(f"Extracted {len(flac_files)} clean speech files into {target_dir}")
    return flac_files

def setup_esc50(archive_path: str, noise_base_dir: str):
    print("\n=== Extracting ESC-50 Noise Categories ===")
    extract_temp = os.path.join("data", "temp_esc50")
    os.makedirs(extract_temp, exist_ok=True)
    with zipfile.ZipFile(archive_path, "r") as z:
        z.extractall(extract_temp)
        
    csv_file = glob.glob(os.path.join(extract_temp, "**", "esc50.csv"), recursive=True)[0]
    root_dir = os.path.dirname(os.path.dirname(csv_file))
    audio_dir = os.path.join(root_dir, "audio")
    
    import csv
    category_map = {
        "engine": [os.path.join(noise_base_dir, "stationary", "engine"), os.path.join(noise_base_dir, "stationary", "vehicle")],
        "helicopter": [os.path.join(noise_base_dir, "non_stationary", "helicopter")],
        "fireworks": [os.path.join(noise_base_dir, "impulsive", "explosion")]
    }
    
    for targets in category_map.values():
        for t in targets:
            os.makedirs(t, exist_ok=True)
            
    counts = {cat: 0 for cat in category_map}
    with open(csv_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cat = row["category"]
            if cat in category_map:
                src = os.path.join(audio_dir, row["filename"])
                if os.path.exists(src):
                    for target_dir in category_map[cat]:
                        dest = os.path.join(target_dir, row["filename"])
                        shutil.copy2(src, dest)
                    counts[cat] += 1
                    
    print(f"ESC-50 extracted categories: {counts}")
    shutil.rmtree(extract_temp, ignore_errors=True)

if __name__ == "__main__":
    downloads_dir = os.path.join("data", "downloads")
    os.makedirs(downloads_dir, exist_ok=True)
    
    libri_archive = os.path.join(downloads_dir, "dev-clean.tar.gz")
    esc_archive = os.path.join(downloads_dir, "esc50-master.zip")
    
    download_file(LIBRISPEECH_URL, libri_archive)
    download_file(ESC50_URL, esc_archive)
    
    setup_librispeech(libri_archive, os.path.join("data", "clean"))
    setup_esc50(esc_archive, os.path.join("data", "noise"))
