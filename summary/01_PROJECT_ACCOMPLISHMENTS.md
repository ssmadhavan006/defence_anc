# PS26052 — Complete Project Accomplishments Record
**Smart India Hackathon 2026 · DRDO Problem Statement 26052**
*AI/ML-Enabled Adaptive Noise Cancellation for Defence Communications*

**Record compiled:** 2026-08-24
**Scope:** Everything accomplished from project inception (Phase 0) through the post-Phase-5 hardening pass, with empirical evidence for every claim.
**Deployment target:** Raspberry Pi 5 (edge), developed on Windows dev machine.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement Requirement Mapping](#2-problem-statement-requirement-mapping)
3. [Phase 0 — Repository & Environment Setup](#3-phase-0--repository--environment-setup)
4. [Phase 1 — DeepFilterNet Baseline & Pi 5 RTF Benchmarking](#4-phase-1--deepfilternet-baseline--pi-5-rtf-benchmarking)
5. [Phase 2 — Defence Noise Dataset Synthesis](#5-phase-2--defence-noise-dataset-synthesis)
6. [Phase 3 — Classical DSP Baselines](#6-phase-3--classical-dsp-baselines)
7. [Phase 4 — Objective Evaluation Engine](#7-phase-4--objective-evaluation-engine)
8. [Phase 5 — Real-Time Live Pipeline on Raspberry Pi 5](#8-phase-5--real-time-live-pipeline-on-raspberry-pi-5)
9. [Post-Phase-5 Hardening Pass](#9-post-phase-5-hardening-pass)
10. [Incidents Found & Fixed (Engineering Integrity Record)](#10-incidents-found--fixed-engineering-integrity-record)
11. [Final Results & DRDO Target Compliance](#11-final-results--drdo-target-compliance)
12. [Complete Repository Inventory](#12-complete-repository-inventory)
13. [Verification Status — What Is Proven vs What Is Not](#13-verification-status--what-is-proven-vs-what-is-not)

---

## 1. Executive Summary

The project delivers a complete, reproducible, end-to-end pipeline for AI/ML-enabled speech enhancement in defence acoustic environments, built across a two-machine model (**Windows dev machine = laboratory**, **Raspberry Pi 5 = product**), and validated with real measurements on the actual target hardware rather than extrapolated desktop numbers.

**What exists and works today:**

| Capability | Status | Where proven |
|---|---|---|
| Reproducible defence-noise dataset generator (300 seeded mixtures, 48 kHz) | ✅ Complete | `data/manifest.csv`, 600 wav files on disk |
| Three classical DSP baselines from first principles (Spectral Subtraction, Wiener, NLMS) | ✅ Complete | 900 enhanced files, 100% sanity checks passed |
| DeepFilterNet3 batch inference engine | ✅ Complete | 300 enhanced files, 77.29 s runtime |
| Full objective evaluation (PESQ-WB, STOI, SI-SNR, ΔSI-SNR) across 5 conditions × 3 categories | ✅ Complete | `results/eval_raw.csv`, 1500 rows, 0 exclusions |
| DeepFilterNet3 running on Raspberry Pi 5 with measured RTF | ✅ Complete | `results/rtf_pi.json`, median RTF 0.17037 (4-thread) |
| Real-time streaming pipeline (capture → ring buffer → inference → playback) | ✅ Complete | `live/pipeline.py`, running on Pi 5 |
| 10-minute continuous stability gate | ✅ Passed | 600.3 s, 0 dropouts, max 50.1 °C |
| ENHANCE / BYPASS live toggle for A/B demonstration | ✅ Complete | `demo/dashboard.py`, verified on Pi |
| Live visual spectrogram (before/after) | ✅ Built | `demo/spectrogram.py`, self-test passing |
| Clean Pi deployment packaging | ✅ Complete | `pi_deploy.zip`, 15 files, excludes datasets |

**Headline technical result:** On the corrected dataset, DeepFilterNet3 clears **all three DRDO targets simultaneously on impulsive defence noise** (real gunshot/artillery): SI-SNR **+15.75 dB** (target >15), STOI **0.9319** (target >0.85), PESQ-WB **2.5841** (target >2.5) — while the classical reference-assisted NLMS adaptive filter *degrades* the signal by **−7.10 dB ΔSI-SNR** on the same noise. That ~18 dB spread between AI/ML and classical adaptive filtering on rapid acoustic transients is the single strongest evidence in the project for the necessity of a learned model in defence communications.

**Honest scope boundary:** the live pipeline has been validated on the Pi 5 using the **ALSA `snd-aloop` virtual loopback device**, not a physical USB microphone, and the reported "29.18 ms latency" is *model inference time per chunk*, not end-to-end acoustic mouth-to-ear latency. Both gaps are documented in detail in Section 13 and are the top priorities in the companion plan document.

---

## 2. Problem Statement Requirement Mapping

PS26052 lists five expected deliverables. Current status against each:

| # | PS26052 Expected Solution Component | Status | Evidence / Gap |
|---|---|---|---|
| 1 | **A scalable dataset pipeline for generating realistic noisy-clean speech pairs** | ✅ **Delivered** | `data/mix_dataset.py` — seeded, deterministic, 48 kHz, 3 categories × 7 subtypes × 5 SNR levels, 0.0000 dB mean SNR deviation, manifest-verified parity. Regenerable bit-for-bit from `data/manifest.csv`. |
| 2 | **A state-of-the-art AI/ML model trained for robust noise suppression** | ⚠️ **Partial** | Pretrained **DeepFilterNet3** (multi-stage ERB-scale complex-domain deep filtering, 48 kHz native) integrated and fully evaluated. **No defence-specific fine-tuning performed** — Round 1 scope deliberately used the pretrained checkpoint to establish a baseline and identify weaknesses. |
| 3 | **A training framework with optimized hyper-parameters and perceptual loss functions** | ❌ **Not built** | Investigated in depth: DeepFilterNet's training loop requires `libdfdata`, a Rust-compiled HDF5 dataloader not published to PyPI, plus dataset conversion to their HDF5 schema. Scoped at 4–8 h with real build risk; deferred as out of Round-1 critical path. |
| 4 | **A real-time inference engine deployable on edge hardware** | ✅ **Delivered** | `live/` package running on Raspberry Pi 5: lock-free SPSC ring buffers, decoupled inference thread, non-blocking audio callbacks, RTF 0.29–0.38 (2.6–3.4× faster than real time), 10-minute zero-dropout stability gate passed. |
| 5 | **A prototype demonstrating live noise cancellation using microphones / headset integration** | ⚠️ **Partial** | Full software pipeline + ENHANCE/BYPASS toggle + TUI dashboard + live spectrogram all running on the Pi. **Validated on ALSA virtual loopback, not a physical USB microphone or headset.** This is the single largest remaining gap for the prototype evaluation round. |

**Quantitative targets stated in PS26052:**

| Target | Stationary | Non-Stationary | Impulsive |
|---|---|---|---|
| SNR > 15 dB *(measured as SI-SNR)* | **16.14 dB ✅** | 10.75 dB ❌ | **15.75 dB ✅** |
| STOI > 0.85 | **0.9169 ✅** | 0.8297 ❌ | **0.9319 ✅** |
| PESQ > 2.5 | 2.4823 ❌ *(−0.018)* | 2.1303 ❌ *(−0.370)* | **2.5841 ✅** |

**Additional PS26052 techniques mentioned but not yet implemented:** data augmentation (reverberation/RIR, clipping), model optimization (quantization, pruning, ONNX/TensorRT), primary + reference dual-microphone hardware integration, and an integrated lightweight LMS residual-suppression stage in the live path. All are enumerated with concrete implementation plans in `02_NEXT_STEPS_PLAN.md`.

---

## 3. Phase 0 — Repository & Environment Setup

### 3.1 Two-Machine Operational Model

The project was deliberately architected around a strict separation that mirrors real embedded-systems practice:

- **COMPUTER (Development Laboratory):** dataset synthesis, DSP baseline development, evaluation engine, model packaging, deployment preparation. Heavy storage and compute live here permanently.
- **RASPBERRY PI 5 (Edge Deployment Target / Product):** model runtime, live audio capture and playback, real-time inference, latency and thermal measurement, demonstration surface. Carries only what the running system needs.

This split was enforced throughout — the Pi never generated a dataset, never ran an evaluation, and never stored the 300-mixture corpus.

### 3.2 Persistent Engineering-Discipline Memory System

Three living documents were established at project start and maintained continuously:

| File | Purpose |
|---|---|
| `progress.md` | Append-only chronological execution log. Every task records: what was done, the exact commands run, verbatim command output as evidence, the result, and the next step. |
| `rules.md` | Explicit engineering rules governing anti-hallucination, mandatory command-output validation, scope discipline, and machine-attribution honesty (e.g. Rule 29: no Mode B test may be marked passed without real pasted-back Pi output). |
| `architecture.md` | Living repository structure, data flow diagrams, component matrix, and a dated decisions log. |

This system is a genuine differentiator: it is why the two significant data integrity incidents described in Section 10 were caught and corrected rather than shipped.

### 3.3 Verified Environment Specifications

| Component | Development Machine | Raspberry Pi 5 |
|---|---|---|
| OS | Windows 11 (26200) | Debian GNU/Linux 13 (trixie), kernel 6.12, 64-bit |
| CPU | x86-64 (+ RTX 5070 GPU, unused in Round 1) | Broadcom BCM2712, quad-core ARM Cortex-A76 @ 2.4 GHz |
| RAM | — | 8 GB LPDDR4X |
| Python | 3.11.16 (`uv`-managed virtualenv) | 3.13.5 (`anc_env` virtualenv) |
| Core stack | PyTorch 2.5.1, torchaudio 2.5.1, DeepFilterNet 0.5.6, numba, scipy, pystoi, pesq (custom-built), matplotlib/seaborn | PyTorch 2.6+ CPU build, DeepFilterNet, soundfile, sounddevice 0.5.6, PortAudio |
| Audio infra | — | ALSA + `snd-aloop` loopback module |

### 3.4 Repository Structure Created

The specified structure was created in full: `data/{clean,noise,mixtures}`, `baselines/{spectral_subtraction,wiener,nlms}`, `eval/`, `models/deepfilternet/`, `live/`, `results/`, `demo/`, plus `config/`, `scripts/`, and `docs/` added as the work demanded.

---

## 4. Phase 1 — DeepFilterNet Baseline & Pi 5 RTF Benchmarking

### 4.1 Model Selection & Rationale

**DeepFilterNet3** was selected as the AI/ML core:

- Operates **natively at 48 kHz** — matching the target audio pipeline exactly, with no resampling stage in the real-time path (a meaningful latency and quality advantage over 16 kHz models).
- **Multi-stage deep filtering** using ERB-scale (perceptually-spaced) band processing combined with complex-domain deep filtering, which **preserves phase information** — directly matching PS26052's stated requirement that models "operate in the complex domain to preserve phase information."
- Designed and published explicitly for **real-time, low-complexity** operation, making it a defensible choice for embedded deployment.

### 4.2 Key Software Components Built

**1. Universal Compatibility Polyfill — `models/deepfilternet/df_compat.py`**

DeepFilterNet 0.5.6 is incompatible with modern PyTorch/Python on both platforms. Two hard failures were solved:
- `ModuleNotFoundError: No module named 'torchaudio.backend'` (PyTorch 2.6+ removed the legacy backend module)
- `ImportError: TorchCodec is required for load_with_torchcodec` (Python 3.13 / newer torchaudio audio-loading path)

The polyfill overrides `df.io.load_audio`, `df.io.save_audio`, `torchaudio.load`, `torchaudio.save`, and `torchaudio.info` with pure `soundfile` + `torch` implementations, completely isolating the audio I/O layer from upstream churn. **This single file is what makes the model run on both Windows dev and Debian ARM Pi 5 from one codebase.**

**2. Batch Inference Engine — `models/deepfilternet/run_inference.py`**
Manifest-driven, idempotent/resumable (skips already-processed files), with internal assertions verifying output sample rate (48 kHz), file existence, and duration preservation. Includes a self-contained smoke test (`--self-test`).

**3. Edge Benchmark Suite — `models/deepfilternet/benchmark_rtf.py`**
Implements the strict benchmarking protocol: 20 runs, first 3 discarded as warm-up, 17 measured; median and p95 latency and RTF; both single-thread and 4-thread PyTorch execution; CPU temperature captured before and after via `/sys/class/thermal/thermal_zone0/temp` and `vcgencmd`.

### 4.3 Empirical Raspberry Pi 5 Benchmark Results

Executed **directly on the Raspberry Pi 5** with a 3.0-second 48 kHz mixture. These are real edge numbers, not desktop extrapolations.

| Parameter | Single-Thread | 4-Thread | Unit |
|---|---|---|---|
| Audio frame duration | 3.00 | 3.00 | seconds |
| Sample rate | 48,000 | 48,000 | Hz (native) |
| **Median processing latency** | 660.98 | **511.10** | ms |
| **P95 processing latency** | 702.76 | **545.57** | ms |
| **Median RTF** | 0.22033 | **0.17037** | ratio (lower better) |
| **P95 RTF** | 0.23425 | **0.18186** | ratio |
| Real-time speedup | ~4.5× | **~5.8×** | × real time |
| CPU temperature range | 41.1 → 45.0 | 43.9 → 47.2 | °C |

**Interpretation:** at RTF 0.17037 on 4 threads, one second of 48 kHz audio costs only ~170 ms of CPU time. This established the **first go/no-go gate** — real-time neural speech enhancement on a Raspberry Pi 5 is computationally viable with ~5.8× headroom, and thermals stay far below the 80 °C throttle point.

---

## 5. Phase 2 — Defence Noise Dataset Synthesis

### 5.1 Corpus Sourcing & Provenance

Every source clip is openly licensed and documented with origin, URL, license, and proxy rationale in `data/SOURCES.md`. No unverified or unlicensed audio was used.

**Clean speech:** LibriSpeech `dev-clean` (OpenSLR Resource 12), CC BY 4.0 — 150 utterances resampled to 48 kHz.

**Noise corpus (2,358 source clips across 3 categories / 7 subtypes):**

| Category | Subtype | Source | License | Files | Rationale |
|---|---|---|---|---|---|
| Stationary | `engine` | ESC-50 (`engine`) | CC BY-NC 3.0 | 40 | Real mechanical engine recordings |
| Stationary | `vehicle` | ESC-50 (`engine`) | CC BY-NC 3.0 | 40 | *Proxy* — acoustically faithful for armored-vehicle hum |
| Non-Stationary | `helicopter` | ESC-50 (`helicopter`) | CC BY-NC 3.0 | 40 | Real rotary-aircraft rotor/engine noise |
| Non-Stationary | `crowd` | LibriSpeech babble generator | CC BY 4.0 | 20 | *Proxy* — synthetic multi-talker babble, 6 overlapping utterances |
| Impulsive | `gunshot` | Zenodo Record 7004819 | CC BY 4.0 | **2,148** | **Real multi-firearm outdoor gunshot recordings** (Kabealo & Wyatt et al., *Data in Brief*, 2022), 4 firearm types |
| Impulsive | `explosion` | ESC-50 (`fireworks`) | CC BY-NC 3.0 | 40 | *Proxy* — blast-impulse acoustic characteristics |
| Impulsive | `artillery` | Zenodo Record 7004819 | CC BY 4.0 | 30 | *Proxy* — 12-gauge (largest-caliber) subset as artillery-class impulse |

The Zenodo gunshot corpus is genuine research-grade defence-relevant audio: 4 firearm types (Glock 17 9 mm, Ruger AR-556 .223, S&W .38, Remington 870 12-gauge), multi-channel, multi-orientation, collected with AFRL involvement.

### 5.2 Mixing Pipeline — `data/mix_dataset.py`

- **Sample-rate standardization:** all clips resampled to 48 kHz using DeepFilterNet's native sinc interpolation kernel before mixing.
- **Seeded reproducibility:** master `--seed` plus per-mixture `combo_seed = seed + mixture_idx` deterministically fixes clean/noise pairing *and* the temporal offset within the noise clip — making every mixture bit-for-bit regenerable and, critically, allowing the NLMS baseline to trace the exact aligned reference noise segment later.
- **Energy-scaled SNR mixing:**

  $$P_s = \tfrac{1}{N}\sum s[n]^2,\quad P_d = \tfrac{1}{N}\sum d[n]^2,\quad a = \sqrt{\frac{P_s}{P_d \cdot 10^{\mathrm{SNR}_{dB}/10}}},\quad \text{mixed}[n] = s[n] + a\cdot d[n]$$

- **Peak normalization** to prevent digital clipping (scales down if peak > 0.95, with `norm_factor` recorded).
- **Paired clean reference written per mixture** (`clean_ref_*.wav`) — scaled identically to the speech component in the mixture, which is what makes SI-SNR and PESQ/STOI scoring valid.

### 5.3 Output & Verification

**300 mixtures** at 48 kHz spanning 3 categories × 5 SNR levels (−5, 0, +5, +10, +15 dB), 20 per combination, plus 300 paired clean references (600 files total).

| Verification | Standard | Result |
|---|---|---|
| Post-mixing SNR accuracy | Recomputed from written audio | **0.0000 dB mean deviation** |
| Sample rate | 48,000 Hz uniform | **300/300** |
| Manifest-to-disk parity | rows == mix files == ref files | **300 == 300 == 300** |
| Category coverage | All 15 (3 cat × 5 SNR) combinations | **No empty combinations** |
| Provenance | License + origin documented | **100% in `data/SOURCES.md`** |

`data/manifest.csv` carries 12 fields per row: `clean_id, noise_id, category, snr_db, seed, output_path, clean_ref_path, subtype, duration_sec, achieved_snr_db, snr_dev_db, norm_factor`.

---

## 6. Phase 3 — Classical DSP Baselines

Three baselines implemented **from first principles** (no library black boxes) to give rigorous, defensible comparison points against the AI/ML model.

### 6.1 Spectral Subtraction — `baselines/spectral_subtraction/spectral_subtraction.py`
Berouti/Boll over-subtraction with spectral floor. Hann window, $N_{fft}=1024$ (21.3 ms @ 48 kHz), hop 256 (75% overlap).

$$|\hat S(m,k)|^2 = \max\!\left(|Y(m,k)|^2 - \alpha|\hat N(k)|^2,\; \beta|Y(m,k)|^2\right)$$

Over-subtraction $\alpha = 2.0$, spectral floor $\beta = 0.02$ (−17 dB). Noise estimated as the 15th-percentile magnitude across STFT frames (minimum-statistics quantile estimation).

### 6.2 Wiener Filter — `baselines/wiener/wiener.py`
Scalart & Vieira-Filho decision-directed a priori SNR estimation (Ephraim–Malah lineage):

$$\xi(m,k) = \alpha_{DD}\frac{|\hat S(m\!-\!1,k)|^2}{P_n(k)} + (1-\alpha_{DD})\max(\gamma(m,k)-1,0),\qquad H(m,k)=\frac{\xi(m,k)}{\xi(m,k)+1}$$

Smoothing $\alpha_{DD} = 0.98$.

### 6.3 NLMS Adaptive Filter — `baselines/nlms/nlms.py`
Widrow/Haykin sample-by-sample normalized weight adaptation, taps $L=64$, step size $\mu = 0.01$, regularization $\epsilon = 10^{-6}$:

$$\mathbf{w}[n\!+\!1] = \mathbf{w}[n] + \frac{\mu}{\|\mathbf{x}[n]\|^2+\epsilon}\,e[n]\,\mathbf{x}[n]$$

- **Reference-channel traceability:** the reference input $x[n]$ is the **true original pre-mix noise clip**, located via the manifest's `noise_id` and time-aligned using the recorded `combo_seed` — a 300/300 verified trace. This makes NLMS an *oracle* baseline, which is disclosed everywhere it is reported.
- **Numba JIT-compiled kernel** achieving ~14.4 M samples/sec.

### 6.4 Execution & Quality Control

All three run over all 300 mixtures → **900 enhanced files** at 48 kHz.

| Algorithm | Batch runtime (300 files) |
|---|---|
| Spectral Subtraction | 56.95 s |
| Wiener Filter | 18.89 s |
| NLMS Adaptive Filter | 11.03 s |
| **Total** | **86.86 s** |

Every output passed automated sanity checks before manifest logging: **900/900** non-silent (RMS > 1e-4), zero NaN/Inf, sample rate preserved at 48 kHz, peak ≤ 0.95 (no clipping). `results/baseline_manifest.csv` joins all 900 rows against the Phase 2 metadata.

---

## 7. Phase 4 — Objective Evaluation Engine

### 7.1 Metrics Implemented — `eval/metrics.py`, `eval/run_eval.py`

| Metric | Standard | Purpose |
|---|---|---|
| **PESQ-WB** | ITU-T P.862.2 wideband | Perceptual speech quality (DRDO target > 2.5) |
| **STOI** | Short-Time Objective Intelligibility | Intelligibility (DRDO target > 0.85) |
| **SI-SNR** | Scale-invariant SNR vs paired clean reference | Noise suppression (DRDO target > 15 dB) |
| **ΔSI-SNR** | SI-SNR(method) − SI-SNR(noisy) | Genuine improvement attributable to the method |

**Documented substitution:** PS26052 states "SNR > 15 dB". The evaluation uses **SI-SNR** computed against the paired `clean_ref_path`, because it is scale-invariant and reproducible against a known clean reference — more rigorous than raw segSNR for a synthetic corpus. This substitution is stated explicitly in `results/final/target_compliance.md` and does not extend to any claim about raw hardware SNR.

### 7.2 Evaluation Scale

**5 conditions × 300 mixtures = 1,500 condition-mixture pairs**, all scored, **0 exclusions**:
Unprocessed Noisy · Spectral Subtraction · Wiener · NLMS · DeepFilterNet.

Runtime 221.87 s. Outputs: `results/eval_raw.csv` (1,500 per-mixture rows), `results/results.csv` (15-row category × method summary), and four comparison charts in `results/charts/`.

### 7.3 Supporting Investigations

Beyond the headline evaluation, several rigorous diagnostic studies were run:

- **NLMS un-confounded ablation** (`scripts/ablate_nlms.py`) — separated the effect of the sample-alignment fix from step-size damping. Alignment alone contributed +1.76 to +2.19 dB ΔSI-SNR; step-size damping ($\mu: 0.10 \to 0.01$) was independently necessary to reach positive enhancement, because an aggressive step size causes the filter to adapt to high-energy speech formants and distort speech.
- **Impulsive zero-lag verification** (`scripts/investigate_nlms_alignment.py`) — cross-correlation confirmed **0-sample lag, 1.0000 normalized correlation peak** on impulsive mixtures, proving NLMS's failure on transients is genuine convergence lag inherent to gradient-based adaptation, **not** a dataset alignment artifact. This is what makes the AI/ML-necessity argument defensible under scrutiny.
- **Independent SNR audit** (`scripts/audit_snr.py`) — post-hoc verification of achieved mixing SNR.
- **Native PESQ-WB build for Windows** (`scripts/build_pesq_gcc.py`) — the `pesq` C extension has no Windows wheel; it was Cythonized and compiled from source against a MinGW-w64 GCC toolchain, giving real ITU-T P.862.2 scores rather than a substitute metric.

---

## 8. Phase 5 — Real-Time Live Pipeline on Raspberry Pi 5

### 8.1 Architecture

```
USB / Loopback Audio Input (48 kHz, mono, float32)
   │
   ▼
sounddevice InputStream  ── non-blocking audio callback thread (high-priority C thread)
   │  write()  [zero allocation, zero inference in callback]
   ▼
Input RingBuffer  ── lock-free SPSC, 2.0 s / 96,000 samples, pre-allocated
   │  read()  [blocks on condition variable]
   ▼
InferenceThread  ── decoupled daemon worker
   │   ├── ENHANCE: DeepFilterNet3 (df_compat, pad=True)
   │   └── BYPASS : time-aligned pass-through
   ▼
Output RingBuffer ── 2.0 s / 96,000 samples
   │  read()
   ▼
sounddevice OutputStream ── non-blocking playback callback thread
   ▼
Headphones / Communication Unit
```

**The central design decision — and the one the plan explicitly demanded — is that model inference never runs inside the audio callback.** Callbacks only move memory (< 1 ms); all neural computation happens on a decoupled worker thread. This is what prevents audio dropouts under inference jitter.

### 8.2 Components Built

| File | Role |
|---|---|
| `live/ring_buffer.py` | Thread-safe single-producer/single-consumer circular buffer. Fixed capacity, no allocation in the hot path. Overflow drops oldest rather than ever blocking the audio callback. **6/6 self-tests pass.** |
| `live/inference_engine.py` | Stateful DeepFilterNet3 wrapper. One-time model load + 3 warm-up passes at construction to eliminate first-chunk JIT/cache jitter. Hot-path `enhance_chunk()` / `bypass_chunk()`. **6/6 self-tests pass.** |
| `live/pipeline.py` | Full streaming orchestrator: dual sounddevice streams, dual ring buffers, inference thread, per-session statistics, graceful Ctrl-C shutdown. Includes `_resolve_device()` to auto-detect valid ALSA interfaces. |
| `live/detect_devices.py` | Enumerates PortAudio devices and auto-suggests a config block for hardcoding device IDs. |
| `live/latency_test.py` | Click-impulse cross-correlation measurement of algorithmic lookahead and per-chunk wall time. |
| `live/stress_test.py` | 10-minute continuous-run gate with CPU / RAM / temperature / dropout monitoring and pass-fail verdict. |
| `live/main.py` | Unified CLI: `detect`, `pipeline`, `latency`, `stress`, `demo`. |
| `demo/dashboard.py` | Interactive ANSI TUI — live telemetry plus `b` (ENHANCE/BYPASS toggle) and `q` (graceful quit). |
| `demo/spectrogram.py` | Live before/after waterfall spectrogram, terminal-rendered (SSH-safe, no X11). |
| `config/audio_config.yaml` | Central hardware configuration: sample rate, chunk size, ring capacity, device IDs, mode, warm-up passes. |
| `scripts/deploy_to_pi.py` | Clean runtime packaging → `pi_deploy.zip` (15 files, excludes datasets/venv/git). |

### 8.3 Runtime Configuration

| Parameter | Value |
|---|---|
| Sample rate | 48,000 Hz (DeepFilterNet3 native — no resampling in the live path) |
| Channels | 1 (mono) |
| Processing chunk | 0.1 s = **4,800 samples** |
| Ring buffer capacity | 2.0 s = 96,000 samples (each direction) |
| Attenuation limit | 100 dB (full suppression) |
| Warm-up passes | 3 |
| Audio device | Index 0 — ALSA `snd-aloop` Loopback (`hw:2,0`) |

### 8.4 Verified Raspberry Pi 5 Measurements (Mode B — real hardware)

**Per-chunk processing latency & algorithmic lag** (`results/latency_pi.json`, 10 reps + 5 warm-up):

| Mode | Median lag | Median wall time | P95 | Max | Median RTF |
|---|---|---|---|---|---|
| BYPASS | **0.0 samples (0.000 ms)** | 0.00 ms | 0.01 ms | 0.01 ms | 0.0000 |
| ENHANCE | **0.0 samples (0.000 ms)** | **29.18 ms** | 29.85 ms | 29.93 ms | **0.2918** |

The 0-sample cross-correlation lag confirms DeepFilterNet3 with `pad=True` introduces **no time shift**, so ENHANCE and BYPASS audio are sample-aligned — which is exactly what makes the live A/B toggle click-free and honest.

**10-minute continuous stress test** (`results/stress_test_report.json`):

| Metric | Target | Measured | Verdict |
|---|---|---|---|
| Duration | ≥ 600 s | **600.3 s** (5,997 chunks) | ✅ PASS |
| Ring buffer overflows | 0 | **0** | ✅ PASS |
| Ring buffer underruns | 0 | **0** | ✅ PASS |
| Total audio dropouts | 0 | **0** | ✅ PASS |
| Max CPU temperature | < 80 °C | **50.1 °C** (30 °C headroom) | ✅ PASS |
| Mean / max CPU utilization | — | **17.2% / 19.1%** | ✅ PASS |
| Mean RAM usage | — | **8.0%** | ✅ PASS |
| Streaming RTF (median) | < 1.00 | **0.3784** (~2.6× real time) | ✅ PASS |
| **Overall verdict** | PASS | **PASS** | ✅ |

Per-chunk latency during the run: median 37.84 ms, p95 39.31 ms, max 63.92 ms.

**Interactive dashboard session:** 684 continuous chunks, median 37.22 ms (RTF 0.3722), p95 40.39 ms, 0 overflows, 0 underruns, clean exit. ENHANCE/BYPASS toggle verified working live.

### 8.5 Disclosed Performance Finding (Rule 33)

The original internal target was RTF < 0.25. Measured: **0.292 in-memory, 0.378 under live loopback streaming**. Both exceed 0.25 but sit far below the real-time ceiling of 1.00, leaving substantial headroom and producing zero dropouts across a 10-minute run. **This is reported exactly as measured, not re-parameterized to appear compliant.** The gap between 0.292 and 0.378 is attributable to ALSA loopback scheduling overhead; a physical USB audio interface is expected to land closer to the in-memory figure — an expectation explicitly labeled as unverified until tested.

---

## 9. Post-Phase-5 Hardening Pass

A dedicated review pass run after Phase 5 closure, which produced both quality improvements and two significant integrity findings.

### 9.1 Deliverables

| Item | Detail |
|---|---|
| **README correction** | The status section still claimed live Pi streaming was "the next integration step" despite Phase 5 being complete with real hardware evidence — it was actively hiding the project's strongest result from anyone reading the repository front page. Corrected, with Pi 5 evidence summarized and `live/`, `demo/`, `config/` added to the repository layout. |
| **`demo/spectrogram.py` (new)** | Live before/after waterfall spectrogram. 64 log-spaced frequency bins (50 Hz – 8 kHz), 14-row scrolling history, 5-level color intensity ramp. **Critically: both panels share one auto-gain reference driven by the BEFORE signal**, so when DeepFilterNet suppresses energy the AFTER panel visibly darkens — rather than independently re-normalizing and misleadingly appearing equally loud. Includes an offline `--self-test` (verified: before_mean 0.938 vs after_mean 0.037 on a synthetic noise-vs-clean pair). |
| **`live/pipeline.py` instrumentation** | Added `last_in_chunk` / `last_out_chunk` display-only attributes so demo tooling can read the most recent audio without touching the audio hot path. |
| **`scripts/run_all_selftests.py` (new)** | Unified Mode A test runner across `ring_buffer`, `inference_engine`, `run_inference`, and `spectrogram`. One command, one pass/fail summary. Deliberately excludes Mode B (Pi-hardware) tests per Rule 29. |
| **`docs/non_stationary_root_cause.md` (new)** | Subtype-level decomposition of the weakest category (see 9.2). |
| **`scripts/build_pesq_gcc.py` portability fix** | Made machine-independent (see Section 10). |
| **`pi_deploy.zip` regenerated** | Now includes the spectrogram demo. |

### 9.2 Root-Cause Analysis: the Non-Stationary Weakness

The non-stationary category fails all three DRDO targets, and the existing documentation attributed this vaguely to "helicopter/crowd noise being harder." Decomposing `results/eval_raw.csv` by subtype showed that framing was wrong:

| Method | Subtype | n | STOI | ΔSI-SNR |
|---|---|---|---|---|
| **DeepFilterNet** | **helicopter** | 60 | **0.9108** | **+8.898 dB** |
| **DeepFilterNet** | **crowd** | 40 | **0.7080** | **+1.031 dB** |
| NLMS (ref-assisted) | crowd | 40 | 0.8657 | +2.650 dB |
| Unprocessed noisy | crowd | 40 | 0.7196 | 0.000 dB |

**Findings:**
1. On **helicopter** — a genuine, sourced defence noise type — DeepFilterNet delivers **0.9108 STOI and +8.9 dB**, on par with its best categories. Helicopter is not the problem.
2. On **crowd babble**, DeepFilterNet's STOI (0.7080) is **below the unprocessed noisy baseline** (0.7196) — it measurably *reduces* intelligibility — and its ΔSI-SNR gain is the smallest of every method tested, including all three classical baselines.

**Root cause:** crowd babble is *other human speech* (synthesized by overlapping six clean utterances). Every other subtype is acoustically separable from speech by spectral shape, harmonic structure, or temporal envelope. Babble is not — it occupies the same band with the same spectral envelope and modulation statistics as the target voice. This is the classic **cocktail-party problem**: a single-channel enhancer has no cue to distinguish "the speaker we want" from "other speakers," because both are speech. It is a structural limitation of the entire class of single-channel neural enhancers, not a defect in this checkpoint, and the standard mitigations (multi-channel beamforming, or speaker-conditioned models with target enrollment) are outside the current single-channel architecture.

**Why this matters for the pitch:** it converts an unexplained metric miss into a precisely scoped, well-understood limitation — a much stronger position under expert questioning.

---

## 10. Incidents Found & Fixed (Engineering Integrity Record)

Four defects were found and corrected. Documenting them is deliberate: the ability to detect and honestly correct one's own data integrity failures is itself evidence of engineering rigor.

### 10.1 🔴 CRITICAL — Missing gunshot/artillery corpus (silent dataset corruption)

**What was wrong:** `data/noise/impulsive/` contained **only** the 40-file `explosion` (ESC-50 fireworks proxy) subtype. The `gunshot` (2,148 files) and `artillery` (30 files) corpora were entirely absent. Every "impulsive" result in Phases 3 and 4 — reported throughout the documentation as **"Impulsive (Gunshot/Artillery)"** — had actually been computed on **explosion-only proxy noise**.

**Root cause:** the ~1.5 GB Zenodo download was failing under the original non-resumable downloader (`urllib.request.urlretrieve`, no retry/resume). A commit (`feb019c`) correctly fixed the downloader **but regenerated and committed the manifest before the download had actually completed** — silently collapsing all 100 impulsive mixtures onto the one surviving subtype. Verified via `git show feb019c~1:data/manifest.csv`: the pre-commit manifest correctly held `artillery: 34, explosion: 40, gunshot: 26`; post-commit it was `explosion: 100`.

**Why it went unnoticed:** `data/mix_dataset.py` printed a soft `[WARNING]` for empty noise subtypes and then proceeded normally. No error, no failed assertion, and the manifest-parity check still passed (300 rows == 300 files) because the count was right — only the *composition* was wrong.

**Recovery:** automated re-download returned `403 Forbidden` from Zenodo ("unusual traffic from your network") — a network-level anti-bot block, not a code defect, confirmed by a standalone HEAD request. The archive was obtained manually via browser, verified byte-complete (1,567,979,135 bytes, `zipfile.testzip()` clean), and found to contain exactly **2,148 files across 4 firearm-type folders** — matching the documented gunshot count precisely. The full pipeline was regenerated end to end: manifest → mixtures → 3 baselines → DeepFilterNet → 1,500-pair evaluation.

**Outcome — the correction strengthened the results:**

| Metric | Before (explosion-only, wrong) | After (real gunshot/artillery) | Change |
|---|---|---|---|
| Impulsive PESQ-WB | 2.4916 (**FAIL**) | **2.5841 (PASS)** | ✅ FAIL → PASS |
| Impulsive STOI | 0.9196 | **0.9319** | ↑ |
| Impulsive SI-SNR | +15.20 dB | **+15.75 dB** | ↑ |
| NLMS impulsive ΔSI-SNR | −3.30 dB | **−7.10 dB** | Collapse is sharper on real transients — strengthens the AI/ML argument |

Stationary and non-stationary numbers were unaffected and verified byte-identical, confirming the fault was isolated to the impulsive corpus.

**Preventive fix:** `data/mix_dataset.py` now raises a hard `RuntimeError` naming the missing subtypes if any declared noise subtype has zero files (override with `--allow-partial-corpus`). `scripts/download_datasets.py` gained a `setup_gunshot()` function with an explicit manual-download fallback message. Full writeups in `docs/phase_4_summary.md`, `data/SOURCES.md` §5, and `results/final/target_compliance.md`.

### 10.2 🟠 PESQ-WB C extension missing / build script non-portable

`results/eval_raw.csv` and `results/results.csv` had been regenerated without valid PESQ-WB data (all 1,500 rows reading *"Unavailable: C++ Build Tools required"*). Root cause: `scripts/build_pesq_gcc.py` hardcoded a GCC path under a **different Windows user profile** (`C:\Users\Admin\...`) and a **Python 3.9 ABI tag** (`cypesq.cp39-win_amd64.pyd`) — both specific to whatever machine originally built it; additionally `pesq` was never added to `pyproject.toml`, so it lived outside the lockfile and did not survive environment changes.

**Fix:** rewrote the script to discover `gcc` dynamically (PATH → WinGet → Chocolatey → MSYS2) and derive the correct ABI tag at build time from `sysconfig.get_config_var("EXT_SUFFIX")`. Installed a MinGW-w64 toolchain, rebuilt successfully for Python 3.11, verified with a real PESQ computation, then confirmed via a full 1,500-pair re-run showing **"100/100 Valid"** on every category. No committed data had been lost — the verified category-level means were safely preserved in the git-tracked `results/final/target_compliance.json`.

### 10.3 🟡 Stale self-test fixture + duplicate-glob bug

`run_inference.py::run_self_test()` depended on `data/mixtures/noisy.wav`, a Phase-1 leftover; that directory now holds the 300-mixture dataset. The self-test therefore either failed outright, or — via `batch_inference()`'s directory glob — would have silently reprocessed the entire 600-file dataset instead of running a fast smoke check. Separately, `batch_inference()` combined a non-recursive **and** a recursive glob pattern, double-matching every top-level file.

**Fix:** the self-test now generates its own synthetic 2 s clip and calls `process_file()` directly; the duplicate glob was removed. Verified passing (RTF 0.2455). The production path (`process_manifest()`, manifest-driven) was never affected. **This bug was found by the newly-built unified self-test runner** — the tooling justified itself immediately.

### 10.4 🟡 Reporting overstatement (found earlier, 2026-08-23)

`docs/phase_4_summary.md` originally claimed the DRDO PESQ > 2.5 benchmark was met, citing values of 2.48–2.49 — which are *below* 2.5 — and supported an overall claim using only a favorable SNR-conditional slice. Corrected with a dated note preserving the original text, plus two terminology corrections: NLMS relabeled a **reference-assisted** baseline (not comparable to single-channel methods), and "ANC" clarified as **noise suppression / speech enhancement** (retained only where mirroring PS26052's own language).

---

## 11. Final Results & DRDO Target Compliance

### 11.1 Complete Category × Method Matrix

*1,500 condition-mixture pairs, 100% valid, 0 exclusions. Regenerated 2026-08-24 on the corrected dataset with real ITU-T P.862.2 PESQ-WB.*

| Category | Method | n | PESQ-WB | STOI | SI-SNR (dB) | ΔSI-SNR (dB) |
|---|---|---|---|---|---|---|
| **Stationary** (engine/vehicle) | Unprocessed Noisy | 100 | 1.3801 | 0.8198 | +5.04 | 0.00 |
| | Spectral Subtraction | 100 | 1.4185 | 0.8225 | +6.29 | +1.25 |
| | Wiener Filter | 100 | 1.4889 | 0.8329 | +8.27 | +3.23 |
| | NLMS *(ref-assisted)* | 100 | 1.4480 | 0.9010 | +9.01 | +3.97 |
| | **DeepFilterNet** | 100 | **2.4823** | **0.9169** | **+16.14** | **+11.10** |
| **Non-Stationary** (helicopter/crowd) | Unprocessed Noisy | 100 | 1.4047 | 0.7846 | +5.00 | 0.00 |
| | Spectral Subtraction | 100 | 1.4295 | 0.7862 | +5.76 | +0.76 |
| | Wiener Filter | 100 | 1.4519 | 0.7905 | +6.76 | +1.76 |
| | NLMS *(ref-assisted)* | 100 | 1.3990 | 0.8796 | +7.85 | +2.86 |
| | **DeepFilterNet** | 100 | **2.1303** | **0.8297** | **+10.75** | **+5.75** |
| **Impulsive** (gunshot/artillery) | Unprocessed Noisy | 100 | 1.6638 | 0.8584 | +5.00 | 0.00 |
| | Spectral Subtraction | 100 | 1.6916 | 0.8591 | +5.12 | +0.12 |
| | Wiener Filter | 100 | 1.6343 | 0.8593 | +5.26 | +0.27 |
| | NLMS *(ref-assisted)* | 100 | 1.3085 | 0.8183 | −2.10 | **−7.10** |
| | **DeepFilterNet** | 100 | **2.5841** | **0.9319** | **+15.75** | **+10.75** |

### 11.2 DRDO Target Compliance Matrix

*Targets: SI-SNR > 15 dB · STOI > 0.85 · PESQ-WB > 2.5*

| Category | SI-SNR | STOI | PESQ-WB | Overall |
|---|---|---|---|---|
| **Stationary** | 16.14 dB ✅ | 0.9169 ✅ | 2.4823 ❌ (−0.018) | **2 of 3** |
| **Non-Stationary** | 10.75 dB ❌ (−4.25) | 0.8297 ❌ (−0.020) | 2.1303 ❌ (−0.370) | **0 of 3** |
| **Impulsive** | 15.75 dB ✅ | 0.9319 ✅ | **2.5841 ✅ (+0.084)** | **3 of 3** ⭐ |

**Impulsive noise — the hardest and most defence-critical category — passes every DRDO target.**

### 11.3 Supplementary: PESQ-WB by Input SNR (DeepFilterNet)

*Conditional slices for analysis, explicitly not substituted for the compliance verdict.*

| Input SNR | Stationary | Non-Stationary | Impulsive |
|---|---|---|---|
| −5 dB | 1.71 | 1.41 | 1.87 |
| 0 dB | 2.09 | 1.74 | 2.44 |
| +5 dB | 2.58 | 2.24 | 2.72 |
| +10 dB | 2.86 (80% > 2.5) | 2.53 (55%) | 2.94 (85%) |
| +15 dB | 3.17 (100% > 2.5) | 2.73 (80%) | 2.95 (75%) |

At realistic operating SNRs (≥ +10 dB), the majority of individual mixtures clear PESQ 2.5 in every category — and **100% of stationary mixtures at +15 dB**.

### 11.4 The Two Findings That Drive the Design Argument

1. **Classical adaptive filtering fails structurally on impulsive defence noise.** NLMS — despite being given an *oracle* second-channel noise reference that no deployed single-mic system would have — **degrades** the signal by 7.10 dB ΔSI-SNR on real gunshot/artillery transients. Verified by zero-lag cross-correlation ablation to be inherent convergence lag, not an alignment artifact.
2. **Deep learning closes the gap decisively.** On the identical audio, DeepFilterNet delivers **+10.75 dB ΔSI-SNR and 2.58 PESQ-WB** using only a single channel — an ~18 dB swing versus the oracle-assisted classical method. This is the quantitative core of the case for AI/ML in defence communications.

---

## 12. Complete Repository Inventory

```
defence_anc/
├── data/
│   ├── clean/                    150 LibriSpeech utterances (48 kHz)
│   ├── noise/
│   │   ├── stationary/{engine,vehicle}/          40 + 40 files
│   │   ├── non_stationary/{helicopter,crowd}/    40 + 20 files
│   │   └── impulsive/{gunshot,explosion,artillery}/  2148 + 40 + 30 files
│   ├── mixtures/                 600 files (300 mixtures + 300 clean refs)
│   ├── mix_dataset.py            Seeded generator, hard-fails on partial corpus
│   ├── manifest.csv              300 rows, 12 fields
│   └── SOURCES.md                Full provenance, licenses, §5 recovery record
├── baselines/
│   ├── spectral_subtraction/     Berouti/Boll over-subtraction
│   ├── wiener/                   Decision-directed a priori SNR
│   └── nlms/                     Numba-JIT, manifest-traced oracle reference
├── models/deepfilternet/
│   ├── df_compat.py              Cross-platform I/O polyfill (the portability keystone)
│   ├── run_inference.py          Manifest-driven batch inference + self-test
│   └── benchmark_rtf.py          20-run RTF protocol with thermal logging
├── eval/
│   ├── metrics.py                PESQ-WB / STOI / SI-SNR / ΔSI-SNR
│   └── run_eval.py               1500-pair evaluation + chart generation
├── live/                         ── RASPBERRY PI RUNTIME ──
│   ├── ring_buffer.py            Lock-free SPSC circular buffer (6/6 tests)
│   ├── inference_engine.py       Stateful DFN3 wrapper (6/6 tests)
│   ├── pipeline.py               Streaming orchestrator
│   ├── detect_devices.py         PortAudio enumeration + config suggestion
│   ├── latency_test.py           Click cross-correlation measurement
│   ├── stress_test.py            10-minute stability gate
│   └── main.py                   Unified CLI
├── demo/
│   ├── dashboard.py              ANSI TUI, ENHANCE/BYPASS toggle
│   └── spectrogram.py            Live before/after waterfall
├── config/audio_config.yaml      Hardware configuration
├── scripts/                      Downloads, orchestration, ablations, audits, packaging
├── results/
│   ├── eval_raw.csv              1500 per-mixture rows
│   ├── results.csv               15-row summary
│   ├── baselines/{4 methods}/    1200 enhanced wav files
│   ├── charts/                   4 comparison charts
│   ├── final/target_compliance.{md,json}   Authoritative compliance matrix
│   ├── rtf_pi.json               Pi 5 RTF benchmark
│   ├── latency_pi.json           Pi 5 latency measurement
│   └── stress_test_report.json   10-minute gate result
├── docs/                         Phase summaries 0-1, 2, 3, 4, 5 + root-cause analysis
├── summary/                      This record + forward plan
├── progress.md                   Append-only execution log with command evidence
├── rules.md                      Engineering discipline rules
├── architecture.md               Living architecture + dated decisions log
└── pi_deploy.zip                 Clean 15-file Pi runtime bundle
```

---

## 13. Verification Status — What Is Proven vs What Is Not

This section exists so that no claim in this project is ever overstated in front of evaluators. **Knowing precisely where the evidence stops is as important as the evidence itself.**

### ✅ Proven on real Raspberry Pi 5 hardware

- DeepFilterNet3 inference runs correctly on ARM64 Debian — RTF 0.17037 (4-thread, 3 s file)
- Live streaming pipeline runs continuously for 600.3 s with **0 buffer overflows and 0 underruns**
- Thermal behavior is safe — max 50.1 °C against an 80 °C throttle threshold, ~19% peak CPU
- Per-chunk inference latency 29.18 ms median (RTF 0.2918) in-memory; 37.84 ms median (RTF 0.3784) under live streaming load
- DeepFilterNet3 introduces **0-sample algorithmic lag** (`pad=True`), so ENHANCE/BYPASS are sample-aligned
- ENHANCE ⇄ BYPASS runtime toggle works without dropouts or stream interruption
- ANSI TUI dashboard renders correctly over SSH and exits cleanly

### ✅ Proven on the development machine

- Full 300-mixture dataset generation with 0.0000 dB SNR deviation and verified manifest parity
- All three DSP baselines across 900 files with 100% sanity-check pass rate
- 1,500-pair evaluation with real ITU-T P.862.2 PESQ-WB, 0 exclusions
- All Mode A self-tests green (`scripts/run_all_selftests.py`)

### ⚠️ NOT yet proven — explicit gaps

| Gap | Detail | Consequence |
|---|---|---|
| **No physical microphone has ever been used** | All live validation used the ALSA `snd-aloop` **virtual loopback** device (`hw:2,0`), configured as both input and output. No USB microphone, no headset, no acoustic path. | The system has never processed real captured speech in real time. PS26052 explicitly requires microphone + headset integration. **Highest-priority gap.** |
| **True end-to-end latency has never been measured** | `live/latency_test.py`'s own docstring states it "does NOT require physical audio hardware (it operates on in-memory audio arrays, not a sounddevice stream)" — it is a **Mode A** test. The reported 29.18 ms is *model inference wall time per chunk*, **not** mouth-to-ear latency. | The end-to-end figure PS26052 cares about is unknown. Static analysis of `pipeline.py` suggests roughly **~530 ms** (100 ms input block + 300 ms output priming + 100 ms output block + ~30 ms inference) — which would be well above the ITU-T G.114 comfort threshold for interactive voice. **Must be measured and reduced.** |
| **The 10-minute stress test processed loopback content, not live speech** | The pipeline read from `snd-aloop` with nothing feeding its playback side. The test rigorously validates *stability, thermals, buffer management, and CPU load* (DeepFilterNet runs identically regardless of input content) but does **not** validate enhancement quality on real acoustic input. | Stability claims are sound; "10 minutes of live noise cancellation" would be an overstatement. |
| **Latency test used 10 repetitions, not 20** | The project plan specified 20 repetitions with a reported median. | Minor methodological shortfall; trivially fixed. |
| **`demo/spectrogram.py` untested on Pi** | Only the offline `--self-test` (synthetic audio) has run. Never executed against Pi hardware. | Demo risk — must be smoke-tested before it is relied upon live. |
| **No fine-tuning / training framework** | Pretrained checkpoint only. | PS26052 deliverable #3 unmet; non-stationary category fails all targets. |
| **No model optimization** | No quantization, pruning, ONNX, or TensorRT conversion. | PS26052 explicitly lists these; they are also the most direct route to lower latency. |
| **No dual-microphone (primary + reference)** | Single-channel only. NLMS's reference channel is an offline oracle, not live hardware. | PS26052 explicitly specifies "microphones (primary + reference)". |
| **No data augmentation** | No RIR/reverberation, no clipping augmentation. | PS26052 explicitly lists these; already flagged in `data/SOURCES.md` §4. |

Every one of these gaps has a concrete, prioritized remediation plan in **`summary/02_NEXT_STEPS_PLAN.md`**.

---

*Compiled 2026-08-24. All figures traceable to `results/eval_raw.csv`, `results/final/target_compliance.json`, `results/rtf_pi.json`, `results/latency_pi.json`, `results/stress_test_report.json`, and the command-evidence log in `progress.md`.*
