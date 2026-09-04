import os
import sys
import csv
import time
import glob
import argparse
import numpy as np
import soundfile as sf
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.insert(0, ".")
from eval.metrics import compute_si_snr, compute_stoi, compute_pesq_wb

TARGET_SR = 48000
METHODS = ["noisy", "spectral_subtraction", "wiener", "nlms", "deepfilternet"]

def resolve_method_audio_path(row: dict, method: str, baselines_dir: str = "results/baselines") -> str:
    mix_file = os.path.basename(row["output_path"])
    if method == "noisy":
        return row["output_path"]
    else:
        return os.path.join(baselines_dir, method, mix_file)

def run_evaluation(
    manifest_path: str = "data/manifest.csv",
    baselines_dir: str = "results/baselines",
    raw_eval_out: str = "results/eval_raw.csv",
    summary_out: str = "results/results.csv",
    charts_dir: str = "results/charts",
    limit: int = None,
    extra_methods: list = None,
):
    """
    Evaluates all 5 conditions across mixtures in manifest.csv.
    Generates eval_raw.csv, results.csv, and comparison charts.
    `extra_methods` appends additional method subdirectories under baselines_dir (e.g. a tuned
    DeepFilterNet variant) without touching the module-level METHODS default used by every other run.
    """
    methods = METHODS + list(extra_methods) if extra_methods else METHODS
    with open(manifest_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    if limit is not None and limit < len(rows):
        rows = rows[:limit]

    print(f"=== STARTING EVALUATION ENGINE ({len(rows)} mixtures x {len(methods)} methods = {len(rows)*len(methods)} target evaluations) ===")
    t0_start = time.time()

    raw_eval_rows = []
    exclusions = []
    noisy_si_snr_map = {}

    # First pass: evaluate 'noisy' condition for all mixtures to build noisy_si_snr_map
    print("\n--- Evaluating Condition 1/5: NOISY (Baseline Reference) ---")
    for row in rows:
        mix_id = os.path.basename(row["output_path"])
        clean_ref_path = row["clean_ref_path"]
        noisy_path = row["output_path"]
        cat = row["category"]
        sub = row["subtype"]
        snr_db = float(row["snr_db"])

        if not os.path.exists(clean_ref_path) or not os.path.exists(noisy_path):
            exclusions.append({"mixture_id": mix_id, "method": "noisy", "error": "File missing"})
            continue

        try:
            ref_audio, _ = sf.read(clean_ref_path, dtype="float32")
            deg_audio, _ = sf.read(noisy_path, dtype="float32")

            # SI-SNR
            si_snr_val = compute_si_snr(ref_audio, deg_audio)
            noisy_si_snr_map[mix_id] = si_snr_val

            # STOI
            stoi_val = compute_stoi(ref_audio, deg_audio, fs=TARGET_SR)

            # PESQ-WB
            pesq_err_msg = None
            try:
                pesq_val = compute_pesq_wb(ref_audio, deg_audio, fs=TARGET_SR)
            except Exception as pe:
                pesq_val = np.nan
                pesq_err_msg = str(pe)
                exclusions.append({"mixture_id": mix_id, "method": "noisy", "error": f"PESQ: {pe}"})

            raw_eval_rows.append({
                "mixture_id": mix_id,
                "method": "noisy",
                "category": cat,
                "subtype": sub,
                "snr_db": snr_db,
                "pesq_wb": pesq_val,
                "pesq_wb_error": pesq_err_msg if pesq_err_msg else "",
                "stoi": stoi_val,
                "si_snr": si_snr_val,
                "delta_si_snr": 0.0,
                "output_path": noisy_path,
                "clean_ref_path": clean_ref_path,
            })
        except Exception as e:
            exclusions.append({"mixture_id": mix_id, "method": "noisy", "error": str(e)})

    # Second pass: evaluate remaining 4 enhanced methods
    other_methods = [m for m in methods if m != "noisy"]
    for idx, method in enumerate(other_methods, start=2):
        print(f"--- Evaluating Condition {idx}/5: {method.upper()} ---")
        for row in rows:
            mix_id = os.path.basename(row["output_path"])
            clean_ref_path = row["clean_ref_path"]
            deg_path = resolve_method_audio_path(row, method, baselines_dir)
            cat = row["category"]
            sub = row["subtype"]
            snr_db = float(row["snr_db"])

            if not os.path.exists(clean_ref_path) or not os.path.exists(deg_path):
                exclusions.append({"mixture_id": mix_id, "method": method, "error": f"File missing: {deg_path}"})
                continue

            try:
                ref_audio, _ = sf.read(clean_ref_path, dtype="float32")
                deg_audio, _ = sf.read(deg_path, dtype="float32")

                # SI-SNR
                si_snr_val = compute_si_snr(ref_audio, deg_audio)
                
                # Rule 25: Delta SI-SNR = method SI-SNR - noisy SI-SNR for same mixture
                noisy_baseline = noisy_si_snr_map.get(mix_id, np.nan)
                delta_si_snr_val = (si_snr_val - noisy_baseline) if not np.isnan(noisy_baseline) else np.nan

                # STOI
                stoi_val = compute_stoi(ref_audio, deg_audio, fs=TARGET_SR)

                # PESQ-WB
                pesq_err_msg = None
                try:
                    pesq_val = compute_pesq_wb(ref_audio, deg_audio, fs=TARGET_SR)
                except Exception as pe:
                    pesq_val = np.nan
                    pesq_err_msg = str(pe)
                    # Log PESQ exception per Rule 24
                    exclusions.append({"mixture_id": mix_id, "method": method, "error": f"PESQ: {pe}"})

                raw_eval_rows.append({
                    "mixture_id": mix_id,
                    "method": method,
                    "category": cat,
                    "subtype": sub,
                    "snr_db": snr_db,
                    "pesq_wb": pesq_val,
                    "pesq_wb_error": pesq_err_msg if pesq_err_msg else "",
                    "stoi": stoi_val,
                    "si_snr": si_snr_val,
                    "delta_si_snr": delta_si_snr_val,
                    "output_path": deg_path,
                    "clean_ref_path": clean_ref_path,
                })
            except Exception as e:
                exclusions.append({"mixture_id": mix_id, "method": method, "error": str(e)})

    total_eval_time = time.time() - t0_start
    print(f"\nEvaluation loop complete in {total_eval_time:.2f}s.")
    print(f"Total Evaluation Rows: {len(raw_eval_rows)} / {len(rows)*len(methods)}")
    print(f"Total Rule-24 Exclusions Logged: {len(exclusions)}")

    # Write results/eval_raw.csv
    os.makedirs(os.path.dirname(raw_eval_out), exist_ok=True)
    df_raw = pd.DataFrame(raw_eval_rows)
    df_raw.to_csv(raw_eval_out, index=False)
    print(f"Saved raw scores to: {raw_eval_out}")

    # Generate results/results.csv (Category x Method aggregates)
    df_summary = generate_summary_table(df_raw, summary_out)

    # Generate comparison charts
    generate_charts(df_raw, charts_dir)

    return df_raw, df_summary, exclusions

def generate_summary_table(df_raw: pd.DataFrame, summary_out: str) -> pd.DataFrame:
    """
    Aggregates raw evaluation scores by (category x method).
    Calculates mean and std for PESQ-WB, STOI, SI-SNR, and Delta SI-SNR.
    Visibly reports PESQ-WB status and availability count per Rule 28.
    """
    grouped = df_raw.groupby(["category", "method"]).agg(
        sample_count=("mixture_id", "count"),
        pesq_wb_valid=("pesq_wb", lambda x: x.notna().sum()),
        pesq_wb_mean=("pesq_wb", "mean"),
        pesq_wb_std=("pesq_wb", "std"),
        stoi_mean=("stoi", "mean"),
        stoi_std=("stoi", "std"),
        si_snr_mean=("si_snr", "mean"),
        si_snr_std=("si_snr", "std"),
        delta_si_snr_mean=("delta_si_snr", "mean"),
        delta_si_snr_std=("delta_si_snr", "std"),
    ).reset_index()

    # Rule 28: Add visible status column for PESQ-WB availability
    grouped["pesq_wb_status"] = grouped.apply(
        lambda r: f"{r['pesq_wb_valid']}/{r['sample_count']} (Unavailable: C++ Build Tools required for pesq C extension)" if r["pesq_wb_valid"] == 0 else f"{r['pesq_wb_valid']}/{r['sample_count']} Valid",
        axis=1
    )

    # Reorder columns so pesq_wb is visibly present
    cols_order = [
        "category", "method", "sample_count",
        "pesq_wb_mean", "pesq_wb_std", "pesq_wb_status",
        "stoi_mean", "stoi_std",
        "si_snr_mean", "si_snr_std",
        "delta_si_snr_mean", "delta_si_snr_std"
    ]
    grouped = grouped[cols_order]

    # Round numeric columns for clean display
    for col in grouped.columns:
        if "mean" in col or "std" in col:
            grouped[col] = grouped[col].round(4)

    os.makedirs(os.path.dirname(summary_out), exist_ok=True)
    grouped.to_csv(summary_out, index=False)
    print(f"\n=== CATEGORY x METHOD SUMMARY TABLE ===")
    print(grouped.to_string())
    print(f"\nSaved summary table to: {summary_out}")
    return grouped

def generate_charts(df_raw: pd.DataFrame, charts_dir: str = "results/charts"):
    """
    Generates grouped bar charts comparing all 5 methods across 3 categories per metric.
    """
    os.makedirs(charts_dir, exist_ok=True)
    sns.set_theme(style="whitegrid", palette="muted")
    
    metrics = [
        ("pesq_wb", "PESQ-WB Quality Score (-0.5 - 4.5)", "pesq_comparison.png", (-0.5, 4.5)),
        ("stoi", "STOI Intelligibility Score (0.0 - 1.0)", "stoi_comparison.png", (0.0, 1.05)),
        ("si_snr", "SI-SNR (dB)", "si_snr_comparison.png", None),
        ("delta_si_snr", "Delta SI-SNR Improvement over Noisy (dB)", "delta_si_snr_comparison.png", None),
    ]

    category_order = ["stationary", "non_stationary", "impulsive"]
    method_order = ["noisy", "spectral_subtraction", "wiener", "nlms", "deepfilternet"]

    for col, title, fname, ylim in metrics:
        plt.figure(figsize=(10, 6))
        ax = sns.barplot(
            data=df_raw,
            x="category",
            y=col,
            hue="method",
            order=category_order,
            hue_order=method_order,
            errorbar="sd",
            capsize=0.08,
            err_kws={"linewidth": 1.2},
        )
        plt.title(f"PS26052 Defence ANC: {title}", fontsize=14, fontweight="bold", pad=12)
        plt.xlabel("Noise Category", fontsize=12, fontweight="bold")
        plt.ylabel(title, fontsize=12, fontweight="bold")
        if ylim:
            plt.ylim(ylim)
        plt.legend(title="Method", bbox_to_anchor=(1.02, 1), loc="upper left", frameon=True)
        plt.tight_layout()
        
        chart_path = os.path.join(charts_dir, fname)
        plt.savefig(chart_path, dpi=300)
        plt.close()
        print(f"Saved chart: {chart_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PS26052 Objective Evaluation Engine")
    parser.add_argument("--manifest", default="data/manifest.csv")
    parser.add_argument("--baselines-dir", default="results/baselines")
    parser.add_argument("--eval-raw", default="results/eval_raw.csv")
    parser.add_argument("--results", default="results/results.csv")
    parser.add_argument("--charts-dir", default="results/charts")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--extra-methods", default=None,
                         help="Comma-separated extra method subdirs under --baselines-dir to evaluate "
                              "alongside the standard 5 (e.g. a tuned DeepFilterNet variant), without "
                              "changing the default METHODS used by every other run.")
    args = parser.parse_args()

    run_evaluation(
        manifest_path=args.manifest,
        baselines_dir=args.baselines_dir,
        raw_eval_out=args.eval_raw,
        summary_out=args.results,
        charts_dir=args.charts_dir,
        limit=args.limit,
        extra_methods=args.extra_methods.split(",") if args.extra_methods else None,
    )
