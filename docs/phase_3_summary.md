# Summary Report — Phase 3 Execution
**Smart India Hackathon 2026 | DRDO Problem Statement 26052**  
*AI/ML-Enabled Adaptive Noise Cancellation (ANC) for Defence Communications*  
**Scope:** Phase 3 — Classical DSP Baselines Implementation & Execution  

---

## 1. Executive Summary

Phase 3 implemented three classical Digital Signal Processing (DSP) baseline algorithms—**Spectral Subtraction**, **Wiener Filter**, and **Normalized Least Mean Squares (NLMS) Adaptive Filter**—from first principles and executed them across all 300 synthetic mixtures from Phase 2. 

A total of **900 enhanced `.wav` audio files** were generated at **48,000 Hz** (48 kHz) into `results/baselines/`, accompanied by a joined dataset manifest ([results/baseline_manifest.csv](file:///d:/Coding/defence_anc/results/baseline_manifest.csv)). All 900 output files passed 100% of internal quality and sanity checks (non-silent, zero NaNs/Infs, 48 kHz sample rate, peak $\le 0.95$).

---

## 2. Algorithm Formulations & Hyperparameters

Every algorithm was implemented from first principles using standard textbook formulations to establish rigorous baseline benchmarks for comparison against DeepFilterNet in Phase 4.

### 2.1 Spectral Subtraction (`baselines/spectral_subtraction/spectral_subtraction.py`)
- **Formulation:** Berouti et al. / Boll STFT spectral over-subtraction with spectral floor.
- **STFT Configuration:** Hann window, $N_{\text{fft}} = 1024$ (21.3 ms at 48 kHz), hop length $H = 256$ (75% overlap).
- **Subtracted Power & Floor:**
  $$|\hat{S}(m, k)|^2 = \max\left( |Y(m, k)|^2 - \alpha \cdot |\hat{N}(k)|^2, \; \beta \cdot |Y(m, k)|^2 \right)$$
  - Over-subtraction factor $\alpha = 2.0$
  - Spectral floor factor $\beta = 0.02$ ($-17 \text{ dB}$)
- **Noise Estimation:** 15th percentile magnitude across STFT frames (minimum-statistics quantile estimation, robust for full-clip noise coverage).

### 2.2 Wiener Filter (`baselines/wiener/wiener.py`)
- **Formulation:** Norbert Wiener / Scalart & Vieira-Filho Decision-Directed (DD) a priori SNR estimation.
- **STFT Configuration:** Hann window, $N_{\text{fft}} = 1024$, hop length $H = 256$.
- **Decision-Directed A Priori SNR & Wiener Gain:**
  $$\xi(m, k) = \alpha_{\text{DD}} \cdot \frac{|\hat{S}(m-1, k)|^2}{P_n(k)} + (1 - \alpha_{\text{DD}}) \cdot \max(\gamma(m, k) - 1, 0), \quad H_{\text{Wiener}}(m, k) = \frac{\xi(m, k)}{\xi(m, k) + 1}$$
  - Smoothing factor $\alpha_{\text{DD}} = 0.98$
  - Noise power spectrum $P_n(k)$ estimated via 15th percentile frame magnitude squared.

### 2.3 NLMS Adaptive Filter (`baselines/nlms/nlms.py`)
- **Formulation:** Widrow / Haykin sample-by-sample normalized weight adaptation.
- **Filter Parameters:** Taps $L = 64$, normalized step size $\mu = 0.1$, regularization $\epsilon = 10^{-6}$.
- **Weight Update Equation:**
  $$\mathbf{w}[n+1] = \mathbf{w}[n] + \frac{\mu}{\|\mathbf{x}[n]\|^2 + \epsilon} \cdot e[n] \cdot \mathbf{x}[n]$$
- **Rule 18 Traceability:** Reference channel $x[n]$ strictly uses the true original pre-mix noise clip traced via `noise_id` under `data/noise/` (100% 300/300 trace audit passed).
- **Execution Acceleration:** Numba JIT compiled kernel running at **`14.4 M samples/sec`**.

---

## 3. Pilot Timing Benchmarks & Full Batch Execution

Per Rule 19, a 10-file pilot benchmark was executed prior to the full batch run to measure processing throughput and extrapolate total runtime.

| Algorithm | Pilot Time (10 files) | Per-File Latency | Extrapolated Time (300 files) | Actual Batch Runtime (300 files) |
|---|---|---|---|---|
| **Spectral Subtraction** | 0.3655 s | 36.6 ms | 10.97 s | **15.45 s** |
| **Wiener Filter** | 0.2889 s | 28.9 ms | 8.67 s | **12.98 s** |
| **NLMS Adaptive Filter** | 0.6115 s | 61.1 ms | 18.34 s | **7.87 s** |
| **Total Pipeline** | **1.2659 s** | **126.6 ms** | **37.98 s** | **36.30 s** |

Because total runtime extrapolated to **`37.98 seconds`** (< 2 minutes), all three baselines were executed directly in Mode A without requiring background delegation.

---

## 4. Quality Control & Internal Sanity Audit (Rule 21)

Every baseline output file was subjected to automated sanity checks prior to manifest logging.

| Verification Criteria | Threshold / Requirement | Result |
|---|---|---|
| **File Parity** | 300 `.wav` files created per method | **900 / 900 files verified** |
| **Signal RMS** | $\text{RMS} > 10^{-4}$ (non-silent output) | **300/300 per method passed** |
| **Numerical Integrity** | Zero `NaN` or `Inf` floating point values | **300/300 per method passed** |
| **Sample Rate** | Preserved at native 48,000 Hz | **300/300 per method passed** |
| **Peak Amplitude** | Peak $\le 0.95$ (zero digital clipping) | **300/300 per method passed** |
| **Rule 21 Compliance** | Zero PESQ/STOI/SI-SNR metrics computed in Phase 3 | **100% compliant** |

---

## 5. Baseline Manifest Structure (`results/baseline_manifest.csv`)

The baseline manifest joins the Phase 2 mixture metadata with the Phase 3 outputs across 900 rows:
- `mixture_id`: Filename of the input mixture (`mix_*.wav`)
- `method`: `spectral_subtraction`, `wiener`, or `nlms`
- `output_path`: Relative path to enhanced output (`results/baselines/<method>/mix_*.wav`)
- `clean_ref_path`: Relative path to matched clean reference (`data/mixtures/clean_ref_*.wav`)
- `category`: `stationary`, `non_stationary`, or `impulsive`
- `subtype`: `engine`, `vehicle`, `helicopter`, `crowd`, `gunshot`, `explosion`, `artillery`
- `snr_db`: Mixture SNR level (`-5.0, 0.0, 5.0, 10.0, 15.0`)

---

## 6. Phase 3 Definition of Done Checklist

- [x] All three algorithms implemented from first principles matching standard textbook formulations.
- [x] NLMS confirmed to use true pre-mix reference noise clip (Rule 18, 300/300 traced).
- [x] Pilot timing benchmark completed and logged (37.98s extrapolated total).
- [x] All 300 mixtures processed through all three methods (900 `.wav` outputs generated in 36.30s).
- [x] `results/baseline_manifest.csv` created (900 rows joined against Phase 2 manifest).
- [x] Per-method sanity checks passed (100.0% pass rate).
- [x] Zero PESQ/STOI/SI-SNR metrics computed in Phase 3 (Rule 21).
- [x] `progress.md` and `architecture.md` updated with real, evidence-backed numbers.
- [x] Raspberry Pi isolated from Phase 3 tasks.

---

## 7. Next Steps & Phase 4 Transition

Phase 3 provides the complete set of enhanced audio files needed for **Phase 4 (Objective Evaluation Engine)**:
1. **Evaluation Script (`eval/run_eval.py`)**: Compute PESQ, STOI, and SI-SNR across all 1,200 output files (300 Unprocessed Noisy + 300 Spectral Subtraction + 300 Wiener + 300 NLMS + 300 DeepFilterNet baseline).
2. **Category-Level Analysis**: Benchmark speech intelligibility preservation and noise reduction across stationary, non-stationary, and impulsive defence noise categories.
