"""
scripts/sweep_atten_lim.py — Phase 3 T4: per-category atten_lim_db / post_filter sweep.

Stage 1 (D2): sweeps a stratified subset (20 mixtures per category, 4 per SNR level = 60 files total)
across the grid atten_lim_db in {30, 50, 70, 85, 100} x post_filter in {off, on}, dispatched per category
since --atten-lim/--post-filter are global DeepFilterNet3 knobs with no built-in per-category mechanism
(phase3_plan.md Sec 3.1(b)). Writes results/atten_sweep.csv with columns:
category, atten_lim_db, post_filter, pesq_wb, stoi, si_snr, n.

Never touches results/baselines/deepfilternet/ (the committed baseline) or data/mixtures/ -- all sweep
inference outputs go to results/atten_sweep_outputs/<category>_<atten>_<pf>/, all skip-if-exists
(Rule 20 resumable).
"""

import os
import sys
import csv
import argparse
import random

sys.path.insert(0, ".")
import soundfile as sf
from eval.metrics import compute_si_snr, compute_stoi, compute_pesq_wb
from models.deepfilternet.run_inference import process_manifest

TARGET_SR = 48000
CATEGORIES = ["stationary", "non_stationary", "impulsive"]
SNR_LEVELS = [-5.0, 0.0, 5.0, 10.0, 15.0]
ATTEN_GRID = [30, 50, 70, 85, 100]
POST_FILTER_GRID = [False, True]
PER_CATEGORY_PER_SNR = 4  # 4 x 5 SNR levels x 3 categories = 60-file stratified subset


