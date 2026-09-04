"""
scripts/extract_esc50_subtype.py — Extract a single named ESC-50 class into a noise subtype dir.

Added for the Phase 4.5 non_stationary corpus redefinition (docs/corpus_redefinition_v2.md).

Why this exists rather than reusing scripts/download_datasets.py::setup_esc50():
  - setup_esc50() carries a hardcoded category_map for the ORIGINAL three subtypes
    (engine/helicopter/fireworks) and re-extracts the whole 645 MB archive to a temp
    directory. This tool takes the class name as a parameter and streams only the
    matching members out of the zip, so adding a subtype does not require editing a
    dict or paying a full extractall.
  - The ESC-50 class name and the destination subtype name are decoupled
    (e.g. ESC-50 class "airplane" -> subtype directory "aircraft").

Provenance/licence is unchanged from the existing ESC-50 subtypes: ESC-50, CC BY-NC 3.0.
See data/SOURCES.md.

Usage:
    python scripts/extract_esc50_subtype.py --list
    python scripts/extract_esc50_subtype.py --class-name wind     --dest data/noise/non_stationary/wind
    python scripts/extract_esc50_subtype.py --class-name airplane --dest data/noise/non_stationary/aircraft
    python scripts/extract_esc50_subtype.py --self-test
"""

import argparse
import csv
import io
import os
import sys
import zipfile

DEFAULT_ARCHIVE = os.path.join("data", "downloads", "esc50-master.zip")


def _read_meta(z: zipfile.ZipFile):
    """Locate and parse ESC-50's meta/esc50.csv inside the archive."""
    meta_names = [n for n in z.namelist() if n.replace("\\", "/").endswith("meta/esc50.csv")]
    if not meta_names:
        raise FileNotFoundError(
            "meta/esc50.csv not found inside the archive — is this really the ESC-50 master zip?"
        )
    meta_name = meta_names[0]
    rows = list(csv.DictReader(io.StringIO(z.read(meta_name).decode("utf-8"))))
    if not rows:
        raise ValueError(f"{meta_name} parsed to zero rows")
    return rows


def list_classes(archive_path: str = DEFAULT_ARCHIVE):
    """Print every ESC-50 class name with its clip count."""
    with zipfile.ZipFile(archive_path, "r") as z:
        rows = _read_meta(z)
    counts = {}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    for name in sorted(counts):
        print(f"  {name:24s} {counts[name]}")
    return counts


def extract_class(class_name: str, dest_dir: str, archive_path: str = DEFAULT_ARCHIVE,
                  verbose: bool = True) -> list:
    """
    Copy every ESC-50 clip belonging to `class_name` into `dest_dir`.

    Files are written with their original ESC-50 filenames ({fold}-{clip}-{take}-{target}.wav)
    so each file remains traceable back to the source corpus, matching how the existing
    helicopter/engine/explosion subtypes were populated.

    Returns the list of written paths.
    """
    with zipfile.ZipFile(archive_path, "r") as z:
        rows = _read_meta(z)

        available = sorted({r["category"] for r in rows})
        if class_name not in available:
            raise ValueError(
                f"ESC-50 class {class_name!r} does not exist. Available classes:\n  "
                + "\n  ".join(available)
            )

        wanted = {r["filename"] for r in rows if r["category"] == class_name}

        # Map bare filenames to their full in-zip member paths.
        member_by_name = {}
        for n in z.namelist():
            base = n.replace("\\", "/").split("/")[-1]
            if base in wanted:
                member_by_name[base] = n

        missing = wanted - set(member_by_name)
        if missing:
            raise FileNotFoundError(
                f"{len(missing)} clip(s) listed in meta/esc50.csv for class {class_name!r} "
                f"are absent from the archive, e.g. {sorted(missing)[:3]}"
            )

        os.makedirs(dest_dir, exist_ok=True)
        written = []
        for base in sorted(wanted):
            out_path = os.path.join(dest_dir, base)
            with z.open(member_by_name[base]) as src, open(out_path, "wb") as dst:
                dst.write(src.read())
            written.append(out_path)

    if verbose:
        print(f"[extract_esc50_subtype] class={class_name!r} -> {dest_dir}  ({len(written)} files)")
    return written


