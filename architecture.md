# Architecture — PS26052 AI/ML Adaptive Noise Cancellation (ANC)

## Current Folder Structure
```
PS26052/
├── .gitignore
├── README.md
├── architecture.md
├── progress.md
├── rules.md
├── pyproject.toml
├── baselines/
│   ├── nlms/
│   ├── spectral_subtraction/
│   └── wiener/
├── config/
│   └── audio_config.yaml
├── data/
│   ├── SOURCES.md
│   ├── manifest.csv
│   ├── mix_dataset.py
│   ├── clean/
│   ├── mixtures/
│   └── noise/
│       ├── impulsive/
│       │   ├── artillery/
│       │   ├── explosion/
│       │   └── gunshot/
│       ├── non_stationary/
│       │   ├── crowd/
│       │   └── helicopter/
│       └── stationary/
│           ├── engine/
│           └── vehicle/
├── demo/
│   ├── dashboard.py
│   ├── spectrogram.py
│   └── webdash/               (Phase 4 WOW #2)
│       ├── app.py             FastAPI + WebSocket telemetry server
│       ├── generate_qr.py     QR code for LAN URL
│       └── static/
│           └── index.html     Single-page web client
├── docs/
├── eval/
├── live/
│   ├── ring_buffer.py
│   ├── inference_engine.py
│   ├── pipeline.py
│   ├── latency_test.py
│   ├── e2e_latency_test.py
│   ├── calibrate_mic_pair.py
│   ├── reference_nlms.py
│   ├── latency_budget.py
│   ├── cpu_affinity.py
│   ├── fast_resample.py
│   └── acoustic_latency_test.py
├── models/
│   ├── deepfilternet/
│   ├── dnsmos/                (Phase 4 WOW #3)
│   │   ├── SOURCES.md         Model origin, version, licence (Rule 12)
│   │   ├── download_model.py  Fetch sig_bak_ovr.onnx from DNS Challenge
│   │   └── dnsmos_infer.py    Inference thread + self-test
│   └── noise_classifier/      (Phase 4 WOW #1)
│       ├── model.py           Small PyTorch log-mel CNN
│       ├── train.py           Grouped-split training (grouped by noise_id)
│       ├── classify_chunk.py  Inference + UNCERTAIN state + self-test
│       └── impulsive_log.py   JSONL timestamped impulsive-event log
├── results/
└── scripts/
```

## System Data Flow Diagram
```mermaid
graph LR
    Mic["Microphone / Audio Input"] --> RingBuf["Input Ring Buffer"]
    RingBuf --> DFN["DeepFilterNet Engine"]
    DFN --> OutBuf["Output Ring Buffer"]
    OutBuf --> Headphone["Headphones / Speaker Output"]
```

