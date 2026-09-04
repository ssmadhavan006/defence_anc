# PS26052 — Phase 3 T5: Post-Processing Experiments (Spectral Tilt / Pre-Emphasis)

**Generated:** 2026-09-04
**Status: DROPPED — null-to-negative result, not kept in the pipeline.** Logged per DoD-4 (negative
results are a finding, not a non-event) rather than silently deleted.

## What was tried

`phase3_plan.md` D5 proposed a first-order pre-emphasis filter `y[n] = x[n] - alpha*x[n-1]` applied
directly to DeepFilterNet's *already-enhanced* output (post-DFN, not pre-DFN — a different, untested
variant), on the hypothesis (from codec/ASR front-end practice) that lifting high-frequency energy can
raise PESQ by 0.05–0.15. D5 explicitly flagged the counter-hypothesis up front: DFN3 already operates on
a learned ERB-scale spectral representation, so an external tilt may fight rather than complement it —
budgeted as a 2-hour experiment, "expect a null or negative result."

**Method:** `scripts/postproc_experiments.py`, self-tested (formula correctness + DC-suppression sanity
check). Grid `alpha ∈ {0.0 (no-op control), 0.5, 0.95, 0.97}`, applied to the T4-winning
(`atten_lim_db=30`, `post_filter=off`) DeepFilterNet output on the same 60-file stratified subset used in
T4 Stage 1, scored against `clean_ref_path` with the same PESQ-WB/STOI/SI-SNR pipeline used everywhere
else in this phase.

## Result: negative on SI-SNR, flat-to-negative on PESQ, essentially flat on STOI

| Category | alpha | PESQ-WB | STOI | SI-SNR (dB) |
|---|---|---|---|---|
| stationary | 0.0 (control) | 2.5023 | 0.8961 | 15.38 |
| | 0.5 | 2.4851 | 0.8961 | 12.89 |
| | 0.95 | 2.3868 | 0.8957 | **−6.22** |
| | 0.97 | 2.4167 | 0.8955 | **−10.08** |
| non_stationary | 0.0 (control) | 2.1371 | 0.8421 | 11.36 |
| | 0.5 | 2.1152 | 0.8421 | 9.75 |
| | 0.95 | 2.0569 | 0.8417 | **−7.66** |
| | 0.97 | 2.0829 | 0.8414 | **−11.38** |
| impulsive | 0.0 (control) | 2.6299 | 0.9232 | 15.61 |
| | 0.5 | 2.6099 | 0.9232 | 13.08 |
| | 0.95 | 2.5952 | 0.9225 | **−6.45** |
| | 0.97 | 2.6300 | 0.9221 | **−10.24** |

Full data: `results/postproc_tilt_experiment.csv`.

**No alpha value improves PESQ in any category** — every non-zero alpha is flat-to-lower than the alpha=0
control. STOI barely moves (±0.001), consistent with STOI being fairly tolerant of spectral tilt. **SI-SNR
collapses catastrophically at alpha≥0.95** (−6 to −11 dB, i.e. *worse than doing nothing to the noisy
signal* in absolute terms) — expected once you consider what the metric measures: SI-SNR is a
scale-invariant but *waveform*-sensitive comparison against `clean_ref_path`, and pre-emphasis changes the
spectral balance of the enhanced signal relative to an *unfiltered* clean reference, which the metric
penalizes heavily even though perceptual quality (PESQ/STOI, both more spectrally-tolerant metrics) barely
registers it.

## Why this matches D5's prior

DFN3 already applies a learned, ERB-scale, per-band gain — exactly the kind of frequency-dependent
processing a hand-rolled first-order tilt would naively try to approximate, except DFN3's version is
conditioned on the actual noise/speech mixture rather than a fixed heuristic curve. Layering a static tilt
on top doesn't correct a deficiency in the model's output; it just detunes an already-optimized spectral
balance. This is the same class of finding as T3's NLMS-under-augmentation result: a technique whose
benefit is well-established for *un-modeled* signal paths (raw microphone capture in ASR front-ends;
NLMS's simple adaptive filter) does not transfer to a signal that has already been through a trained,
context-aware model.

## Disposition

**Dropped, not merged.** No config flag is added, no live-pipeline code path exists for this — the
experiment lived entirely in `scripts/postproc_experiments.py` / `results/postproc_tilt_experiment.csv`
as evaluation artifacts, kept for the record per DoD-4's no-cherry-picking clause. The T4 winning
configuration (`atten_lim_db=30, post_filter=off`, no post-processing) remains the recommendation.