def _self_test() -> bool:
    """
    Self-test (Rule 8). Runs against the real archive but writes only to a temp dir,
    so it never mutates data/noise/.
    """
    import tempfile
    import shutil

    print("extract_esc50_subtype self-test -- start")
    ok = True

    if not os.path.exists(DEFAULT_ARCHIVE):
        print(f"  [SKIP] archive not present at {DEFAULT_ARCHIVE}")
        print("extract_esc50_subtype self-test -- SKIPPED")
        return True

    tmp = tempfile.mkdtemp(prefix="esc50_selftest_")
    try:
        # test 1: metadata parses and has the canonical 2000 rows / 50 classes
        with zipfile.ZipFile(DEFAULT_ARCHIVE, "r") as z:
            rows = _read_meta(z)
        classes = {r["category"] for r in rows}
        if len(rows) == 2000 and len(classes) == 50:
            print(f"  [PASS] test 1: meta parses ({len(rows)} rows, {len(classes)} classes)")
        else:
            print(f"  [FAIL] test 1: expected 2000 rows / 50 classes, got {len(rows)} / {len(classes)}")
            ok = False

        # test 2: extracting a known class yields exactly 40 clips (ESC-50 is 40 per class)
        dest = os.path.join(tmp, "wind")
        written = extract_class("wind", dest, verbose=False)
        if len(written) == 40:
            print(f"  [PASS] test 2: class 'wind' extracted 40 clips")
        else:
            print(f"  [FAIL] test 2: expected 40 clips, got {len(written)}")
            ok = False

        # test 3: every written file exists, is non-empty, and is a readable WAV
        import soundfile as sf
        bad = []
        srs = set()
        for p in written:
            if not os.path.exists(p) or os.path.getsize(p) == 0:
                bad.append(p)
                continue
            try:
                info = sf.info(p)
                srs.add(info.samplerate)
            except Exception as e:  # noqa: BLE001 - want the real error surfaced (Rule 4)
                bad.append(f"{p}: {e}")
        if not bad:
            print(f"  [PASS] test 3: all {len(written)} clips readable, source rate(s)={sorted(srs)} Hz")
            print(f"           (mix_dataset.py resamples to 48 kHz explicitly -- Rule 14)")
        else:
            print(f"  [FAIL] test 3: {len(bad)} unreadable/empty file(s), e.g. {bad[:2]}")
            ok = False

        # test 4: an unknown class name raises rather than silently producing an empty dir
        try:
            extract_class("definitely_not_a_class", os.path.join(tmp, "nope"), verbose=False)
            print("  [FAIL] test 4: unknown class did not raise")
            ok = False
        except ValueError:
            print("  [PASS] test 4: unknown class raises ValueError")

        # test 5: extracted filenames all carry the class's ESC-50 target index suffix
        target_idx = {r["target"] for r in rows if r["category"] == "wind"}
        suffix = f"-{sorted(target_idx)[0]}.wav"
        if all(os.path.basename(p).endswith(suffix) for p in written):
            print(f"  [PASS] test 5: all filenames carry ESC-50 target suffix '{suffix}'")
        else:
            print(f"  [FAIL] test 5: filename/target suffix mismatch")
            ok = False

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("extract_esc50_subtype self-test -- " + ("ALL PASSED" if ok else "FAILURES PRESENT"))
    return ok


def main():
    ap = argparse.ArgumentParser(description="Extract one ESC-50 class into a noise subtype directory.")
    ap.add_argument("--class-name", help="ESC-50 class name, e.g. 'wind' or 'airplane'")
    ap.add_argument("--dest", help="Destination subtype directory")
    ap.add_argument("--archive", default=DEFAULT_ARCHIVE, help=f"ESC-50 zip (default: {DEFAULT_ARCHIVE})")
    ap.add_argument("--list", action="store_true", help="List all ESC-50 class names and exit")
    ap.add_argument("--self-test", action="store_true", help="Run self-test and exit")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(0 if _self_test() else 1)
    if args.list:
        list_classes(args.archive)
        return
    if not args.class_name or not args.dest:
        ap.error("--class-name and --dest are both required (or use --list / --self-test)")

    extract_class(args.class_name, args.dest, args.archive)


if __name__ == "__main__":
    main()
