import csv
import glob
import os

def trace_noise_ids(manifest_path="data/manifest.csv", noise_base_dir="data/noise"):
    with open(manifest_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    print(f"Total manifest rows: {len(rows)}")
    sample_row = rows[0]
    print("Sample manifest row:")
    for k, v in sample_row.items():
        print(f"  {k}: {v}")

    untraced = 0
    traced_map = {}

    for row in rows:
        nid = row["noise_id"]
        cat = row["category"]
        sub = row["subtype"]
        
        # Primary lookup: category / subtype
        matches = glob.glob(os.path.join(noise_base_dir, cat, sub, "**", nid), recursive=True)
        if not matches:
            # Fallback lookup: anywhere under noise_base_dir
            matches = glob.glob(os.path.join(noise_base_dir, "**", nid), recursive=True)

        if matches:
            traced_map[row["output_path"]] = matches[0]
        else:
            untraced += 1
            print(f"  [UNTRACED] noise_id '{nid}' (cat={cat}, sub={sub})")

    print(f"\nTrace Audit Result: {len(rows) - untraced} / {len(rows)} rows successfully traced to disk.")
    if len(rows) > 0 and untraced == 0:
        sample_mix = list(traced_map.keys())[0]
        print(f"Sample mapping:")
        print(f"  Mixture WAV  : {sample_mix}")
        print(f"  Reference WAV: {traced_map[sample_mix]}")

if __name__ == "__main__":
    trace_noise_ids()