def build_stratified_subset(manifest_path: str = "data/manifest.csv", seed: int = 42) -> dict:
    """
    Deterministically selects PER_CATEGORY_PER_SNR mixtures per (category, snr_db) cell.
    Returns {category: [row, ...]} -- 20 rows per category, 60 total.
    """
    with open(manifest_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    by_cell = {}
    for row in rows:
        key = (row["category"], float(row["snr_db"]))
        by_cell.setdefault(key, []).append(row)

    rng = random.Random(seed)
    subset = {cat: [] for cat in CATEGORIES}
    for cat in CATEGORIES:
        for snr in SNR_LEVELS:
            cell_rows = sorted(by_cell.get((cat, snr), []), key=lambda r: r["output_path"])
            picked = rng.sample(cell_rows, min(PER_CATEGORY_PER_SNR, len(cell_rows)))
            subset[cat].extend(picked)
    return subset


def _write_subset_manifest(rows: list, path: str):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def evaluate_outputs(rows: list, output_dir: str) -> dict:
    """Computes mean PESQ-WB / STOI / SI-SNR over `rows`' DeepFilterNet outputs in output_dir."""
    pesq_vals, stoi_vals, si_snr_vals = [], [], []
    for row in rows:
        mix_filename = os.path.basename(row["output_path"])
        deg_path = os.path.join(output_dir, mix_filename)
        ref_path = row["clean_ref_path"]
        if not os.path.exists(deg_path) or not os.path.exists(ref_path):
            continue
        ref_audio, _ = sf.read(ref_path, dtype="float32")
        deg_audio, _ = sf.read(deg_path, dtype="float32")
        si_snr_vals.append(compute_si_snr(ref_audio, deg_audio))
        stoi_vals.append(compute_stoi(ref_audio, deg_audio, fs=TARGET_SR))
        try:
            pesq_vals.append(compute_pesq_wb(ref_audio, deg_audio, fs=TARGET_SR))
        except Exception:
            pass  # PESQ can reject pathological clips; STOI/SI-SNR still count (Rule 24 spirit -- see n column)

    n = len(stoi_vals)
    return {
        "pesq_wb": sum(pesq_vals) / len(pesq_vals) if pesq_vals else float("nan"),
        "stoi": sum(stoi_vals) / n if n else float("nan"),
        "si_snr": sum(si_snr_vals) / n if n else float("nan"),
        "n": n,
        "n_pesq": len(pesq_vals),
    }


def run_sweep(
    manifest_path: str = "data/manifest.csv",
    output_root: str = "results/atten_sweep_outputs",
    sweep_csv_path: str = "results/atten_sweep.csv",
    atten_grid: list = None,
    pf_grid: list = None,
    seed: int = 42,
) -> list:
    atten_grid = atten_grid if atten_grid is not None else ATTEN_GRID
    pf_grid = pf_grid if pf_grid is not None else POST_FILTER_GRID

    subset = build_stratified_subset(manifest_path, seed=seed)
    for cat, rows in subset.items():
        print(f"  stratified subset[{cat}]: {len(rows)} files")

    os.makedirs(output_root, exist_ok=True)
    os.makedirs(os.path.dirname(sweep_csv_path), exist_ok=True)

    # Resumable: load any already-computed grid points (Rule 20).
    existing = {}
    if os.path.exists(sweep_csv_path):
        with open(sweep_csv_path, "r", newline="") as f:
            for r in csv.DictReader(f):
                existing[(r["category"], int(float(r["atten_lim_db"])), r["post_filter"])] = r

    results = list(existing.values())
    for cat in CATEGORIES:
        rows = subset[cat]
        subset_manifest_path = os.path.join(output_root, f"_subset_manifest_{cat}.csv")
        _write_subset_manifest(rows, subset_manifest_path)

        for atten in atten_grid:
            for pf in pf_grid:
                pf_label = "on" if pf else "off"
                key = (cat, atten, pf_label)
                if key in existing:
                    print(f"  [skip, already swept] {cat} atten={atten} pf={pf_label}")
                    continue

                run_dir = os.path.join(output_root, f"{cat}_{atten}_{pf_label}")
                print(f"  [sweep] category={cat} atten_lim_db={atten} post_filter={pf_label} -> {run_dir}")
                process_manifest(
                    manifest_path=subset_manifest_path,
                    output_dir=run_dir,
                    post_filter=pf,
                    atten_lim_db=float(atten),
                )
                metrics = evaluate_outputs(rows, run_dir)
                row_out = {
                    "category": cat,
                    "atten_lim_db": atten,
                    "post_filter": pf_label,
                    "pesq_wb": round(metrics["pesq_wb"], 4),
                    "stoi": round(metrics["stoi"], 4),
                    "si_snr": round(metrics["si_snr"], 4),
                    "n": metrics["n"],
                    "n_pesq": metrics["n_pesq"],
                }
                results.append(row_out)
                # Write incrementally so an interrupted sweep keeps prior grid points (Rule 20).
                with open(sweep_csv_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(row_out.keys()))
                    writer.writeheader()
                    writer.writerows(results)

    return results


def select_optima(sweep_csv_path: str, committed: dict) -> dict:
    """
    Selection rule (pre-committed, phase3_plan.md T4): maximise PESQ-WB subject to STOI not regressing
    more than 0.005 and SI-SNR not regressing more than 0.1 dB against `committed` (the current
    committed per-category means). `committed` = {category: {"stoi": x, "si_snr": y}}.
    """
    with open(sweep_csv_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    optima = {}
    for cat in CATEGORIES:
        base = committed[cat]
        candidates = [
            r for r in rows
            if r["category"] == cat
            and float(r["stoi"]) >= base["stoi"] - 0.005
            and float(r["si_snr"]) >= base["si_snr"] - 0.1
        ]
        if not candidates:
            optima[cat] = None
            continue
        best = max(candidates, key=lambda r: float(r["pesq_wb"]))
        optima[cat] = best
    return optima


def run_self_test():
    print("sweep_atten_lim self-test -- start")

    # Test 1: stratified subset shape (needs the real manifest; skip gracefully if absent, e.g. CI).
    if os.path.exists("data/manifest.csv"):
        subset = build_stratified_subset("data/manifest.csv")
        assert set(subset.keys()) == set(CATEGORIES), f"category keys mismatch: {subset.keys()}"
        for cat, rows in subset.items():
            assert len(rows) == len(SNR_LEVELS) * PER_CATEGORY_PER_SNR, (
                f"[FAIL] {cat}: expected {len(SNR_LEVELS)*PER_CATEGORY_PER_SNR} rows, got {len(rows)}"
            )
            snrs = sorted(float(r["snr_db"]) for r in rows)
            for snr in SNR_LEVELS:
                assert snrs.count(snr) == PER_CATEGORY_PER_SNR, f"[FAIL] {cat}/{snr}dB stratification count off"
        # Determinism: same seed -> identical selection.
        subset2 = build_stratified_subset("data/manifest.csv")
        for cat in CATEGORIES:
            ids1 = [r["output_path"] for r in subset[cat]]
            ids2 = [r["output_path"] for r in subset2[cat]]
            assert ids1 == ids2, f"[FAIL] {cat}: stratified subset not deterministic across calls"
        print("  [PASS] test 1: stratified subset shape + determinism (real manifest)")
    else:
        print("  [SKIP] test 1: data/manifest.csv not present in this environment")

    # Test 2: select_optima picks the max-PESQ candidate that doesn't regress STOI/SI-SNR.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        sweep_csv = os.path.join(td, "atten_sweep.csv")
        fake_rows = [
            {"category": "stationary", "atten_lim_db": 30, "post_filter": "off", "pesq_wb": 2.50, "stoi": 0.917, "si_snr": 16.10, "n": 20, "n_pesq": 20},
            {"category": "stationary", "atten_lim_db": 50, "post_filter": "off", "pesq_wb": 2.55, "stoi": 0.910, "si_snr": 16.00, "n": 20, "n_pesq": 20},  # PESQ higher but STOI regresses too much
            {"category": "stationary", "atten_lim_db": 70, "post_filter": "on", "pesq_wb": 2.52, "stoi": 0.918, "si_snr": 16.15, "n": 20, "n_pesq": 20},  # valid, PESQ higher than baseline row 1
        ]
        with open(sweep_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(fake_rows[0].keys()))
            writer.writeheader()
            writer.writerows(fake_rows)
        committed = {"stationary": {"stoi": 0.9169, "si_snr": 16.1387}, "non_stationary": {"stoi": 0, "si_snr": 0}, "impulsive": {"stoi": 0, "si_snr": 0}}
        optima = select_optima(sweep_csv, committed)
        assert optima["stationary"] is not None, "[FAIL] expected a valid stationary optimum"
        assert optima["stationary"]["atten_lim_db"] == "70", f"[FAIL] expected atten=70 (row 2 STOI regresses too far), got {optima['stationary']}"
        print("  [PASS] test 2: select_optima enforces the pre-committed no-regression rule")

    print("sweep_atten_lim self-test -- ALL PASSED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 3 T4 -- atten_lim_db / post_filter sweep")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest", default="data/manifest.csv")
    parser.add_argument("--output-root", default="results/atten_sweep_outputs")
    parser.add_argument("--sweep-csv", default="results/atten_sweep.csv")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
    else:
        run_sweep(manifest_path=args.manifest, output_root=args.output_root, sweep_csv_path=args.sweep_csv)
