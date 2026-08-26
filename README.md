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
| Impulsive (gunshot/artillery) | +0.27 dB ΔSI-SNR · 0.86 STOI | **+10.75 dB ΔSI-SNR · 0.93 STOI · 2.58 PESQ-WB** |

Two findings drive the design argument:

- **Adaptive filters fail structurally on impulsive noise.** NLMS *loses* 7.1 dB of SI-SNR on real gunshot/artillery transients (Zenodo Record 7004819, CC BY 4.0) due to convergence lag — verified by zero-lag cross-correlation ablation to be inherent to gradient-based adaptation, not an alignment artifact.
- **Deep learning closes the gap.** DeepFilterNet maintains +10–11 dB improvement where classical methods collapse or stall. On impulsive noise it clears all three DRDO targets (SI-SNR > 15 dB, STOI > 0.85, **PESQ-WB > 2.5**) on the full SNR-averaged evaluation, not just at high input SNR.

Non-stationary is the one open gap, and it's narrower than the category number suggests: it's driven almost entirely by crowd/babble (other human speech — a single-channel enhancer structurally can't separate target speech from background speech, the cocktail-party problem), while helicopter alone scores STOI 0.91 / +8.9 dB ΔSI-SNR, on par with the strongest categories. See [docs/non_stationary_root_cause.md](docs/non_stationary_root_cause.md) for the subtype-level breakdown.

Full per-method tables live in [docs/phase_4_summary.md](docs/phase_4_summary.md) and [results/final/target_compliance.md](results/final/target_compliance.md); charts in `results/charts/`.

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

### Processing your own audio (no dataset needed)

`models/deepfilternet/run_inference.py --input-dir` enhances any `.wav`/`.flac` file(s) you point it at directly — file in, enhanced file out, no manifest or dataset setup required. Works the same on the dev machine or the Pi.

```bash
mkdir my_audio                         # put your noisy recording(s) in here
uv run python models/deepfilternet/run_inference.py --input-dir my_audio --output-dir my_audio/enhanced
```

Output lands at `my_audio/enhanced/<name>_DeepFilterNet3.wav`. The input just needs speech and noise already mixed into one file (record it that way, or mix separate tracks in an editor first).

To generate an illustrative before/after clip from the project's own noise corpus (clean speech + engine + a gunshot burst, mixed at a controlled SNR) instead of supplying your own audio:

```bash
uv run python scripts/make_demo_clip.py --output results/demo_audio/before_demo.wav --snr -5
uv run python models/deepfilternet/run_inference.py --input-dir results/demo_audio --output-dir results/demo_audio/enhanced
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
live/                  real-time pipeline: ring buffer, inference engine, streaming orchestrator, latency/stress tests
demo/                  terminal dashboard + live spectrogram for the judged demo
config/                audio_config.yaml — hardware device IDs, chunk size, pipeline mode
requirements.txt          Pi core deps — must always install cleanly (the live pipeline's demo path)
requirements-optional.txt Pi optional deps (residual filter, ONNX backend, scipy) — never blocks the core install
```

## Project documentation

- [architecture.md](architecture.md) — component matrix, data flow diagrams, decisions log
- [rules.md](rules.md) — engineering discipline rules governing the pipeline
- [progress.md](progress.md) — append-only execution log with command evidence
- [docs/](docs/) — chronological execution reports per development milestone

## Status

All phases complete (0–5). The offline batch pipeline (dataset, DSP baselines, DeepFilterNet, evaluation) is fully evaluated, and the real-time live pipeline is physically verified on Raspberry Pi 5 hardware:

- **Live streaming**: `sounddevice` capture → ring buffer → DeepFilterNet3 → ring buffer → playback, running on-device (`live/pipeline.py`).
- **Per-chunk model inference time** (Pi 5, in-memory, isolated call, 10 reps): 29.18 ms median (RTF 0.29), 0-sample cross-correlation lookahead. This is inference only — not a round-trip or end-to-end figure.
- **Device I/O round-trip** (Pi 5, real `sounddevice`/PortAudio/ALSA, 20 reps, `snd-aloop` loopback): 42.67 ms round-trip. Combined with inference and 100 ms priming ≈ **172 ms full-pipeline estimate**, chunk size 100 ms. This specific click-based round-trip figure is still loopback-measured — the click-and-cross-correlate method it uses can't run against physically separate mic/headset hardware, only a wired-back loopback.
- **Physical microphone + headset are now integrated and validated** (2026-08-26): a USB mic + headset (via a Generalplus USB audio adapter) replaced the `snd-aloop` loopback for all live-pipeline testing. Under real acoustic input, per-chunk inference time in the streaming loop measured **38.96 ms median / 40.44 ms p95** (600.5 s run, 6001 chunks) — higher than the 29.18 ms isolated figure above because it includes real thread-scheduling overhead under continuous audio I/O, not because of any hardware slowdown.
- **10-minute stress test, real microphone + headset** (Pi 5, 100 ms chunk size, 2026-08-26): 600.5 s continuous run in ENHANCE mode, **0 dropouts across 6001 chunks, 0 inference errors**, max CPU temp 40.2 °C, mean CPU load 17.9 %, RTF median 0.3896 / p95 0.4044. Supersedes the earlier loopback-based stress result (600.5 s, 0 dropouts, max 52.9 °C, RTF median 0.3823) as the current stability evidence — both are real Pi 5 measurements, just against different signal sources. Note: this run's headset was later found to have a defective mic (see below), so this figure should be read as *data-flow/stability* evidence (buffer health, thermals, CPU), not as confirmation of real acoustic content.
- **Demo tooling**: terminal dashboard (`demo/dashboard.py`) and live before/after spectrogram (`demo/spectrogram.py`), both with ENHANCE/BYPASS toggle. **Mic-verified as of 2026-08-26 evening**: the headset used in earlier same-day testing was found to have a physically defective mic (isolated via gain sweeps, a direct tap test, and cross-testing on a laptop — all pointed at the headset, not the Pi/adapter/software). After swapping headsets, `demo/spectrogram.py` was re-run against confirmed real speech (clean recording, no clipping) and shows the expected BEFORE (dense broadband energy) vs. AFTER (energy collapsed to the speech band) divergence live, with 0 dropouts / 0 inference errors. Offline batch enhancement of arbitrary audio files (`run_inference.py --input-dir`, see above) also verified on the Pi, including as a same-Pi record→enhance→playback fallback for demo scenarios without a live full-duplex mic path.

Post-Phase-5 additions, all off by default / non-invasive to the demo path unless explicitly enabled:
- **Data augmentation** (`data/augment.py`, `mix_dataset.py --augment-rir/--augment-clipping`): synthetic room-reverb + mic-overload clipping for a robustness-focused evaluation set, alongside the clean-condition baseline.
- **Residual noise-suppression stage** (`live/residual_filter.py`, `pipeline.residual_filter: true`): reference-free adaptive filter after DeepFilterNet. Mechanically verified stable on the Pi (10-min stress, 0 dropouts); audio-quality impact not yet validated against the eval set, hence off by default.
- **ONNX Runtime inference backend** (`models/deepfilternet/export_onnx.py`, `pipeline.inference_backend: onnx`): verified bit-exact vs PyTorch and ~42% faster on an x86_64 dev machine. **Not usable on this Pi's Python 3.13** — `onnx`'s `ml_dtypes` dependency requires `numpy≥2.1` there, which conflicts with `deepfilternet`'s `numpy<2.0` requirement; a hard upstream constraint, not a config issue. Optional dependencies for both of the above live in `requirements-optional.txt`, kept separate from `requirements.txt` so the core live pipeline's install can never be blocked by an optional feature.

Full Pi 5 evidence: [docs/phase_5_summary.md](docs/phase_5_summary.md). Known gap: PESQ-WB misses the >2.5 DRDO target on stationary (2.48) and non-stationary (2.13) noise on the full SNR-averaged evaluation — impulsive now passes (2.58) with the corrected gunshot/artillery dataset; see [results/final/target_compliance.md](results/final/target_compliance.md) for the full compliance matrix.
