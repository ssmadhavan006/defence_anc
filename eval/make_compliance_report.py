"""
eval/make_compliance_report.py — Compute the DRDO target-compliance verdict from eval_raw.csv.

Why this exists:
    Prior versions of results/final/target_compliance.{json,md} were assembled by hand. That
    made the headline 6/9 verdict unreproducible from a single command, which sits badly with
    Rule 1 (no number that didn't come from an executed command) and Rule 3 (paste the
    evidence). This script derives every cell from results/eval_raw.csv so the verdict can be
    regenerated and diffed.

What it does NOT do:
    It does not compute metrics. It only aggregates what eval/run_eval.py already measured.

Rules honoured:
    - Rule 24/26: PESQ exclusions are counted per cell and reported explicitly, never silently
      dropped and never backfilled.
    - Rule 28: every metric is present for every category cell, with its own n.
    - No averaging across categories — the verdict is per-category, per-metric.

Usage:
    python eval/make_compliance_report.py
    python eval/make_compliance_report.py --method deepfilternet --label "untuned baseline"
    python eval/make_compliance_report.py --self-test
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict

TARGETS = {
    "SI_SNR_dB": {"threshold": 15.0, "criterion": "greater_than", "field": "si_snr"},
    "STOI": {"threshold": 0.85, "criterion": "greater_than", "field": "stoi"},
    "PESQ_WB": {"threshold": 2.5, "criterion": "greater_than", "field": "pesq_wb"},
}

CATEGORY_ORDER = ["stationary", "non_stationary", "impulsive"]


def _mean(vals):
    return sum(vals) / len(vals) if vals else None


def _collect(eval_raw_path: str, method: str):
    """
    Returns (per_category, per_subtype, total_rows_for_method).

    Each entry maps metric-name -> {"values": [...], "excluded": int}.
    A PESQ row is 'excluded' when the metric is blank or unparseable (Rule 24) — those rows
    are counted, not silently skipped, and never replaced with a placeholder.
    """
    per_cat = defaultdict(lambda: defaultdict(lambda: {"values": [], "excluded": 0}))
    per_sub = defaultdict(lambda: defaultdict(lambda: {"values": [], "excluded": 0}))
    n_rows = 0

    with open(eval_raw_path, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["method"] != method:
                continue
            n_rows += 1
            cat = row["category"]
            sub = f"{cat}/{row['subtype']}"
            for metric, spec in TARGETS.items():
                raw = (row.get(spec["field"]) or "").strip()
                try:
                    val = float(raw)
                    if val != val:  # NaN
                        raise ValueError("NaN")
                except (TypeError, ValueError):
                    per_cat[cat][metric]["excluded"] += 1
                    per_sub[sub][metric]["excluded"] += 1
                    continue
                per_cat[cat][metric]["values"].append(val)
                per_sub[sub][metric]["values"].append(val)

    return per_cat, per_sub, n_rows


def _manifest_composition(manifest_path: str):
    if not os.path.exists(manifest_path):
        return {}
    comp = defaultdict(lambda: defaultdict(int))
    with open(manifest_path, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            comp[row["category"]][row["subtype"]] += 1
    return {k: dict(v) for k, v in comp.items()}


def build_report(eval_raw_path: str, manifest_path: str, method: str,
                 corpus_version: str, label: str):
    per_cat, per_sub, n_rows = _collect(eval_raw_path, method)
    if n_rows == 0:
        raise ValueError(
            f"No rows with method={method!r} found in {eval_raw_path}. "
            f"Did eval/run_eval.py run with --extra-methods {method}?"
        )

    results = {}
    passes = 0
    cells = 0
    for cat in CATEGORY_ORDER:
        if cat not in per_cat:
            continue
        entry = {}
        for metric, spec in TARGETS.items():
            bucket = per_cat[cat][metric]
            mean = _mean(bucket["values"])
            ok = (mean is not None) and (mean > spec["threshold"])
            cells += 1
            passes += int(ok)
            entry[f"{metric}_mean"] = None if mean is None else round(mean, 4)
            entry[f"{metric}_pass"] = ok
            entry[f"{metric}_verdict"] = "PASS" if ok else "FAIL"
            entry[f"{metric}_n"] = len(bucket["values"])
            entry[f"{metric}_excluded"] = bucket["excluded"]
            if mean is not None:
                margin = mean - spec["threshold"]
                entry[f"{metric}_margin"] = round(margin, 4)
        results[cat] = entry

    subtypes = {}
    for sub in sorted(per_sub):
        e = {}
        for metric in TARGETS:
            b = per_sub[sub][metric]
            m = _mean(b["values"])
            e[f"{metric}_mean"] = None if m is None else round(m, 4)
            e[f"{metric}_n"] = len(b["values"])
            e[f"{metric}_excluded"] = b["excluded"]
        subtypes[sub] = e

    return {
        "generated_by": "eval/make_compliance_report.py",
        "corpus_version": corpus_version,
        "method_evaluated": method,
        "label": label,
        "eval_raw_source": eval_raw_path,
        "rows_for_method": n_rows,
        "dataset_composition": _manifest_composition(manifest_path),
        "targets": {k: {"threshold": v["threshold"], "criterion": v["criterion"]}
                    for k, v in TARGETS.items()},
        "results": results,
        "per_subtype": subtypes,
        "verdict": {
            "cells_passed": passes,
            "cells_total": cells,
            "summary": f"{passes} of {cells} metric cells PASS",
        },
    }


def render_markdown(rep: dict) -> str:
    L = []
    L.append("# DRDO Target Compliance Report")
    L.append("")
    L.append(f"- **Generated by:** `{rep['generated_by']}` (verdict computed from `{rep['eval_raw_source']}`, not hand-written)")
    L.append(f"- **Corpus version:** {rep['corpus_version']}")
    L.append(f"- **Method evaluated:** `{rep['method_evaluated']}` — {rep['label']}")
    L.append(f"- **Rows aggregated:** {rep['rows_for_method']}")
    L.append("")
    L.append(f"## Verdict: {rep['verdict']['summary']}")
    L.append("")
    L.append("No averaging across categories. Each cell is a per-category mean over all five input SNR levels.")
    L.append("")
    L.append("| Category | SI-SNR (dB) >15 | STOI >0.85 | PESQ-WB >2.5 |")
    L.append("|---|---|---|---|")
    for cat in CATEGORY_ORDER:
        if cat not in rep["results"]:
            continue
        r = rep["results"][cat]
        cells = []
        for metric in ["SI_SNR_dB", "STOI", "PESQ_WB"]:
            mean = r.get(f"{metric}_mean")
            mark = "PASS" if r.get(f"{metric}_pass") else "FAIL"
            cells.append(f"{mean} ({mark})")
        L.append(f"| `{cat}` | {cells[0]} | {cells[1]} | {cells[2]} |")
    L.append("")

    L.append("## Dataset composition")
    L.append("")
    L.append("| Category | Subtype | Mixtures |")
    L.append("|---|---|---|")
    for cat in CATEGORY_ORDER:
        for sub, n in sorted(rep["dataset_composition"].get(cat, {}).items()):
            L.append(f"| `{cat}` | `{sub}` | {n} |")
    L.append("")

    L.append("## Per-subtype breakdown")
    L.append("")
    L.append("Included because category means can hide a single dominating subtype — that is exactly")
    L.append("how the v1 `crowd` defect stayed invisible behind a `non_stationary` average.")
    L.append("")
    L.append("| Subtype | SI-SNR (dB) | STOI | PESQ-WB | n |")
    L.append("|---|---|---|---|---|")
    for sub, e in rep["per_subtype"].items():
        L.append(f"| `{sub}` | {e['SI_SNR_dB_mean']} | {e['STOI_mean']} | {e['PESQ_WB_mean']} | {e['PESQ_WB_n']} |")
    L.append("")

    excl_total = sum(
        rep["results"][c].get(f"{m}_excluded", 0)
        for c in rep["results"] for m in TARGETS
    )
    L.append("## Exclusions (Rules 24 / 26)")
    L.append("")
    L.append(f"Total excluded metric observations across all cells: **{excl_total}**")
    if excl_total:
        L.append("")
        L.append("| Category | Metric | Excluded |")
        L.append("|---|---|---|")
        for c in rep["results"]:
            for m in TARGETS:
                n = rep["results"][c].get(f"{m}_excluded", 0)
                if n:
                    L.append(f"| `{c}` | {m} | {n} |")
    L.append("")
    return "\n".join(L)


def _self_test() -> bool:
    """Self-test (Rule 8): runs the aggregation over a tiny synthetic eval_raw."""
    import tempfile
    import shutil

    print("make_compliance_report self-test -- start")
    ok = True
    tmp = tempfile.mkdtemp(prefix="compliance_selftest_")
    try:
        ev = os.path.join(tmp, "eval_raw.csv")
        cols = ["mixture_id", "method", "category", "subtype", "snr_db",
                "pesq_wb", "pesq_wb_error", "stoi", "si_snr", "delta_si_snr",
                "output_path", "clean_ref_path"]
        rows = [
            # stationary: comfortably passes everything
            dict(mixture_id="a", method="m", category="stationary", subtype="engine", snr_db="0",
                 pesq_wb="3.0", pesq_wb_error="", stoi="0.90", si_snr="16.0", delta_si_snr="0",
                 output_path="", clean_ref_path=""),
            dict(mixture_id="b", method="m", category="stationary", subtype="engine", snr_db="5",
                 pesq_wb="3.0", pesq_wb_error="", stoi="0.90", si_snr="16.0", delta_si_snr="0",
                 output_path="", clean_ref_path=""),
            # impulsive: one blank PESQ -> must be EXCLUDED, not treated as 0
            dict(mixture_id="c", method="m", category="impulsive", subtype="gunshot", snr_db="0",
                 pesq_wb="", pesq_wb_error="boom", stoi="0.90", si_snr="16.0", delta_si_snr="0",
                 output_path="", clean_ref_path=""),
            dict(mixture_id="d", method="m", category="impulsive", subtype="gunshot", snr_db="5",
                 pesq_wb="3.0", pesq_wb_error="", stoi="0.90", si_snr="16.0", delta_si_snr="0",
                 output_path="", clean_ref_path=""),
            # a different method that must be ignored entirely
            dict(mixture_id="e", method="other", category="stationary", subtype="engine", snr_db="0",
                 pesq_wb="1.0", pesq_wb_error="", stoi="0.10", si_snr="1.0", delta_si_snr="0",
                 output_path="", clean_ref_path=""),
        ]
        with open(ev, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)

        rep = build_report(ev, os.path.join(tmp, "nope.csv"), "m", "test", "unit test")

        # test 1: rows from other methods are excluded
        if rep["rows_for_method"] == 4:
            print("  [PASS] test 1: only the requested method's rows are aggregated")
        else:
            print(f"  [FAIL] test 1: expected 4 rows, got {rep['rows_for_method']}")
            ok = False

        # test 2: blank PESQ is counted as an exclusion, not coerced to a number
        imp = rep["results"]["impulsive"]
        if imp["PESQ_WB_excluded"] == 1 and imp["PESQ_WB_n"] == 1 and abs(imp["PESQ_WB_mean"] - 3.0) < 1e-9:
            print("  [PASS] test 2: blank PESQ excluded (n=1, mean=3.0), not backfilled with 0")
        else:
            print(f"  [FAIL] test 2: exclusion handling wrong: {imp}")
            ok = False

        # test 3: threshold is strict greater-than
        st = rep["results"]["stationary"]
        if st["PESQ_WB_pass"] and st["STOI_pass"] and st["SI_SNR_dB_pass"]:
            print("  [PASS] test 3: passing cells marked PASS")
        else:
            print(f"  [FAIL] test 3: {st}")
            ok = False

        # test 4: verdict counts cells correctly (2 categories x 3 metrics = 6)
        if rep["verdict"]["cells_total"] == 6 and rep["verdict"]["cells_passed"] == 6:
            print("  [PASS] test 4: verdict tally 6/6")
        else:
            print(f"  [FAIL] test 4: {rep['verdict']}")
            ok = False

        # test 5: markdown renders without raising and carries the verdict line
        md = render_markdown(rep)
        if "6 of 6 metric cells PASS" in md:
            print("  [PASS] test 5: markdown renders with verdict")
        else:
            print("  [FAIL] test 5: verdict missing from markdown")
            ok = False

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("make_compliance_report self-test -- " + ("ALL PASSED" if ok else "FAILURES PRESENT"))
    return ok


def main():
    ap = argparse.ArgumentParser(description="Generate the DRDO target-compliance report from eval_raw.csv")
    ap.add_argument("--eval-raw", default="results/eval_raw.csv")
    ap.add_argument("--manifest", default="data/manifest.csv")
    ap.add_argument("--method", default="deepfilternet_tuned",
                    help="Method subdir name as it appears in eval_raw.csv (default: deepfilternet_tuned)")
    ap.add_argument("--corpus-version", default="v2 (non_stationary = helicopter/wind/aircraft; see docs/corpus_redefinition_v2.md)")
    ap.add_argument("--label", default="DeepFilterNet3, atten_lim_db=30 (deployed configuration)")
    ap.add_argument("--out-json", default="results/final/target_compliance.json")
    ap.add_argument("--out-md", default="results/final/target_compliance.md")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(0 if _self_test() else 1)

    rep = build_report(args.eval_raw, args.manifest, args.method, args.corpus_version, args.label)
    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write(render_markdown(rep))

    print(render_markdown(rep))
    print(f"\nWrote {args.out_json} and {args.out_md}")


if __name__ == "__main__":
    main()
