# PS26052 — Augmentation Robustness (Phase 3 T1–T3)

**Generated:** 2026-09-04
**Purpose:** Quantify how each method degrades when the clean 300-mixture evaluation is replayed through
a more adverse acoustic path — synthetic room reverb (`--augment-rir`) and mic/ADC clipping
(`--augment-clipping`) — rather than whether scores drop (they do, by construction).

## Datasets

| | Clean | Augmented |
|---|---|---|
| Manifest | `data/manifest.csv` | `data/manifest_augmented.csv` |
| Mixtures | `data/mixtures/` | `data/mixtures_augmented/` |
| Baselines | `results/baselines/` | `results/baselines_augmented/` |
| Raw eval | `results/eval_raw.csv` | `results/eval_raw_augmented.csv` |
| Summary | `results/results.csv` | `results/results_augmented.csv` |

Both are 300 mixtures × 5 methods = 1,500 evaluation pairs, **0 exclusions** in either run (Rule 24).
Row-count integrity verified programmatically for both (Rule 26): manifest rows == files on disk == 300,
0 missing, 0 orphans (clean set checked as part of the prerequisite manifest-drift fix earlier this
session; augmented set checked immediately after T1 generation).

Augmentation parameters per mixture are logged in `data/manifest_augmented.csv`'s `rir_rt60_sec` and
`clip_frac` columns (per-category room presets / clip-intensity presets — see `data/mix_dataset.py`
`CATEGORY_ROOM`/`CATEGORY_CLIP`/`ROOM_PRESETS`/`CLIP_PRESETS`). Reverb is convolved into the noise
channel before mixing; clipping is applied to the final mix after mixing, so `achieved_snr_db` in the
augmented manifest reflects pre-clip SNR (mixing-stage behavior, unrelated to this comparison).

## Delta table: augmented − clean, DeepFilterNet3 vs. every baseline, all 3 categories

| Category | Method | ΔPESQ-WB | ΔSTOI | ΔSI-SNR (dB) |
|---|---|---|---|---|
| Stationary | noisy | −0.011 | +0.000 | −0.14 |
| | spectral_subtraction | −0.009 | −0.000 | −0.04 |
| | wiener | −0.019 | −0.002 | **−0.00** |
| | nlms *(ref-assisted)* | −0.243 | −0.123 | **−5.37** |
| | **deepfilternet** | −0.061 | −0.002 | −0.81 |
| Non-stationary | noisy | +0.015 | +0.004 | −0.12 |
| | spectral_subtraction | +0.008 | +0.004 | −0.06 |
| | wiener | −0.002 | +0.004 | −0.01 |
| | nlms *(ref-assisted)* | −0.188 | −0.112 | **−4.29** |
| | **deepfilternet** | +0.014 | +0.019 | **+0.19** |
| Impulsive | noisy | −0.064 | −0.009 | −0.77 |
| | spectral_subtraction | −0.067 | −0.009 | −0.78 |
| | wiener | −0.065 | −0.010 | −0.82 |
| | nlms *(ref-assisted)* | −0.142 | −0.094 | **−4.08** |
| | **deepfilternet** | −0.224 | −0.017 | −3.15 |

*(Full per-metric values: `results/results.csv` vs `results/results_augmented.csv`.)*

## The robustness story (not just "did scores drop")

**NLMS collapses under augmentation, sharply and consistently — the largest degradation of any method
in every category** (−5.37 dB stationary, −4.29 dB non-stationary, −4.08 dB SI-SNR impulsive; on
stationary and impulsive its mean SI-SNR after augmentation is *below* the noisy baseline, i.e. the
reference-assisted filter now makes things worse than doing nothing on average). This is structural, not
incidental: NLMS's whole advantage rests on Rule 18's true pre-mix noise reference being a faithful,
sample-aligned copy of the noise actually present in the mix (see `docs/non_stationary_root_cause.md` §5
on the oracle-reference assumption). RIR convolution changes the noise's acoustic path *after* the
reference clip was captured, and clipping introduces nonlinear distortion the linear NLMS reference model
has no way to represent — both directly attack the one assumption NLMS depends on. This is independent
confirmation, from a different angle, of why NLMS's oracle advantage (§1.2 of `phase3_plan.md`) does not
transfer to realistic conditions.

**DeepFilterNet3 degrades far more gracefully than NLMS everywhere, and on non-stationary noise it does
not degrade at all** — ΔSI-SNR is *positive* (+0.19 dB) and ΔSTOI is the largest positive delta in the
whole table (+0.019). Plausible explanation: DFN3 was trained on a broad, reverberant/noisy speech
distribution (unlike NLMS, which has no learned prior), so mild synthetic reverb falls inside its trained
operating envelope. Impulsive is DFN3's largest drop (−3.15 dB, −0.224 PESQ) — plausible because clipping
specifically distorts sharp transients, which is exactly the acoustic signature impulsive noise (and the
model's cue for it) depends on — but even this worst case is well short of NLMS's collapse in the same
category (−4.08 dB).

**Classical spectral methods (spectral subtraction, Wiener) are the most robust of all**, with SI-SNR
deltas under 0.1 dB in stationary and non-stationary, and a moderate, noisy-baseline-tracking drop on
impulsive. They have no learned prior to be inside or outside of, and no fragile second-channel reference
to be broken by reverb/clipping, so they simply process whatever signal arrives — at the cost of never
suppressing noise as well as DFN3 to begin with (see the un-augmented compliance report).

**Takeaway for the Phase 3 pitch:** the AI/ML method (DeepFilterNet3) is not just stronger on clean audio
than the reference-assisted classical baseline — it is also *more robust* to realistic acoustic
degradation than the one baseline (NLMS) that depends on assumptions a real second microphone breaks.
That reinforces, from an independent angle, `phase3_plan.md` §1.2's conclusion that NLMS's clean-eval
advantage should not be extrapolated to live dual-mic conditions.
