# PS26052 ANC — Phase 4 Target Compliance Report
**Generated:** 2026-08-24 (regenerated — see dataset correction note below)
**Method evaluated:** DeepFilterNet3 (AI/ML speech enhancement)
**Dataset:** 300 mixtures · 3 noise categories · 5 SNR levels (−5 to +15 dB, 20-file increments)
**Evaluation pairs:** 1,500 · PESQ-WB valid: **1,500 / 1,500 (0 exclusions)**

---

## Dataset Correction Note (2026-08-24)

> [!WARNING]
> **This report supersedes the 2026-08-23 version.** The prior evaluation's impulsive-category noise pool was silently missing the gunshot (2,148 files) and artillery (30 files) corpora — `data/noise/impulsive/` contained only the 40-file `explosion` (ESC-50 fireworks proxy) subtype, due to an incomplete Zenodo download that a manifest-regeneration commit papered over instead of surfacing as an error. All 100 "impulsive" mixtures in that run were actually explosion-only, despite being labeled and reported throughout the documentation as "Gunshot/Artillery." Stationary and non-stationary were never affected (their noise corpora were always complete).
>
> The gunshot/artillery corpus (Zenodo Record 7004819, CC BY 4.0) has been re-fetched and the full pipeline (manifest → mixtures → baselines → DeepFilterNet → evaluation) regenerated end to end. **The corrected impulsive numbers are stronger than what was previously reported**, not weaker — see Section 1.
>
> The original script that produced the documented 30-file "artillery" proxy subset was not preserved in the repository, so it could not be bit-for-bit reproduced. The corpus (2,148 files across 4 firearm types) was re-split using the same documented rationale (`data/SOURCES.md`: "large-caliber firearm shots selected to simulate artillery") — all 2,148 files used as `gunshot` (matches the documented count exactly), and the first 30 files (sorted, deterministic) from `remington_870_12_gauge` (12-gauge shotgun, the highest-energy/largest-caliber of the four types) used as the `artillery` proxy subset.

---

## Terminology & Substitution Notes

> [!IMPORTANT]
> **SI-SNR substitution for PS "SNR > 15 dB" criterion:** PS26052 states "SNR > 15 dB" as a target. This evaluation uses **SI-SNR (Scale-Invariant Signal-to-Noise Ratio)** computed against the paired `clean_ref_path` as the measurable substitute. SI-SNR is scale-invariant and reproducible against a clean reference — more rigorous than raw segSNR for this synthetic-corpus evaluation. This substitution is explicit; it does not extend to any claim about raw hardware SNR.

> [!IMPORTANT]
> **PESQ-WB is SNR-input-dependent.** At higher input SNR levels, the model has less noise to suppress and outputs score higher. The compliance verdict below uses the **full category mean across all five input SNR levels (−5 to +15 dB)**. Per-SNR breakdowns are shown as supplementary context in Section 3 and are clearly labeled as conditional slices — they are not substituted for the overall verdict.

> [!NOTE]
> **System description:** What is built is AI/ML-enabled adaptive **noise suppression / speech enhancement** (single-channel DeepFilterNet + one reference-assisted adaptive filter baseline). This is not true Active Noise Cancellation in the acoustic anti-noise / secondary-path sense. "ANC" appears in report titles only to match PS26052's own problem-statement language.

> [!NOTE]
> **NLMS is a reference-assisted baseline, not a single-channel method.** NLMS uses the true oracle pre-mix noise clip as a separate second-channel reference input. The other methods (Spectral Subtraction, Wiener, DeepFilterNet) operate on the single noisy channel only. NLMS results are not directly comparable to single-channel methods; they are shown on a separate track.

---

## 1. Per-Category Target Compliance Matrix

*Targets: SI-SNR > 15 dB · STOI > 0.85 · PESQ-WB > 2.5*

