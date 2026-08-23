# PS26052 ANC — Phase 4 Target Compliance Report
**Generated:** 2026-08-23  
**Method evaluated:** DeepFilterNet3 (AI/ML speech enhancement)  
**Dataset:** 300 mixtures · 3 noise categories · 5 SNR levels (−5 to +15 dB, 20-file increments)  
**Evaluation pairs:** 1,500 · PESQ-WB valid: **1,500 / 1,500 (0 exclusions)**

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
| **Impulsive** (Gunshot / Artillery) | **15.20 dB — ✅ PASS** | **0.9196 — ✅ PASS** | **2.4916 — ❌ FAIL** (−0.008) | **2 of 3 PASS** |

### Verdict Summary

- **SI-SNR:** 2 of 3 categories pass. Non-stationary fails at **10.75 dB** (−4.25 dB below target).
- **STOI:** 2 of 3 categories pass. Non-stationary fails at **0.8297** (−0.020 below target).
- **PESQ-WB: 0 of 3 categories pass on the full SNR-averaged evaluation.** Stationary (2.48) and impulsive (2.49) narrowly miss. Non-stationary (2.13) misses substantially.

> [!WARNING]
> **Do not average across categories to produce a single PESQ headline number.** The non-stationary gap (2.13) would be obscured by the stationary/impulsive results (2.48, 2.49) if averaged. The non-stationary category is the most significant remaining gap and should be reported and investigated as such.

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

*Non-stationary noise (helicopter rotor harmonics, crowd babble) presents the hardest suppression problem for DeepFilterNet3. The model was pre-trained primarily on stationary and speech noise profiles; helicopter harmonics and fluctuating crowd noise fall outside its strongest generalisation domain. This is the primary remaining gap for Phase 5/6 investigation.*

### 2.3 Impulsive Noise (Gunshot / Artillery)
| Metric | Value | Target | Gap | Verdict |
|---|---|---|---|---|
| SI-SNR | **15.20 dB** | > 15 dB | +0.20 dB headroom | ✅ **PASS** |
| STOI | **0.9196** | > 0.85 | +0.070 headroom | ✅ **PASS** |
| PESQ-WB | **2.4916** | > 2.5 | −0.008 | ❌ **FAIL** |

*The impulsive PESQ-WB miss (−0.008) is the narrowest across all categories. Note that the NLMS reference-assisted baseline degrades on impulsive noise (ΔSI-SNR = −3.30 dB), a confirmed structural limitation of gradient-based adaptive filters on rapid acoustic transients — not a dataset or alignment bug. DeepFilterNet maintains strong performance (SI-SNR +10.19 dB, STOI 0.9196) because it classifies noise spectrally rather than tracking adaptively.*

---

## 3. Supplementary: PESQ-WB by Input SNR Level (DeepFilterNet)

*These are SNR-conditional slices for analytical context only. They are not the compliance verdict.*

| Input SNR Level | Mean PESQ-WB | N | % above 2.5 target |
|---|---|---|---|
| −5 dB | 1.59 | 60 | — |
| 0 dB | 2.09 | 60 | — |
| +5 dB | 2.47 | 60 | — |
| **+10 dB** | **2.76** | 60 | **76.7%** |
| **+15 dB** | **2.92** | 60 | **85.0%** |

*At input SNR ≥ +10 dB, the majority of individual mixtures exceed PESQ-WB 2.5. This is because higher input SNR means less noise to suppress, so the model's enhancement task is easier. The DRDO target of PESQ > 2.5 is most realistic in higher-SNR operating conditions.*

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
| Impulsive | Noisy (baseline) | 1.55 | 0.831 | 0.00 dB |
| | Spectral Subtraction | 1.57 | 0.832 | +0.19 dB |
| | Wiener Filter | 1.53 | 0.834 | +0.47 dB |
| | NLMS *(ref-assisted)* | 1.32 | 0.833 | −3.30 dB |
| | **DeepFilterNet** | **2.49** | **0.920** | **+10.19 dB** |

---

*Source data: `results/eval_raw.csv` (1,500 rows), `results/results.csv`. Machine-readable version: `results/final/target_compliance.json`.*
