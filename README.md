# PS26052 AI/ML Adaptive Noise Cancellation (ANC)

Smart India Hackathon 2026 — DRDO Problem Statement 26052.

Real-time AI/ML Adaptive Noise Cancellation for defence communications: suppressing stationary engine/vehicle hum, non-stationary helicopter rotor/crowd noise, and impulsive gunshot/artillery transients while preserving speech intelligibility — targeting the Raspberry Pi 5 as the edge deployment platform.

## Results (Phase 4 — final evaluation, 1500/1500 conditions valid)

300 synthetic 48 kHz mixtures (3 noise categories × 5 SNR levels × 20 seeds), scored with PESQ-WB / STOI / SI-SNR across 5 processing conditions. Headline numbers per category:

| Category | Method | PESQ-WB | STOI | ΔSI-SNR |
|---|---|---|---|---|
| Stationary | Classical best (NLMS aligned) | 1.45 | **0.901** | +3.97 dB |
| Stationary | **DeepFilterNet** | **2.48** | **0.917** | **+11.10 dB** |
| Non-stationary | Classical best (NLMS aligned) | 1.40 | **0.880** | +2.86 dB |
| Non-stationary | **DeepFilterNet** | **2.13** | 0.830 | **+5.75 dB** |
| Impulsive | Classical best (Wiener) | 1.53 | 0.834 | +0.47 dB |
| Impulsive | **DeepFilterNet** | **2.49** | **0.920** | **+10.19 dB** |

Key finding: gradient-based adaptive filters (NLMS) *degrade* on impulsive defence noise (−3.30 dB ΔSI-SNR) due to convergence lag on acoustic transients — a zero-lag cross-correlation ablation proved this is structural, not a pipeline bug — while DeepFilterNet maintains +10 dB improvement. This is the core argument for AI/ML on defence-critical speech.

DRDO benchmark alignment at high SNR: PESQ-WB up to 2.92 (target > 2.5), STOI > 0.91.

Full tables: [docs/phase_4_summary.md](docs/phase_4_summary.md). Charts: `results/charts/`.

## Setup

Requires Python >= 3.9, < 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Stack: PyTorch 2.5.1 + torchaudio (resampling), DeepFilterNet 0.5.6 (DFN3 @ 48 kHz native), numba (JIT NLMS kernel), scipy, soundfile, pystoi, pesq (native build via [scripts/build_pesq_gcc.py](scripts/build_pesq_gcc.py) on Windows/GCC systems), matplotlib/seaborn.

## End-to-end reproduction

Run from the repository root. Every step is seeded and idempotent (re-runs skip completed work).

```bash
# 1. Acquire raw corpora (LibriSpeech dev-clean speech + ESC-50 noise subsets)
uv run python scripts/download_datasets.py
uv run python scripts/generate_babble_noise.py

# 2. Synthesize the 300-mixture evaluation dataset -> data/mixtures/ + data/manifest.csv
uv run python data/mix_dataset.py

# 3. Classical DSP baselines (or all three at once: scripts/run_all_baselines.py)
uv run python baselines/nlms/nlms.py
uv run python baselines/spectral_subtraction/spectral_subtraction.py
uv run python baselines/wiener/wiener.py

# 4. DeepFilterNet inference
uv run python models/deepfilternet/run_inference.py

# 5. Evaluate all conditions -> results/results.csv + results/charts/
uv run python eval/run_eval.py
```

Optional checks along the way:

```bash
uv run python scripts/run_pilot_benchmarks.py   # 10-file pilot timing + 300-file extrapolation
uv run python scripts/audit_snr.py              # independent post-hoc SNR audit of mixtures
uv run python scripts/check_env_metrics.py      # verify metric library availability
```

## Dataset

Mixtures combine LibriSpeech dev-clean utterances with defence-relevant noise subtypes (engine idle, vehicle, helicopter rotor, crowd babble, gunshot, artillery, explosion) at −5/+0/+5/+10/+15 dB SNR. Provenance, licensing, and acquisition route for every noise source are documented in [data/SOURCES.md](data/SOURCES.md); the exact generation recipe (per-mixture seeds, SNRs, normalization factors) is in [data/manifest.csv](data/manifest.csv), so the dataset is bit-for-bit regenerable without shipping audio.

## Repository layout

```
data/                  mixture generator, manifest, provenance docs (audio itself is gitignored)
baselines/nlms/        numba-JIT NLMS adaptive filter
baselines/spectral_subtraction/   Berouti/Boll spectral subtraction
baselines/wiener/      decision-directed Wiener filter
models/deepfilternet/  DFN3 batch inference (manifest-driven)
eval/                  PESQ-WB / STOI / SI-SNR engine + batch evaluator
scripts/               dataset download, orchestration, pilots, audits, diagnostics
results/charts/        category × method comparison charts
```

## Documentation

- [architecture.md](architecture.md) — component matrix, data flow, decisions log
- [rules.md](rules.md) — engineering discipline rules governing the pipeline
- [progress.md](progress.md) — append-only execution log with command evidence
- [docs/](docs/) — per-phase summary reports (Phases 0–4)
- [AUDIT_REPORT.md](AUDIT_REPORT.md) — full repository audit (27 findings, severity-ranked, with remediation order)

## Roadmap

Phase 5 targets live streaming on the Pi 5 (`sounddevice` real-time loop) — not yet implemented; see architecture.md future TODOs.