| Noise Category | SI-SNR Mean (>15 dB) | STOI Mean (>0.85) | PESQ-WB Mean (>2.5) | Overall |
|---|---|---|---|---|
| **Stationary** (Engine / Vehicle) | **16.14 dB — ✅ PASS** | **0.9169 — ✅ PASS** | **2.4823 — ❌ FAIL** (−0.018) | **2 of 3 PASS** |
| **Non-Stationary** (Helicopter / Crowd) | **10.75 dB — ❌ FAIL** (−4.25 dB) | **0.8297 — ❌ FAIL** (−0.020) | **2.1303 — ❌ FAIL** (−0.370) | **0 of 3 PASS** |
| **Impulsive** (Gunshot / Artillery) | **15.75 dB — ✅ PASS** | **0.9319 — ✅ PASS** | **2.5841 — ✅ PASS** (+0.084) | **3 of 3 PASS** |

### Verdict Summary

- **SI-SNR:** 2 of 3 categories pass. Non-stationary fails at **10.75 dB** (−4.25 dB below target).
- **STOI:** 2 of 3 categories pass. Non-stationary fails at **0.8297** (−0.020 below target).
- **PESQ-WB: 1 of 3 categories pass** on the full SNR-averaged evaluation — **impulsive now passes** (2.5841, +0.084 headroom) with the corrected dataset. Stationary (2.48) narrowly misses. Non-stationary (2.13) misses substantially.

> [!WARNING]
> **Do not average across categories to produce a single PESQ headline number.** The non-stationary gap (2.13) would be obscured by the stationary/impulsive results (2.48, 2.58) if averaged. The non-stationary category is the most significant remaining gap — see `docs/non_stationary_root_cause.md` for why it's specifically the crowd/babble subtype, not helicopter.

---

## 2. Detailed Per-Category Breakdown

### 2.1 Stationary Noise (Engine / Vehicle)
| Metric | Value | Target | Gap | Verdict |
|---|---|---|---|---|
| SI-SNR | **16.14 dB** | > 15 dB | +1.14 dB headroom | ✅ **PASS** |
| STOI | **0.9169** | > 0.85 | +0.067 headroom | ✅ **PASS** |
| PESQ-WB | **2.4823** | > 2.5 | −0.018 | ❌ **FAIL** |

### 2.2 Non-Stationary Noise (Helicopter / Crowd)
| Metric | Value | Target | Gap | Verdict |
|---|---|---|---|---|
| SI-SNR | **10.75 dB** | > 15 dB | −4.25 dB | ❌ **FAIL** |
| STOI | **0.8297** | > 0.85 | −0.020 | ❌ **FAIL** |
| PESQ-WB | **2.1303** | > 2.5 | −0.370 | ❌ **FAIL** |

*The entire category gap is driven by the crowd/babble subtype, not helicopter. See `docs/non_stationary_root_cause.md`: on helicopter alone, DeepFilterNet scores STOI 0.9108 and +8.9 dB ΔSI-SNR — on par with the strongest categories. On crowd babble, STOI is 0.7080 (below the unprocessed noisy baseline, 0.7196) and ΔSI-SNR is +1.03 dB, the smallest gain of every method tested including the classical baselines. Root cause: crowd babble is synthetic multi-speaker overlap (other human speech), and single-channel enhancers structurally cannot separate target speech from background speech without a second microphone or speaker-conditioning input (the cocktail-party problem) — a known limitation of the model class, not a defect specific to this checkpoint.*

### 2.3 Impulsive Noise (Gunshot / Artillery)
| Metric | Value | Target | Gap | Verdict |
|---|---|---|---|---|
| SI-SNR | **15.75 dB** | > 15 dB | +0.75 dB headroom | ✅ **PASS** |
| STOI | **0.9319** | > 0.85 | +0.082 headroom | ✅ **PASS** |
| PESQ-WB | **2.5841** | > 2.5 | +0.084 headroom | ✅ **PASS** |

