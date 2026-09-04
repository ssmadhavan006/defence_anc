"""
scripts/postproc_experiments.py — Phase 3 T5: spectral tilt / pre-emphasis post-processing experiment.

Applies a simple first-order pre-emphasis filter y[n] = x[n] - alpha*x[n-1] directly to DeepFilterNet's
already-enhanced output (post-DFN, per phase3_plan.md D5/T5 -- not applied to the input before DFN3, which
is a different, untested variant), at a small grid of alpha values, and measures PESQ-WB/STOI/SI-SNR
against the T4 stratified subset outputs (results/atten_sweep_outputs/<category>_30_off/, the winning
atten_lim_db=30/post_filter=off configuration -- reused rather than regenerated).

D5's prior: DFN3 already operates on a learned ERB-scale spectral representation, so an external tilt may
fight the model rather than complement it. Expected: null or negative result, budgeted as a short
experiment (phase3_plan.md D5), kept only on a demonstrated win under the T4 selection rule
(DoD-4: negative results are logged, not deleted).
"""

import os
import sys
import csv
import argparse

import numpy as np

sys.path.insert(0, ".")
import soundfile as sf
from eval.metrics import compute_si_snr, compute_stoi, compute_pesq_wb
from scripts.sweep_atten_lim import build_stratified_subset, CATEGORIES

TARGET_SR = 48000
ALPHA_GRID = [0.0, 0.5, 0.95, 0.97]  # 0.0 = no-op control


def apply_preemphasis(audio: np.ndarray, alpha: float) -> np.ndarray:
    """y[n] = x[n] - alpha*x[n-1], y[0] = x[0]. alpha=0.0 is the identity (no-op) control."""
    if alpha == 0.0:
        return audio.copy()
    out = np.empty_like(audio)
    out[0] = audio[0]
    out[1:] = audio[1:] - alpha * audio[:-1]
    return out


def evaluate_tilt(rows: list, dfn_output_dir: str, alpha: float) -> dict:
    pesq_vals, stoi_vals, si_snr_vals = [], [], []
    for row in rows:
        mix_filename = os.path.basename(row["output_path"])
        deg_path = os.path.join(dfn_output_dir, mix_filename)
        ref_path = row["clean_ref_path"]
        if not os.path.exists(deg_path) or not os.path.exists(ref_path):
            continue
        ref_audio, _ = sf.read(ref_path, dtype="float32")
        deg_audio, _ = sf.read(deg_path, dtype="float32")
        tilted = apply_preemphasis(deg_audio, alpha)
        si_snr_vals.append(compute_si_snr(ref_audio, tilted))
        stoi_vals.append(compute_stoi(ref_audio, tilted, fs=TARGET_SR))
        try:
            pesq_vals.append(compute_pesq_wb(ref_audio, tilted, fs=TARGET_SR))
        except Exception:
            pass
    n = len(stoi_vals)
    return {
        "pesq_wb": sum(pesq_vals) / len(pesq_vals) if pesq_vals else float("nan"),
        "stoi": sum(stoi_vals) / n if n else float("nan"),
        "si_snr": sum(si_snr_vals) / n if n else float("nan"),
        "n": n,
    }


def run_experiment(
    manifest_path: str = "data/manifest.csv",
    dfn_output_root: str = "results/atten_sweep_outputs",
    out_csv_path: str = "results/postproc_tilt_experiment.csv",
    alpha_grid: list = None,
    seed: int = 42,
) -> list:
    alpha_grid = alpha_grid if alpha_grid is not None else ALPHA_GRID
    subset = build_stratified_subset(manifest_path, seed=seed)

    results = []
    for cat in CATEGORIES:
        dfn_dir = os.path.join(dfn_output_root, f"{cat}_30_off")
        if not os.path.isdir(dfn_dir):
            raise FileNotFoundError(
                f"Expected T4 sweep output at {dfn_dir} (atten_lim_db=30/post_filter=off) -- run "
                f"scripts/sweep_atten_lim.py first."
            )
        for alpha in alpha_grid:
            metrics = evaluate_tilt(subset[cat], dfn_dir, alpha)
            row_out = {
                "category": cat,
                "alpha": alpha,
                "pesq_wb": round(metrics["pesq_wb"], 4),
                "stoi": round(metrics["stoi"], 4),
                "si_snr": round(metrics["si_snr"], 4),
                "n": metrics["n"],
            }
            results.append(row_out)
            print(f"  category={cat} alpha={alpha}: PESQ={row_out['pesq_wb']} STOI={row_out['stoi']} SI-SNR={row_out['si_snr']}")

    os.makedirs(os.path.dirname(out_csv_path), exist_ok=True)
    with open(out_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    return results


def run_self_test():
    print("postproc_experiments self-test -- start")

    # Test 1: alpha=0.0 is the identity.
    x = np.array([1.0, 2.0, 3.0, -1.0, 0.5], dtype=np.float32)
    y = apply_preemphasis(x, 0.0)
    assert np.array_equal(x, y), "[FAIL] alpha=0.0 must be a no-op"
    print("  [PASS] test 1: alpha=0.0 is identity")

    # Test 2: known pre-emphasis formula on a hand-computed example.
    x = np.array([1.0, 2.0, 4.0, 8.0], dtype=np.float32)
    y = apply_preemphasis(x, 0.5)
    expected = np.array([1.0, 2.0 - 0.5 * 1.0, 4.0 - 0.5 * 2.0, 8.0 - 0.5 * 4.0], dtype=np.float32)
    assert np.allclose(y, expected), f"[FAIL] pre-emphasis formula mismatch: {y} vs {expected}"
    print("  [PASS] test 2: pre-emphasis formula matches y[n]=x[n]-alpha*x[n-1]")

    # Test 3: pre-emphasis high-pass-tilts a DC-heavy signal toward zero mean-ish behavior (sanity, not exact).
    dc = np.ones(1000, dtype=np.float32)
    y = apply_preemphasis(dc, 0.97)
    assert abs(y[1:].mean()) < abs(dc.mean()), "[FAIL] pre-emphasis should suppress low-frequency/DC content"
    print("  [PASS] test 3: pre-emphasis suppresses DC/low-frequency content as expected")

    print("postproc_experiments self-test -- ALL PASSED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 3 T5 -- spectral tilt / pre-emphasis experiment")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest", default="data/manifest.csv")
    parser.add_argument("--dfn-output-root", default="results/atten_sweep_outputs")
    parser.add_argument("--out-csv", default="results/postproc_tilt_experiment.csv")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
    else:
        run_experiment(manifest_path=args.manifest, dfn_output_root=args.dfn_output_root, out_csv_path=args.out_csv)
