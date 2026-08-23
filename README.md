# AI/ML Adaptive Noise Cancellation for Defence Communications

Smart India Hackathon 2026 — DRDO Problem Statement 26052 (PS26052).

A single-channel speech enhancement system that suppresses defence-relevant acoustic noise — stationary engine/vehicle hum, non-stationary helicopter rotor and crowd noise, and impulsive gunshot/artillery transients — while preserving speech intelligibility. Designed for real-time operation on a Raspberry Pi 5 edge target, combining classical adaptive DSP baselines with a state-of-the-art deep learning enhancer (DeepFilterNet3) under one reproducible evaluation harness.

## How it works

The system processes 48 kHz mono audio through five comparable conditions:

1. **Unprocessed noisy** — baseline reference for improvement deltas
2. **NLMS adaptive filter** — numba-JIT Widrow/Haykin kernel, manifest-aligned reference channel
3. **Spectral subtraction** — Berouti/Boll over-subtraction with minimum-statistics noise floor
4. **Decision-directed Wiener filter** — Ephraim & Malah a priori SNR tracking
5. **DeepFilterNet** — pretrained DFN3, multi-stage ERB-scale deep filtering at native 48 kHz

Every stage is driven by a single seeded manifest (`data/manifest.csv`), making the entire pipeline deterministic and bit-for-bit regenerable.

## Results

Evaluated on 300 synthetic mixtures (3 noise categories × 5 SNR levels from −5 to +15 dB × 20 seeds): 1500 condition–mixture pairs scored with PESQ-WB, STOI, SI-SNR, and ΔSI-SNR vs the noisy input. All 1500 evaluations valid, zero exclusions.

| Noise category | Best classical | DeepFilterNet |
|---|---|---|
| Stationary (engine/vehicle) | +3.97 dB ΔSI-SNR · 0.90 STOI | **+11.10 dB ΔSI-SNR · 0.92 STOI · 2.48 PESQ-WB** |
| Non-stationary (helicopter/crowd) | +2.86 dB ΔSI-SNR · 0.88 STOI | **+5.75 dB ΔSI-SNR · 0.83 STOI · 2.13 PESQ-WB** |
| Impulsive (gunshot/artillery) | +0.47 dB ΔSI-SNR · 0.83 STOI | **+10.19 dB ΔSI-SNR · 0.92 STOI · 2.49 PESQ-WB** |

Two findings drive the design argument:

- **Adaptive filters fail structurally on impulsive noise.** NLMS loses 3.3 dB of SI-SNR on gunshot/artillery transients due to convergence lag — verified by zero-lag cross-correlation ablation to be inherent to gradient-based adaptation, not an alignment artifact.
- **Deep learning closes the gap.** DeepFilterNet maintains ~10 dB improvement where classical methods collapse, reaching up to 2.92 PESQ-WB at high SNR (DRDO benchmark: > 2.5) and > 91% STOI.

Full per-method tables live in [docs/phase_4_summary.md](docs/phase_4_summary.md); charts in `results/charts/`.

## Getting started

Requirements: Python ≥ 3.9, < 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Main dependencies: PyTorch 2.5.1 + torchaudio, DeepFilterNet 0.5.6, numba, scipy, soundfile, pystoi, pesq (native build helper included), matplotlib/seaborn.

### Running the full pipeline

From the repository root. Each step is seeded and idempotent — re-runs skip completed work.

```bash
# 1. Acquire raw corpora (LibriSpeech dev-clean speech + ESC-50 noise subsets)
uv run python scripts/download_datasets.py
uv run python scripts/generate_babble_noise.py

# 2. Synthesize the 300-mixture dataset -> data/mixtures/ + data/manifest.csv
uv run python data/mix_dataset.py

# 3. Classical DSP baselines (or all three at once via scripts/run_all_baselines.py)
uv run python baselines/nlms/nlms.py
uv run python baselines/spectral_subtraction/spectral_subtraction.py
uv run python baselines/wiener/wiener.py

# 4. DeepFilterNet inference
uv run python models/deepfilternet/run_inference.py

# 5. Score everything -> results/results.csv + results/charts/
uv run python eval/run_eval.py
```

Utility checks along the way:

```bash
uv run python scripts/run_pilot_benchmarks.py   # pilot timing + full-run extrapolation
uv run python scripts/audit_snr.py              # independent post-hoc SNR audit
uv run python scripts/check_env_metrics.py      # metric library availability check
```

## Dataset

Clean speech comes from LibriSpeech dev-clean; noise subtypes (engine idle, vehicle, helicopter rotor, crowd babble, gunshot, artillery, explosion) are sourced and license-audited in [data/SOURCES.md](data/SOURCES.md). Mixtures are generated at controlled SNRs with per-mixture seeds recorded alongside achieved SNRs and normalization factors in [data/manifest.csv](data/manifest.csv). Audio files themselves are not stored in git — the manifest regenerates the exact dataset anywhere.

## Repository layout

```
data/                  mixture generator, manifest, provenance docs
baselines/nlms/        numba-JIT NLMS adaptive filter
baselines/spectral_subtraction/   spectral subtraction (Berouti/Boll)
baselines/wiener/      decision-directed Wiener filter
models/deepfilternet/  DFN3 manifest-driven batch inference
eval/                  PESQ-WB / STOI / SI-SNR engine + batch evaluator
scripts/               downloads, orchestration, pilots, audits, diagnostics
results/charts/        category × method comparison charts
```

## Project documentation

- [architecture.md](architecture.md) — component matrix, data flow diagrams, decisions log
- [rules.md](rules.md) — engineering discipline rules governing the pipeline
- [progress.md](progress.md) — append-only execution log with command evidence
- [docs/](docs/) — chronological execution reports per development milestone

## Status

Offline batch pipeline is complete and fully evaluated. Live real-time streaming on the Pi 5 (`sounddevice` capture → enhance → playback loop) is the next integration step — see architecture.md future TODOs.