*Impulsive is the only category that passes all three DRDO targets. The NLMS reference-assisted baseline collapses badly on impulsive noise (ΔSI-SNR = **−7.10 dB**), a confirmed structural limitation of gradient-based adaptive filters on rapid acoustic transients (convergence lag) — not a dataset or alignment bug (see the zero-lag cross-correlation ablation in `docs/phase_4_summary.md`). DeepFilterNet maintains strong performance (SI-SNR +10.75 dB, STOI 0.9319) because it classifies noise spectrally rather than tracking adaptively, and the gap between DeepFilterNet and NLMS on real gunshot/artillery transients (+10.75 dB vs. −7.10 dB, a ~18 dB spread) is now the sharpest AI/ML-vs-classical contrast in the entire evaluation.*

---

## 3. Supplementary: PESQ-WB by Input SNR Level (DeepFilterNet), per category

*SNR-conditional slices for analytical context only — not the compliance verdict. Computed per category; a prior version of this table appears to have applied one category's breakdown to more than one category's narrative text.*

**Stationary**

| Input SNR | Mean PESQ-WB | N | % above 2.5 |
|---|---|---|---|
| −5 dB | 1.71 | 20 | 0.0% |
| 0 dB | 2.09 | 20 | 10.0% |
| +5 dB | 2.58 | 20 | 45.0% |
| +10 dB | 2.86 | 20 | 80.0% |
| +15 dB | 3.17 | 20 | 100.0% |

**Non-stationary**

| Input SNR | Mean PESQ-WB | N | % above 2.5 |
|---|---|---|---|
| −5 dB | 1.41 | 20 | 0.0% |
| 0 dB | 1.74 | 20 | 20.0% |
| +5 dB | 2.24 | 20 | 35.0% |
| +10 dB | 2.53 | 20 | 55.0% |
| +15 dB | 2.73 | 20 | 80.0% |

**Impulsive**

| Input SNR | Mean PESQ-WB | N | % above 2.5 |
|---|---|---|---|
| −5 dB | 1.87 | 20 | 5.0% |
| 0 dB | 2.44 | 20 | 45.0% |
| +5 dB | 2.72 | 20 | 70.0% |
| +10 dB | 2.94 | 20 | 85.0% |
| +15 dB | 2.95 | 20 | 75.0% |

---

## 4. Classical Baselines (Reference-Assisted Track)

> [!NOTE]
> **NLMS is shown on a separate reference-assisted track.** It receives the true oracle pre-mix noise clip as a second-channel reference — an input assumption the deployed system and single-channel methods do not have. Its results are not directly comparable to Spectral Subtraction, Wiener, or DeepFilterNet.

| Category | Method | PESQ-WB | STOI | ΔSI-SNR |
|---|---|---|---|---|
| Stationary | Noisy (baseline) | 1.38 | 0.820 | 0.00 dB |
| | Spectral Subtraction | 1.42 | 0.823 | +1.25 dB |
| | Wiener Filter | 1.49 | 0.833 | +3.23 dB |
| | NLMS *(ref-assisted)* | 1.45 | 0.901 | +3.97 dB |
| | **DeepFilterNet** | **2.48** | **0.917** | **+11.10 dB** |
| Non-Stationary | Noisy (baseline) | 1.40 | 0.785 | 0.00 dB |
| | Spectral Subtraction | 1.43 | 0.786 | +0.76 dB |
| | Wiener Filter | 1.45 | 0.791 | +1.76 dB |
| | NLMS *(ref-assisted)* | 1.40 | 0.880 | +2.86 dB |
| | **DeepFilterNet** | **2.13** | **0.830** | **+5.75 dB** |
| Impulsive | Noisy (baseline) | 1.66 | 0.858 | 0.00 dB |
| | Spectral Subtraction | 1.69 | 0.859 | +0.12 dB |
| | Wiener Filter | 1.63 | 0.859 | +0.27 dB |
| | NLMS *(ref-assisted)* | 1.31 | 0.818 | **−7.10 dB** |
| | **DeepFilterNet** | **2.58** | **0.932** | **+10.75 dB** |

---

*Source data: `results/eval_raw.csv` (1,500 rows, regenerated 2026-08-24), `results/results.csv`. Machine-readable version: `results/final/target_compliance.json`.*