## Component Table
| Component Name | Purpose | Library / Tech Stack | Runs On / Performance |
|---|---|---|---|
| DeepFilterNet Baseline | AI/ML Noise Suppression Core | `deepfilternet` 0.5.6 (DeepFilterNet3) | **Raspberry Pi 5 Verified:** 4-thread RTF = 0.17037 (median) / 0.18186 (p95); 1-thread RTF = 0.22033 (median) / 0.23425 (p95). ~5.8x faster than real-time. |
| Dataset Pipeline | Synthetic noisy/clean dataset synthesis (48 kHz) | `soundfile`, `scipy`, `numpy` | Computer |
| Spectral Subtraction Baseline | First-principles spectral subtraction (Berouti et al.) | `scipy.signal.stft`/`istft`, `numpy` | Computer: 300 files in 15.45s (0.051s/file). |
| Wiener Filter Baseline | First-principles Decision-Directed Wiener filter | `scipy.signal.stft`/`istft`, `numpy` | Computer: 300 files in 12.98s (0.043s/file). |
| NLMS Adaptive Filter Baseline | First-principles sample-by-sample NLMS adaptive filter | `numba`, `numpy`, `soundfile` | Computer: 300 files in 7.87s (0.026s/file). Strictly uses true pre-mix reference noise (`noise_id`, Rule 18). |
| Evaluation Engine | Objective metrics calculation (PESQ-WB, STOI, SI-SNR, ΔSI-SNR) | `pystoi`, `matplotlib`, `seaborn`, `pandas`, `torch` | Computer: Evaluated 1,500 condition-mixture pairs (5 methods × 300 mixtures). |
| DSP Baselines | Benchmark comparison against classical filters | Python (`scipy`, `numpy`) | Computer |
| Live Pipeline Config | Centralised config for SR, chunk size, ring buffer, device, mode | `pyyaml` | Config file: `config/audio_config.yaml` |
| RingBuffer | Thread-safe SPSC circular audio buffer | `numpy`, `threading` | Both (no hardware needed). Overflow drops oldest samples. |
| InferenceEngine | Stateful DFN3 wrapper: load, warmup, chunk-by-chunk enhance/bypass | `deepfilternet`, `torch` | Both (Mode A verified on PC). Dev machine: median RTF=0.093, p95=0.095 per 100 ms chunk. |
| LivePipeline | Sounddevice stream + RingBuffer + InferenceThread orchestration | `sounddevice`, `numpy` | Raspberry Pi 5 (Mode B — requires physical audio hardware) |
| LatencyTest | Click cross-correlation latency measurement (Mode A + Pi) | `numpy`, `scipy` | Both. Dev machine: enhance median=9.77 ms, bypass ~0 ms, lag=0 samples. |
| LatencyBudget (`live/latency_budget.py`) | Phase 2: single source of truth for the end-to-end latency budget — per-component `source` tag (measured/estimated/configured), mandatory `machine` field (Rule 5), JSON round-trip | `numpy`-free, stdlib only | Both (Mode A, no hardware). Replaces the inline arithmetic that used to live in a print statement in `e2e_latency_test.py`. |
| CPU Affinity (`live/cpu_affinity.py`) | Phase 2 (D5): best-effort pin of the calling thread (only the inference thread is reachable from Python — PortAudio's callbacks are internal C threads) to specific cores; clean no-op, never raises, on platforms without `os.sched_setaffinity` | stdlib `os` | Both. Dev machine (Windows): confirmed graceful no-op. Pin-vs-unpin A/B is Pi-only (Track B). |
| Fast Resample (`live/fast_resample.py`) | Phase 2 (D4): optional numba-JIT linear-interpolation resampler, drop-in for `pipeline.py::_resample()`; default OFF, kept only if a Pi A/B shows a real gain | `numba` (optional) | Both. Dev machine: bit-equivalent to `_resample` (max diff 0.00e+00) across 44.1k/16k/48k pairs; ~2.8x faster in a local microbenchmark (NOT a Pi measurement, Rule 5). |
| Acoustic Latency Test (`live/acoustic_latency_test.py`) | Phase 2 (D3, A5/A6): dual-mic physical acoustic round-trip measurement with a *running* pipeline in the loop (first in project history — see phase2_plan.md §1.2/§1.3), plus empirical DFN3 lookahead measurement (Rule 30, never read from config) | `sounddevice`, `numpy` | Acoustic round-trip and lookahead measurement are Pi-only (Mode B, real hardware/model required). Pure peak-detection/lag and lookahead arithmetic verified Mode A via `--self-test` (synthetic clicks + a fake-shift engine stand-in). |

| Web Dashboard (`demo/webdash/app.py`) | Phase 4 WOW #2: FastAPI + WebSocket server pushing live telemetry at 4 Hz over LAN; /mode/{enhance\|bypass} toggle reuses dashboard.py's atomic _mode assignment; single-page HTML client with mode toggle, noise category, MOS, RTF. Unauthenticated, LAN-only, demo-scoped. | `fastapi`, `uvicorn[standard]` (optional) | Both — dev machine for logic/self-test; Pi for live LAN demo |
| QR Generator (`demo/webdash/generate_qr.py`) | Phase 4 WOW #2: generates a QR code encoding `http://<pi-lan-ip>:8080` for judges to scan from a phone | `qrcode[pil]` (optional) | Dev machine / Pi |
| DNSMOS Monitor (`models/dnsmos/dnsmos_infer.py`) | Phase 4 WOW #3: non-intrusive perceptual MOS estimation (DNSMOS P.835). Background thread at 0.5 Hz, 9-second sliding window. Resamples 48kHz → 16kHz, computes log-mel spectrogram (numpy), runs Microsoft's sig_bak_ovr.onnx. Outputs SIG/BAK/OVR in [1,5]. Shows "measuring…" until first 9-second window fills (DoD-6). Warn at MOS < 2.5; auto-bypass OFF by default (R8). | `onnxruntime>=1.18.0` (optional; Pi-compatible per §1.2) | Both — timing must be measured on Pi (DoD-6), not asserted |
| Noise Classifier (`models/noise_classifier/classify_chunk.py`) | Phase 4 WOW #1: 3-class (stationary / non_stationary / impulsive) log-mel CNN trained on the project dataset with grouped split by noise_id (DoD-1). Confidence-calibrated output with UNCERTAIN state below threshold (DoD-3). Background thread at 500 ms; display-only under D1-A (no routing). Real-mic accuracy measured separately (DoD-2). | `torch` (already present) | Both — real-mic eval is Pi Track B (DoD-2) |
| Impulsive Event Log (`models/noise_classifier/impulsive_log.py`) | Phase 4 WOW #1 T3: timestamped JSONL log of detected impulsive acoustic events with confidence. Named "impulsive-event log" — NOT shot detection (D5, Rule 32). | stdlib only | Both |
| Shared Telemetry (`live/telemetry.py`) | Phase 4 T6: thread-safe telemetry namespace written by classifier and DNSMOS background threads, read by terminal dashboard, spectrogram, and webdash. Single struct so display surfaces cannot drift apart (T6). | stdlib only | Both |

## Future Augmentation TODOs (Phase 5+)
- [ ] Add room impulse response (RIR) reverberation convolution.
- [ ] Add non-linear microphone clipping and dynamic range distortion.
- [ ] Add speed perturbation and pitch shifting for speech diversity.

## Model Choice & Rationale
- **Model:** DeepFilterNet (Pretrained DeepFilterNet3 baseline for Phase 1; fine-tuning in later phases).
- **Rationale:** High speech intelligibility preservation with low computational latency suitable for edge/embedded processors. Confirmed on Raspberry Pi 5 with RTF 0.170 (5.8x faster than real-time). Empirically proven in Phase 4 to outperform all classical baselines across all 3 defence noise categories (+5.75 to +11.10 dB ΔSI-SNR).

## Deployment Target Specification
- **Hardware:** Raspberry Pi 5 (Quad-core ARM Cortex-A76 @ 2.4GHz)
- **OS:** Debian GNU/Linux 13 (trixie, 13.6)
- **Audio Stack:** `sounddevice` / PortAudio, USB Audio Interface / ALSA (`vc4hdmi` built-in audio confirmed)
- **Python Version:** Python 3.9.25 on Computer, Python 3.13.5 on Raspberry Pi 5
- **Package Manager:** `uv` on Computer; standard `pip`/`venv` on Raspberry Pi 5 (`uv` not installed)

## Decisions Log
- **2026-08-23:** Initialized project architecture for PS26052 targeting Raspberry Pi 5 deployment model with DeepFilterNet as primary AI/ML baseline.
- **2026-08-23:** Confirmed Pi 5 environment (Debian 13 trixie, Python 3.13.5). Approved `pip`/`venv` exception for Pi package installation since `uv` is not present.
- **2026-08-23:** Phase 1 DeepFilterNet RTF benchmark completed on Raspberry Pi 5. Measured 4-thread median RTF = 0.17037 (p95: 0.18186, latency: 511.1ms per 3.0s audio frame) and 1-thread median RTF = 0.22033 (p95: 0.23425, latency: 660.98ms), CPU temp 41.1°C to 47.2°C. Confirmed ~5.8x real-time execution headroom on Pi 5.
- **2026-08-23:** Phase 2 dataset generation complete. Built 300 synthetic mixtures (48 kHz, 150 LibriSpeech clean speech clips mixed across 3 noise categories × 5 SNR levels from -5 dB to +15 dB). Achieved 0.0000 dB post-mixing SNR mean deviation and 100% manifest-to-disk row count parity (300 rows == 300 wav files). Logged origins and proxy rationales in `data/SOURCES.md`.
- **2026-08-23:** Phase 3 classical DSP baselines implemented and executed across all 300 mixtures (900 output files total, 36.30s runtime).
- **2026-08-23:** Phase 4 Remediation & Final Evaluation complete. Resolved all requirements:
  - *Native Windows PESQ-WB Compilation:* Installed GCC build tools via winget (`BrechtSanders.WinLibs.POSIX.UCRT`) and built the `pesq` C extension (`cypesq.cp39-win_amd64.pyd`) linked against `python39.dll`. Evaluated all 1,500 condition-mixture pairs (100% valid, 0 exclusions) across PESQ-WB, STOI, SI-SNR, and ΔSI-SNR.
  - *DeepFilterNet DRDO Benchmark Verification (superseded, see 2026-08-24 entry below):* Original run measured **2.48–2.49 overall PESQ-WB mean**, **0.9169–0.9196 STOI**, and **+5.75 to +11.10 dB ΔSI-SNR**. The "meeting the DRDO PESQ > 2.5 requirement" claim in this line was itself incorrect (2.48/2.49 are both below 2.5) — corrected same-day in the 2026-08-23 Phase 4 Closeout entry below, and the impulsive figures were further corrected on 2026-08-24 (see below) after a dataset gap was found.
  - *Un-Confounded NLMS Ablation:* Isolated alignment fix (`combo_seed`) from step-size damping ($\mu = 0.10 \to 0.01$). Alignment alone improved ΔSI-SNR by $+1.76\text{ to }+2.19\text{ dB}$, while step-size damping ($\mu = 0.01$) prevented speech formant tracking, unlocking $+3.97\text{ dB}$ ΔSI-SNR on stationary noise.
  - *Impulsive Zero-Lag Check:* Confirmed 0-sample cross-correlation lag on impulsive clips; NLMS ΔSI-SNR collapse on impulsive noise is a true structural convergence lag on rapid acoustic transients, validating the core pitch for AI/ML ANC (exact figure corrected 2026-08-24, see below: −7.10 dB on the real gunshot/artillery corpus, not −3.30 dB as originally measured on an explosion-only proxy). All deliverables updated (`results/eval_raw.csv`, `results/results.csv`, `results/charts/`, `docs/phase_4_summary.md`).
- **2026-08-23 (Phase 4 Closeout):** Built `results/final/target_compliance.md` + `.json` with honest per-category PASS/FAIL verdicts. Corrected phase_4_summary.md (PESQ > 2.5 target not met in any category on full SNR-averaged evaluation — later partially superseded, see 2026-08-24 entry). Applied NLMS reference-assisted labeling and ANC -> noise suppression/speech enhancement terminology corrections. Rules 29-33 appended.
- **2026-08-23 (Phase 5 Mode A):** Built live pipeline stack: `config/audio_config.yaml`, `live/ring_buffer.py` (SPSC ring buffer, 6-test self-test PASS), `live/inference_engine.py` (DFN3 wrapper, 6-test self-test PASS, dev machine RTF=0.093), `live/pipeline.py` (streaming orchestrator), `live/latency_test.py` (click cross-correlation, enhance=9.77 ms median wall, 0-sample lag, bypass ~0 ms). All Mode A tests verified on dev machine. Mode B (Pi hardware) tests pending.
- **2026-08-24 (Phase 5 Mode B — COMPLETE):** All physical Pi 5 tests verified with real pasted-back evidence (Rule 29):
  - **Latency (in-memory, Pi 5):** bypass median=0.00 ms, enhance median=29.18 ms (RTF=0.292), 0-sample cross-correlation lag on all 10 reps. `lookahead_samples`=0 confirmed empirically (Rule 30). Results saved to `results/latency_pi.json`.
  - **10-Minute Stress Test:** Verdict PASS — 600.3 s continuous ENHANCE mode, 5997 chunks, median RTF=0.378, max temp=50.1°C, 0 ring-buffer overflows, 0 underruns.
  - **Terminal Dashboard:** Rendered correctly on Pi SSH session (ANSI TUI, CPU/RAM/Temp/latency telemetry), mode toggle via 'b', clean exit via 'q'. Session: 684 chunks, median RTF=0.372, 0 dropouts.
  - **RTF finding (Rule 33):** Live loopback RTF=0.378 exceeds the target of <0.25 but is well below the real-time limit of 1.0. Reported as measured. With real USB audio hardware (less loopback scheduling jitter), RTF is expected closer to the in-memory 0.292 figure.
- **2026-08-24 (Post-Phase-5 hardening):** README status fix, `demo/spectrogram.py` (live terminal waterfall, ENHANCE/BYPASS visual contrast, self-test verified), `scripts/run_all_selftests.py` (unified Mode A test runner — caught and led to fixing a real bug: `run_inference.py`'s self-test depended on a stale Phase-1 fixture and a duplicate-glob bug in unused `batch_inference()`), `docs/non_stationary_root_cause.md` (subtype decomposition: the non-stationary gap is driven almost entirely by crowd/babble, not helicopter — cocktail-party problem, a structural single-channel limitation). `scripts/build_pesq_gcc.py` made portable (was hardcoded to a different machine's GCC path and Python 3.9 ABI tag; rebuilt and verified working for this machine's Python 3.11).
- **2026-09-04 (Phase 2 Track A — latency engineering, dev-machine work):** Implemented `phase2_plan.md`'s dev-machine track ahead of the deferred Pi hardware batch (see `[[pi-work-deferred-to-end]]`-style ordering in this project). **Found and fixed a real pre-existing bug first:** `config/audio_config.yaml` declared TWO top-level `audio:` blocks and TWO top-level `pipeline:` blocks (the Phase 1 dual-mic/reference-NLMS sections were appended as new top-level keys instead of nested under the existing ones). YAML silently collapses duplicate mapping keys to the last one seen, so `yaml.safe_load` was discarding `sample_rate`, `chunk_duration_sec`, `input_device: 1`, `output_device: 0`, `priming_chunks`, etc. from the first blocks, keeping only `dual_mic`/`reference_nlms` — verified directly (`python -c "import yaml; print(yaml.safe_load(...))"` returned `audio: {'dual_mic': {...}}` with every other key missing). `live/pipeline.py`'s `_load_config` deep-merge then silently fell back to its hard-coded defaults for the dropped keys, meaning the documented real Generalplus USB device indices were never actually being honored on any run to date (auto-detection happened to compensate). Merged into single `audio:`/`pipeline:` blocks; re-verified all keys now load correctly. New work landed on top of the fix: `live/latency_budget.py` (A0, source-tagged latency budget dataclass), fractional `priming_chunks` (A1, D1 — float, `1.0` byte-identical to the old int-loop behaviour, verified via `live/pipeline.py --self-test`), startup-underrun tolerance (A2, D2 — `_startup_underruns` bucket separate from real dropouts, bounded by `startup_grace_sec`, always reported even though excluded from the stress verdict), `live/cpu_affinity.py` (A3, D5 — inference-thread-only pinning, confirmed graceful no-op on this Windows dev machine), `live/fast_resample.py` (A4, D4 — optional numba resampler, confirmed bit-equivalent to `_resample` on this machine, kept only if the Pi A/B in Track B shows a real gain), `live/acoustic_latency_test.py` (A5/A6, D3 — physical acoustic round-trip method with a running pipeline in the loop, plus empirical DFN3 lookahead measurement per Rule 30; both are Mode B/Pi-only, logic verified Mode A via synthetic clicks and a fake-engine stand-in), and `scripts/sweep_chunk_size.py` propagation of `dual_mic`/`reference_nlms`/`priming_chunks` into scratch configs plus a `startup_underruns` summary column (A7). All new/changed modules default-off or behavior-preserving at their defaults (`priming_chunks: 1.0`, `cpu_affinity: null`, `fast_resample: false`) — the single-mic demo path is unchanged. Track B (Pi hardware: re-baseline, priming validation, chunk-size re-sweep, pin/fast-resample A/Bs, the acoustic measurement itself, final 600s gate) remains outstanding — see `progress.md` for the full self-test evidence and the honest DoD status.
- **2026-08-24 (Dataset gap found and fixed — gunshot/artillery corpus):** Discovered `data/noise/impulsive/` was missing the `gunshot` (2,148 files) and `artillery` (30 files) corpora entirely — only `explosion` (40 files) was present, due to an earlier commit (`feb019c`) regenerating the manifest before a failing Zenodo download had actually completed. Every "impulsive" result documented up to this point (Phase 3, Phase 4, target_compliance) was silently computed on explosion-only noise despite being labeled "Gunshot/Artillery." Automated re-download was blocked by Zenodo's anti-bot rate limiting (network-level 403, not a code bug); corpus obtained via manual browser download and the full pipeline (manifest -> mixtures -> baselines -> DeepFilterNet -> eval, 1500 pairs) regenerated end to end. **Corrected impulsive results are stronger than previously reported**: PESQ-WB 2.4916 (FAIL) -> **2.5841 (PASS)**, STOI 0.9196 -> 0.9319, SI-SNR +15.20 -> +15.75 dB; NLMS ΔSI-SNR collapse deepened from −3.30 dB to **−7.10 dB** on real gunshot transients (sharper AI/ML-vs-classical contrast, not a regression). Impulsive is now the only category passing all three DRDO targets. `data/mix_dataset.py` and `scripts/download_datasets.py` hardened so this class of silent failure can't recur: `mix_dataset.py` now hard-fails (`--allow-partial-corpus` to override) if any declared noise subtype has zero files, instead of printing a warning and proceeding; `download_datasets.py` gained a `setup_gunshot()` function with a clear manual-download fallback message. Full incident writeup: `docs/phase_4_summary.md` (2026-08-24 correction note), `data/SOURCES.md` §5, `results/final/target_compliance.md`.
- **2026-09-04 (Phase 4 — WOW factors, `phase4_plan.md`):** Phase 4 implements three demo differentiators: (1) Noise classifier (WOW #1) — 3-class log-mel CNN trained with grouped split by noise_id; display-only under D1-A (no routing — T1 confirmed the NLMS realistic penalty is uniformly negative across all non-stationary subtypes: crowd AND helicopter PESQ consistently drops from ~1.5–3.5 to ~1.04–1.18, so no category-dependent routing policy exists; router dead, D1-B stays closed); real-mic accuracy gates whether it is demoed (DoD-2, Track B). (2) Web dashboard (WOW #2, built first per D6) — FastAPI + WebSocket server, /mode/{...} toggle reusing dashboard.py's existing _mode assignment pattern (§3.1), unauthenticated LAN-only demo scope. (3) DNSMOS quality monitor (WOW #3) — Microsoft P.835 model via onnxruntime; Pi-compatible per §1.2 (onnxruntime inference has no onnx/ml_dtypes dependency, numpy<2.0 conflict doesn't trigger); dev uses onnxruntime==1.18.0 (last cp39 build), Pi uses >=1.18.0 (D3-A); per-inference timing must be measured on Pi, not asserted (DoD-6). All three features default-off. "Shot detection" claim removed per D5/Rule 32 — feature is "impulsive-event log." No RTF-impact claim until B5 measures it (Rule 1). DNSMOS model origin + licence recorded in models/dnsmos/SOURCES.md (Rule 12).
- **2026-09-04 (Phase 3 — quality validation, `phase3_plan.md`):** Found and fixed a second, separate reproducibility bug: `data/mix_dataset.py` used unsorted `glob.glob()`, so dataset generation wasn't actually deterministic despite a fixed seed — `data/manifest.csv` had drifted 34 rows out of sync with `data/mixtures/` on disk. Fixed at the source (`sorted()` on the glob calls) and regenerated end to end; the 2026-08-24 entry's 2.5841 PESQ-WB (impulsive) turned out to be an unreproducible favorable draw — the honest reproducible baseline is 2.4916 (FAIL, −0.0084). Phase 3 then swept `model.atten_lim_db` (`scripts/sweep_atten_lim.py`) and found `atten_lim_db=30` (was 100) maximizes PESQ-WB in every category with no STOI/SI-SNR regression beyond a pre-committed tolerance — closing **both** the impulsive (→2.5428) and stationary (→2.5385) PESQ-WB gaps. `config/audio_config.yaml`'s default changed accordingly. Also added: data-augmentation robustness analysis (`docs/augmentation_robustness.md` — DeepFilterNet degrades far more gracefully than NLMS under reverb/clipping), a spectral-tilt post-processing experiment (`docs/postproc_experiments.md` — dropped, negative result as expected), and an offline dual-mic reference-adaptive A/B with a realistically-degraded (not oracle) reference (`scripts/simulate_reference_channel.py` — NLMS's oracle advantage on crowd babble inverts to strongly negative SI-SNR under a realistic reference, so a simple NLMS second-mic stage is not a viable mitigation for the non-stationary gap). **Final compliance: 6 of 9 metric cells PASS** (up from 4/9 pre-tuning), with the 3 remaining failures all in non-stationary/crowd-babble, root-caused as structural (cocktail-party problem) rather than a tuning gap. Full detail: `progress.md` (2026-09-04 entries), `results/final/target_compliance.md`.

