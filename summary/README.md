# Project Summary — PS26052

**Smart India Hackathon 2026 · DRDO Problem Statement 26052**
*AI/ML-Enabled Adaptive Noise Cancellation for Defence Communications*

This folder contains the two consolidated project documents. Everything else in the repository is working material; these two are what you read to understand where the project stands and where it goes next.

---

## 📘 [01_PROJECT_ACCOMPLISHMENTS.md](01_PROJECT_ACCOMPLISHMENTS.md)

**Complete record of everything built and proven, Phase 0 → post-Phase-5.**

Contains: PS26052 requirement mapping · phase-by-phase deliverables · all empirical results with evidence · the four incidents found and fixed · the final DRDO compliance matrix · full repository inventory · and a frank section separating what is *proven on hardware* from what is *not yet verified*.

**Headline:** on the corrected dataset, DeepFilterNet3 clears **all three DRDO targets simultaneously on impulsive defence noise** — SI-SNR +15.75 dB, STOI 0.9319, PESQ-WB 2.5841 — while the oracle-assisted classical NLMS filter *degrades* the same audio by −7.10 dB. That ~18 dB spread is the project's core evidence for AI/ML necessity.

---

## 📗 [02_NEXT_STEPS_PLAN.md](02_NEXT_STEPS_PLAN.md)

**Concrete, prioritized plan for the prototype evaluation round.**

Contains: the central real-time finding · gap analysis vs PS26052 · P0/P1/P2 task breakdowns with time estimates and acceptance criteria · a consolidated latency engineering plan · demo day runbook · risk register · suggested schedule · and prepared answers to likely evaluator questions.

**The one thing to act on first:** the system currently reports *"29.18 ms latency"*, but that is **per-chunk model inference time**, not end-to-end latency — `live/latency_test.py` is an in-memory Mode A test by its own documentation. Static analysis of `live/pipeline.py` puts true mouth-to-ear latency at roughly **530 ms** (100 ms input block + 300 ms output priming + 100 ms output block + ~30 ms inference), which is well above the ITU-T G.114 threshold for interactive voice. It has never been measured, and it needs to be measured and then engineered down to < 150 ms. Every contributor to that budget is controllable in configuration.

---

## Current Status at a Glance

| Dimension | Status |
|---|---|
| Dataset pipeline (300 seeded mixtures, 48 kHz, 7 subtypes) | ✅ Complete & verified |
| Classical DSP baselines (Spectral Subtraction, Wiener, NLMS) | ✅ Complete, 900 files, 100% sanity |
| Objective evaluation (PESQ-WB / STOI / SI-SNR, 1500 pairs) | ✅ Complete, 0 exclusions |
| DeepFilterNet3 on Raspberry Pi 5 | ✅ RTF 0.17037 (4-thread) |
| Real-time streaming pipeline | ✅ Runs, 0 dropouts over 600 s |
| ENHANCE/BYPASS live toggle + TUI dashboard | ✅ Verified on Pi |
| Live before/after spectrogram | ⚠️ Built, self-tested — **not yet run on Pi** |
| **Physical microphone / headset integration** | ❌ **Not yet acquired — all validation used ALSA virtual loopback** |
| **True end-to-end latency** | ⚠️ **Test built (`live/e2e_latency_test.py`), not yet run on Pi** — device-I/O round-trip via the real audio stack, no mic needed; still pending Pi-side execution |
| **Latency reduction (priming/chunk size)** | ⚠️ **Built** — priming made configurable (3→1 chunk default), sweep harness ready (`scripts/sweep_chunk_size.py`); not yet validated on Pi |
| Model optimization (ONNX / quantization) | ❌ Not started |
| Fine-tuning / training framework | ❌ Not started |

**DRDO target compliance:** Impulsive **3 of 3 ✅** · Stationary 2 of 3 · Non-stationary 0 of 3
*(Non-stationary shortfall root-caused to the crowd-babble subtype specifically — see [`docs/non_stationary_root_cause.md`](../docs/non_stationary_root_cause.md). Helicopter alone scores 0.9108 STOI / +8.9 dB.)*

---

## Related Documentation

| Document | Purpose |
|---|---|
| [`../README.md`](../README.md) | Repository front page, quick start |
| [`../progress.md`](../progress.md) | Append-only execution log with verbatim command evidence |
| [`../architecture.md`](../architecture.md) | Living architecture + dated decisions log |
| [`../rules.md`](../rules.md) | Engineering discipline rules (anti-hallucination, evidence requirements) |
| [`../results/final/target_compliance.md`](../results/final/target_compliance.md) | Authoritative DRDO compliance matrix |
| [`../docs/`](../docs/) | Per-phase execution reports (0-1, 2, 3, 4, 5) + root-cause analysis |
| [`../data/SOURCES.md`](../data/SOURCES.md) | Dataset provenance, licenses, corpus recovery record |

---

*Compiled 2026-08-24.*
