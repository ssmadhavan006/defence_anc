import os
import sys
import time
import requests
import tarfile
import zipfile
import glob
import shutil

LIBRISPEECH_URL = "http://www.openslr.org/resources/12/dev-clean.tar.gz"
ESC50_URL = "https://github.com/karolpiczak/ESC-50/archive/refs/heads/master.zip"

def download_file(url: str, dest_path: str, retries: int = 10):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0"}

    for attempt in range(1, retries + 1):
        file_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
        req_headers = headers.copy()
        if file_size > 0:
            req_headers["Range"] = f"bytes={file_size}-"
            print(f"[RESUMING] {url} -> {dest_path} from {file_size / 1e6:.1f} MB (Attempt {attempt}/{retries})...")
        else:
            print(f"[DOWNLOADING] {url} -> {dest_path} (Attempt {attempt}/{retries})...")

        try:
            r = requests.get(url, headers=req_headers, stream=True, timeout=20)
            if r.status_code == 416:
                print(f"[SKIP] Archive already fully downloaded at {dest_path}")
                return
            r.raise_for_status()

            if r.status_code == 206:
                content_range = r.headers.get("content-range", "")
                total_size = int(content_range.split("/")[-1]) if "/" in content_range else 0
                mode = "ab"
                downloaded = file_size
            else:
                total_size = int(r.headers.get("content-length", 0))
                mode = "wb"
                downloaded = 0

            with open(dest_path, mode) as f:
                for chunk in r.iter_content(chunk_size=512 * 1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = downloaded * 100 / total_size
                            sys.stdout.write(f"\r  Progress: {downloaded / 1e6:.1f} MB / {total_size / 1e6:.1f} MB ({percent:.1f}%)")
                            sys.stdout.flush()

            print("\n  Download complete!")
            return
        except Exception as e:
            print(f"\n  Download connection error (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(3)

    raise RuntimeError(f"Failed to download {url} after {retries} attempts.")

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


ZENODO_GUNSHOT_URL = "https://zenodo.org/api/records/7004819/files/edge-collected-gunshot-audio.zip/content"
ZENODO_RECORD_PAGE = "https://zenodo.org/records/7004819"


def setup_gunshot(archive_path: str, noise_base_dir: str, artillery_source_type: str = "remington_870_12_gauge", artillery_count: int = 30):
    """
    Extracts the Zenodo gunshot corpus and splits it into `gunshot` (the full
    corpus, all firearm types) and `artillery` (a proxy subset drawn from the
    highest-energy/largest-caliber firearm type) noise subtypes.

    NOTE on automated download: Zenodo's anti-bot rate limiting blocks
    scripted requests to this record ("Access to this resource has been
    restricted due to unusual traffic from your network"), even a single
    HEAD request, from at least some networks -- this is not something
    retry/resume logic can fix. If `archive_path` doesn't exist, download it
    manually via a normal browser session at ZENODO_RECORD_PAGE and save it
    to `archive_path` before running this function.
    """
    if not os.path.exists(archive_path):
        raise FileNotFoundError(
            f"{archive_path} not found. Zenodo blocks automated downloads of this "
            f"record from many networks -- download it manually via a browser at "
            f"{ZENODO_RECORD_PAGE} and save it to {archive_path}, then re-run."
        )

    print("\n=== Extracting Zenodo Gunshot/Artillery Corpus ===")
    extract_temp = os.path.join("data", "temp_gunshot_extract")
    os.makedirs(extract_temp, exist_ok=True)
    with zipfile.ZipFile(archive_path, "r") as z:
        z.extractall(extract_temp)

    src_root = glob.glob(os.path.join(extract_temp, "edge-collected-gunshot-audio"))
    src_root = src_root[0] if src_root else extract_temp

    firearm_types = [d for d in os.listdir(src_root) if os.path.isdir(os.path.join(src_root, d))]
    gunshot_dir = os.path.join(noise_base_dir, "impulsive", "gunshot")
    artillery_dir = os.path.join(noise_base_dir, "impulsive", "artillery")
    os.makedirs(gunshot_dir, exist_ok=True)
    os.makedirs(artillery_dir, exist_ok=True)

    all_files = []
    for ft in firearm_types:
        all_files.extend(sorted(glob.glob(os.path.join(src_root, ft, "*.wav"))))

    for f in all_files:
        dest = os.path.join(gunshot_dir, os.path.basename(f))
        if not os.path.exists(dest):
            shutil.copy2(f, dest)

    artillery_source = sorted(glob.glob(os.path.join(src_root, artillery_source_type, "*.wav")))
    for f in artillery_source[:artillery_count]:
        dest = os.path.join(artillery_dir, os.path.basename(f))
        if not os.path.exists(dest):
            shutil.copy2(f, dest)

    print(f"Gunshot: {len(os.listdir(gunshot_dir))} files -> {gunshot_dir}")
    print(f"Artillery: {len(os.listdir(artillery_dir))} files -> {artillery_dir} (from {artillery_source_type})")
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

    gunshot_archive = os.path.join(downloads_dir, "edge-collected-gunshot-audio.zip")
    try:
        setup_gunshot(gunshot_archive, os.path.join("data", "noise"))
    except FileNotFoundError as e:
        print(f"\n[SKIP] Gunshot/artillery corpus: {e}")
