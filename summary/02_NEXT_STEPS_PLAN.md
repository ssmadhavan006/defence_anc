# PS26052 — Comprehensive Next-Steps Plan
**Smart India Hackathon 2026 · DRDO Problem Statement 26052**
*What remains to be done to make the system genuinely real-time and to maximize the prototype evaluation round.*

**Plan date:** 2026-08-24
**Current state:** Phases 0–5 complete; see `summary/01_PROJECT_ACCOMPLISHMENTS.md`
**Companion:** every gap referenced here is evidenced in Section 13 of the accomplishments record.

---

## Table of Contents

1. [The Central Finding: You Are Not Yet Real-Time](#1-the-central-finding-you-are-not-yet-real-time)
2. [Gap Analysis Against PS26052](#2-gap-analysis-against-ps26052)
3. [Priority Framework](#3-priority-framework)
4. [P0 — Blocking for the Prototype Evaluation Round](#4-p0--blocking-for-the-prototype-evaluation-round)
5. [P1 — High-Value Scoring Improvements](#5-p1--high-value-scoring-improvements)
6. [P2 — Stretch / Round 2 Differentiators](#6-p2--stretch--round-2-differentiators)
7. [Consolidated Latency Engineering Plan](#7-consolidated-latency-engineering-plan)
8. [Demo Day Runbook](#8-demo-day-runbook)
9. [Risk Register & Contingencies](#9-risk-register--contingencies)
10. [Suggested Execution Schedule](#10-suggested-execution-schedule)
11. [Answering Evaluator Questions](#11-answering-evaluator-questions)

---

## 1. The Central Finding: You Are Not Yet Real-Time

This is the most important thing in this document, so it comes first.

### 1.1 What is currently claimed vs what was actually measured

The project reports **"29.18 ms latency"** as its live-pipeline latency figure. That number is real, but it measures **model inference wall time for one 100 ms chunk** — it is not end-to-end latency. `live/latency_test.py` says so in its own docstring:

> *"This test does NOT require physical audio hardware (it operates on in-memory audio arrays, not a sounddevice stream). It is therefore Mode A..."*

It was executed *on* the Pi, so the compute is genuine Pi compute — but it never passes through `sounddevice`, never touches a real capture or playback device, and therefore cannot and does not measure the delay a listener actually experiences.

**The project plan explicitly required the opposite:**
> *"You must measure: Input buffer + Algorithmic lookahead + Model inference + Output buffer = End-to-end latency. Don't simply say 'Our latency should be around X ms.' Actually measure it. The guide requires a physical loopback click test with 20 repetitions and a reported median."*

That test has not been performed. Additionally, only **10 repetitions** were used rather than the specified 20.

### 1.2 What the real latency almost certainly is

Reading the actual configuration and `live/pipeline.py` line by line, the standing latency budget is:

| Stage | Source | Delay |
|---|---|---|
| Input block fill | `blocksize = chunk_samples = 4800` @ 48 kHz — PortAudio must capture a full block before the callback fires | **100 ms** |
| Ring-buffer transit | Inference thread reads 4,800 samples; wakes on condition variable | ~0–100 ms (load-dependent) |
| Model inference | Measured on Pi 5 | **29–38 ms** |
| **Output priming** | `pipeline.py` pre-writes **3 chunks of silence** into the output ring buffer at startup. This is a FIFO — that silence never drains, it becomes permanent standing delay | **300 ms** |
| Output block drain | `blocksize = 4800` on the output stream | **100 ms** |
| ALSA/PortAudio device buffers | Not instrumented | unmeasured, additive |
| **Estimated total mouth-to-ear** | | **≈ 530 ms +** |

For reference, **ITU-T G.114** recommends **< 150 ms** one-way delay for interactive voice and considers **> 400 ms** unacceptable for most interactive use. A defence communications system at ~530 ms would be conversationally unusable — operators would talk over each other constantly.

> ⚠️ **This is the single biggest technical risk in the project.** An evaluator who asks *"what's your end-to-end latency?"* must not receive the 29.18 ms number, because that answer is not what the question is asking. It needs to be measured honestly and then engineered down.

### 1.3 The good news

Every contributor to that budget is **directly controllable in configuration and a few lines of code**, and there is enormous compute headroom to spend (RTF 0.29–0.38 means the CPU is idle ~65% of the time). A realistic post-optimization target is **75–110 ms end-to-end**, which is squarely inside the G.114 "good" band — and that becomes a genuinely impressive, defensible headline number.

---

## 2. Gap Analysis Against PS26052

| PS26052 requirement | Status | Gap | Priority |
|---|---|---|---|
| Scalable dataset pipeline | ✅ Complete | — | — |
| SOTA AI/ML model for noise suppression | ⚠️ Partial | Pretrained only, no fine-tuning | P1 |
| Training framework, tuned hyper-params, perceptual loss | ❌ Missing | Requires Rust `libdfdata` + HDF5 conversion | P2 |
| Real-time inference engine on edge hardware | ⚠️ Partial | Runs, but **latency not real-time-grade or measured** | **P0** |
| Prototype with microphone / headset integration | ⚠️ Partial | **Never tested with a physical microphone** | **P0** |
| SNR > 15 dB | 2 of 3 categories | Non-stationary at 10.75 dB | P1 |
| STOI > 0.85 | 2 of 3 categories | Non-stationary at 0.8297 | P1 |
| PESQ > 2.5 | 1 of 3 categories | Stationary −0.018, non-stationary −0.370 | P1 |
| Data augmentation (reverb, clipping) | ❌ Missing | Not implemented | P1 |
| Quantization / pruning / ONNX / TensorRT | ❌ Missing | Not implemented — also the best latency lever | P1 |
| Primary + reference microphone | ❌ Missing | Single-channel only; NLMS reference is an offline oracle | P1 |
| Lightweight LMS residual suppression stage | ⚠️ Partial | NLMS exists as an offline baseline, **not integrated into the live path** | P1 |

---

## 3. Priority Framework

- **P0 — Blocking.** Without these, the prototype demo either cannot be honestly described as a real-time microphone-based system, or carries unacceptable failure risk on demo day. **Do these first, in order.**
- **P1 — High-value.** Directly addresses explicit PS26052 requirements or unmet numeric targets. Each meaningfully improves the evaluation score.
- **P2 — Stretch.** Strong differentiators, but expensive and non-blocking. Only if P0 and P1 are genuinely complete.

---

## 4. P0 — Blocking for the Prototype Evaluation Round

### P0-1 · Acquire and integrate physical audio hardware ⏱️ 1–2 h (+ procurement)

**Why:** PS26052 requires *"integrated with microphones (primary + reference) and headphones/communication units to validate real-time ANC performance in practical environments."* Right now the system has literally never heard a real sound. Everything ran through ALSA `snd-aloop`, a virtual software loopback.

**Hardware needed (minimum viable):**
- 1 × USB microphone or USB audio interface with mic input (a USB conference mic or a cheap USB sound card + electret mic both work)
- 1 × wired headphones/headset (3.5 mm into the Pi, or into the same USB interface)
- *(For P1-4 dual-mic)* a second microphone, ideally on a 2-in USB interface

**Steps:**
```bash
# On the Pi, with hardware plugged in:
python live/main.py detect
```
This enumerates PortAudio devices and suggests a config block. Then **hardcode the resulting indices** in `config/audio_config.yaml` (`input_device`, `output_device`) rather than relying on auto-selection — auto-selection reorders across reboots and USB re-plugs and *will* break on demo day.

```bash
# Confirm capture works at all before touching the model:
arecord -D hw:<CARD>,0 -f S32_LE -r 48000 -c 1 -d 5 /tmp/mic_test.wav
aplay /tmp/mic_test.wav
```

**Acceptance criteria:**
- `python live/main.py pipeline --mode bypass` passes your own voice through to the headphones audibly and without dropouts for 60 s.
- `python live/main.py pipeline --mode enhance` audibly suppresses noise on live speech.
- Device indices are hardcoded in `config/audio_config.yaml` with a comment naming the physical device.

---

### P0-2 · Build a true end-to-end latency test ⏱️ 2–3 h

> **Status update (2026-08-24, DONE):** run on the Pi and verified. Result: **42.67 ms device round-trip** (median = p95 = min = max across 20 reps — deterministic digital `snd-aloop` loopback) → **~172 ms full-pipeline estimate** (round-trip + inference + 100ms priming). Getting here required fixing a real bug first: `config/audio_config.yaml` had `input_device`/`output_device` both pointing at the same `snd-aloop` device, which is silent by construction — ALSA loopback cross-pairs the two PCM devices, it doesn't loop one back to itself. Fixed (`input_device: 1`, `output_device: 0`); the test then read a real, consistent round-trip instead of exact zeros. See `docs/phase_5_summary.md` §7 and `progress.md` (2026-08-24 entry) for the full writeup. **What this still does not cover:** it's `snd-aloop`, not a physical microphone — P0-1 remains open, and this number should be re-verified once real hardware is available. The rest of this section is preserved as the original design rationale.

**Why:** See Section 1. You cannot optimize what you have not measured, and the number you would currently quote is the wrong number.

**Create `live/e2e_latency_test.py`.** Unlike the existing Mode A test, this one must drive the *actual* `sounddevice` streams:

**Design:**
1. Open input and output streams **simultaneously** using the same config as the live pipeline.
2. Emit a sharp click (single-sample impulse, or a short 1 kHz tone burst — more robust acoustically) on the output.
3. Simultaneously record the input.
4. Cross-correlate the recorded signal against the emitted click; the peak offset is the **true round-trip latency in samples**.
5. Repeat **20 times** (per the plan), report **median and p95**, and save JSON.
6. Run in both BYPASS and ENHANCE mode — the delta isolates the model's contribution.

**Two loopback options (do both if possible):**
- **Electrical loopback (preferred for precision):** patch the Pi's audio output directly into the USB interface's input with a cable. Measures the full software + driver + device path with no acoustic variability. This is the number to report.
- **Acoustic loopback (preferred for realism):** place the headphones/speaker next to the microphone. Includes the true acoustic path. Subtract the speed-of-sound term (~2.9 ms per metre) if you want the electronic figure.

**Important interpretation note:** round-trip loopback latency measures out→in. One-way mouth-to-ear latency for a comms system is what G.114 governs. State clearly which you are reporting; reporting round-trip and noting it is conservative is the honest approach.

**Acceptance criteria:**
- `results/e2e_latency_pi.json` exists with 20 reps, median and p95, for both modes, generated on the Pi with real hardware.
- The number is quoted in all future documentation **instead of** 29.18 ms as "end-to-end latency" (29.18 ms remains valid and useful, correctly labeled as *per-chunk inference time*).

---

### P0-3 · Reduce latency to real-time grade ⏱️ 3–5 h

> **Status update (2026-08-24, DONE — with an honest gap against the target):** Step 1 (priming 3→1) and Step 2 (chunk-size sweep) both validated on the Pi. **100 ms chunk size selected and confirmed** via `scripts/sweep_chunk_size.py` + a full 10-minute `python live/main.py stress --duration 600`: PASS, 0 dropouts / 6001 chunks, RTF median 0.3823 / p95 0.4008, max temp 52.9°C. 20ms and 10ms fail the RTF≤0.6 budget outright; 50ms hits a sustained `snd-aloop` driver-level `input overflow` issue that survived two different application-level fix attempts (see `progress.md`'s 2026-08-24 entry for the full falsified-hypothesis writeup — a non-blocking-read fix was tried, tested, found to make things worse, and correctly reverted) and wasn't pursued further given the demo timeline. **Gap:** this section's own acceptance criterion was <150ms, ideally <100ms. The confirmed result is **~172ms** — real progress from the ~530ms estimate, but the target is not fully met. Closing it further needs either physical hardware (P0-1, may not share the 50ms `snd-aloop` issue) or P1-3 (ONNX/quantization to shrink inference and permit a smaller chunk). The rest of this section is preserved as the original design rationale.

**Why:** ~530 ms is not deployable for interactive voice. This is where the project's biggest single quality improvement is available.

Apply in this order, **measuring with P0-2 after each step** so you know what each change bought:

#### Step 1 — Cut output priming (biggest win, near-zero cost) → saves ~200 ms

`live/pipeline.py` currently pre-fills the output buffer with 3 chunks of silence:
```python
silence = np.zeros((self._chunk_samples, self._channels), dtype=np.float32)
for _ in range(3):
    self._out_buf.write(silence)
```
Because the ring buffer is FIFO, that 300 ms never drains — it is permanent standing delay. Reduce to **1 chunk** (or make it configurable via `pipeline.priming_chunks` in YAML), then stress-test for underruns. If 1 chunk underruns, try 2.

**Trade-off:** less priming = less cushion against inference jitter = higher underrun risk. Measured p95 inference is 39 ms against a 100 ms chunk, so a single chunk of priming should be comfortable — but verify with a 10-minute run, don't assume.

#### Step 2 — Reduce chunk size → saves up to ~160 ms

`chunk_duration_sec: 0.1` (4,800 samples) sets **both** the input and output block size, so it costs you twice. The original project plan targeted **10 ms blocks**.

Sweep chunk size empirically — **do not assume smaller is strictly better**, because per-call overhead is fixed and RTF will rise as chunks shrink:

| Chunk | Samples | Expected RTF | In+Out latency |
|---|---|---|---|
| 100 ms | 4800 | 0.29 (measured) | 200 ms |
| 50 ms | 2400 | ~0.35 (estimate) | 100 ms |
| 20 ms | 960 | ~0.5–0.7 (estimate) | 40 ms |
| 10 ms | 480 | ~0.8–1.0+ (risky) | 20 ms |

Keep the chunk an integer multiple of DeepFilterNet3's internal frame hop (10 ms at 48 kHz = 480 samples) so no partial frames are introduced. **Pick the smallest chunk that keeps p95 RTF ≤ 0.6** — that preserves ~40% headroom for jitter, which is what actually prevents dropouts.

Add a sweep harness (`scripts/sweep_chunk_size.py`) that runs the latency test at 480/960/2400/4800 samples and tabulates RTF and dropouts, so this decision is data-driven and presentable as a chart.

#### Step 3 — Explicitly control device buffer size

`sounddevice` is already opened with `latency="low"`, but PortAudio/ALSA may still allocate generous buffers. Consider passing an explicit `latency=<seconds>` float (e.g. `latency=0.01`) and verify the resulting `stream.latency` attribute — log it at startup so it is visible rather than assumed.

#### Step 4 — Consider ONNX Runtime / quantization (see P1-3) → cuts inference time

Lower inference time widens the RTF margin, which in turn permits a smaller chunk in Step 2. These compound.

**Target outcome:**

| Configuration | Priming | Chunk | Est. end-to-end |
|---|---|---|---|
| Current | 300 ms | 100 ms | **~530 ms** |
| After Steps 1–2 (50 ms chunk) | 50 ms | 50 ms | **~180 ms** |
| After Steps 1–2 (20 ms chunk) | 20 ms | 20 ms | **~85 ms** |
| After Steps 1–4 (20 ms + ONNX int8) | 20 ms | 20 ms | **~75 ms** |

**Acceptance criteria:**
- Measured end-to-end latency (P0-2 method) **< 150 ms**, ideally < 100 ms.
- 10-minute stress test still passes with **0 dropouts** at the new settings.
- A before/after latency table exists for the presentation — this is a genuinely compelling slide.

---

### P0-4 · Re-run the stability gate with real audio ⏱️ 30 min (+ 10 min runtime)

**Why:** the existing 10-minute PASS was run on `snd-aloop` with nothing feeding it — it validates stability, thermals, buffer management, and CPU load (DeepFilterNet runs identically regardless of input content), but it is **not** "10 minutes of live noise cancellation." Saying so in front of evaluators would be an overstatement.

```bash
# With real mic connected, real speech + noise playing in the room:
python live/main.py stress --duration 600 --output-json results/stress_test_real_mic.json
```

Play continuous defence-relevant noise through a speaker during the run (use clips from `data/noise/`) with intermittent speech, so the model is genuinely working the whole time.

**Acceptance criteria:** 600 s, 0 dropouts, max temp < 80 °C, with a real microphone and real acoustic input — plus a note in `progress.md` distinguishing this run from the earlier loopback run.

---

### P0-5 · Smoke-test the spectrogram on the Pi ⏱️ 30 min

**Why:** `demo/spectrogram.py` has only ever passed its offline `--self-test` with synthetic arrays. It has never run against the Pi, real audio, or an SSH terminal. It is intended to be a centerpiece of the live demo — an untested centerpiece is a liability.

```bash
python demo/spectrogram.py
```

**Check specifically:**
- ANSI 256-colour rendering works in your actual demo terminal (some SSH clients/terminals degrade colour; test the exact one you will use on the day)
- Refresh rate feels responsive without flicker
- The BEFORE panel visibly lights up under noise and the AFTER panel visibly darkens under ENHANCE
- The `b` toggle produces an obvious, immediate visual difference (this is the money shot)
- Terminal width ≥ 64 columns renders the panels without wrapping

**Fallback if terminal colour is unreliable:** add a `--ascii` mode using only density characters (` .:*#`) with no colour codes.

---

### P0-6 · Update all documentation with corrected latency framing ⏱️ 1 h

Once P0-2 and P0-3 produce real numbers, update `README.md`, `docs/phase_5_summary.md`, `results/final/`, and `progress.md` so that:
- "End-to-end latency" refers **only** to the measured P0-2 figure
- 29.18 ms is relabeled **"per-chunk model inference time (Pi 5)"**
- The Phase 5 Definition-of-Done checklist row currently reading *"`measure_latency.py` physical loopback (Test 5, Mode B) ✅ PASS"* is corrected — it was an in-memory Mode A test, not a physical loopback

This matters: the project's credibility rests on the honesty record established in `rules.md`, and this is exactly the kind of mislabel that record exists to catch.

---

## 5. P1 — High-Value Scoring Improvements

### P1-1 · Integrate an LMS residual-suppression stage into the live path ⏱️ 3–4 h

**Why:** PS26052 explicitly describes the architecture as *"The system can optionally include a lightweight adaptive filter (e.g., LMS) for residual noise suppression."* You have a fully implemented, Numba-JIT NLMS — but only as an **offline evaluation baseline**. Wiring it into the live pipeline as a post-model residual stage directly satisfies a stated requirement and makes the system a genuine **hybrid** AI + adaptive-filter design, exactly as the PS describes.

**Design:** `noisy → DeepFilterNet3 → NLMS residual stage → output`, with the NLMS operating on the model's residual. Add a `pipeline.residual_filter: true|false` config flag and a third demo mode so you can A/B *that* too.

**Caveat to handle honestly:** the offline NLMS uses an oracle noise reference. In the live single-mic path there is no such reference — so either (a) run it in a reference-free adaptive configuration, or (b) feed it the reference microphone once P1-4 lands. Option (b) is the stronger story and pairs naturally with dual-mic hardware.

---

### P1-2 · Primary + reference dual-microphone capture ⏱️ 4–6 h

**Why:** PS26052 states *"microphones (primary + reference)"* explicitly. It is also the **only architecturally sound fix for the crowd-babble weakness** documented in `docs/non_stationary_root_cause.md` — a second spatial channel gives the system the cue a single channel fundamentally lacks for separating target speech from background speech.

**Steps:** move `channels: 1` → `2` in config, extend `RingBuffer` usage to carry both channels (it already supports multi-channel), route channel 0 to DeepFilterNet and channel 1 to the NLMS reference input, and demonstrate the combination.

**Payoff:** directly addresses the worst-performing category *and* satisfies an explicit hardware requirement. High value, moderate cost.

---

### P1-3 · Model optimization — ONNX Runtime / quantization ⏱️ 4–8 h

**Why:** PS26052 explicitly lists *"quantization, pruning, and ONNX / TensorRT conversion... to meet latency and power constraints."* Currently none are applied. This is both a checkbox requirement **and** the most direct route to lower inference time, which compounds with P0-3.

**Path:** DeepFilterNet ships `df/scripts/export.py` for ONNX export. Convert DFN3 → ONNX → ONNX Runtime with ARM64 optimizations, then attempt **int8 dynamic quantization**.

**Expected gain:** typically 1.5–3× inference speedup on ARM. If inference drops from 29 ms → ~12 ms, a 20 ms chunk becomes comfortable (RTF ~0.6) instead of marginal.

**Critical requirement — do not skip:** after any quantization, **re-run the full 1,500-pair evaluation** and compare PESQ/STOI/SI-SNR against the FP32 baseline. Quantization can silently degrade quality. Report both, and only adopt the quantized model if the loss is negligible. You already have the harness for this (`eval/run_eval.py`), which makes this cheap to verify and a genuinely rigorous result to present.

---

### P1-4 · Data augmentation — reverberation and clipping ⏱️ 3–5 h

**Why:** PS26052 explicitly lists *"Data augmentation techniques (random noise mixing, reverberation, clipping) are applied to improve generalization."* Already acknowledged as a gap in `data/SOURCES.md` §4.

**Implement in `data/mix_dataset.py`** behind flags (`--augment-rir`, `--augment-clipping`) so the existing 300-mixture baseline remains reproducible:
- **RIR convolution:** use an open RIR corpus (e.g. MIT/OpenSLR RIR sets) to simulate enclosed vehicle cabins, bunkers, and open field — highly defence-relevant.
- **Clipping:** simulate microphone overload, which is *extremely* realistic for gunshot/artillery capture where the transient exceeds the mic's dynamic range. This is a genuinely strong domain-specific argument.

Generate an augmented evaluation set and report robustness alongside the clean-condition numbers.

---

### P1-5 · Targeted fine-tuning for the non-stationary category ⏱️ 6–10 h, high risk

**Why:** non-stationary fails all three targets. This is the only remaining category failure.

**Realistic assessment — read before committing:**
- The **helicopter** subtype already performs excellently (STOI 0.9108, +8.9 dB). There is little to gain there.
- The **crowd babble** subtype is limited by the cocktail-party problem, which is **architectural, not data-limited**. Fine-tuning the same single-channel architecture on more babble may yield modest gains (STOI 0.71 → perhaps 0.75–0.80) but **cannot close the gap**, because the information needed (which voice is the target) is absent at inference time regardless of training.
- The babble pool is only **20 synthetic clips** — thin, with real overfitting risk.
- **Catastrophic-forgetting risk:** naive fine-tuning can degrade your strongest results (+10 to +11 dB on stationary/impulsive). Any run must use balanced data and be re-evaluated across all categories.
- **Infrastructure cost:** DeepFilterNet's training loop needs `libdfdata` — a Rust-compiled HDF5 dataloader **not published on PyPI** — plus dataset conversion to their HDF5 schema and a Rust toolchain. Budget 4–8 h for setup *before* any training begins.

**Recommendation: prefer P1-2 (dual-mic) over P1-5.** Dual-mic attacks the same weakness at its actual root, is cheaper, is explicitly required by the PS, and cannot damage existing results. Pursue fine-tuning only if the schedule is genuinely comfortable.

---

### P1-6 · Presentation deck and backup demo video ⏱️ 4–6 h

**Why:** Day-4 critical path. Currently no deck exists in the repository.

**Suggested narrative arc:**
1. Problem — defence comms fail under gunshot/artillery/rotor noise
2. Why classical DSP is insufficient — **your NLMS −7.10 dB collapse on real gunshot transients is the killer evidence**
3. Approach — DeepFilterNet3, complex-domain, phase-preserving, 48 kHz native
4. Results — the compliance matrix; lead with **impulsive passing all three DRDO targets**
5. Edge deployment — Pi 5, measured RTF, thermals, 10-min zero-dropout gate
6. **Live demo** — BYPASS ⇄ ENHANCE with spectrogram
7. Honest limitations — non-stationary/babble root cause, and the roadmap
8. Round 2 — fine-tuning, dual-mic, quantization

**Backup video is non-negotiable.** Record a full successful demo run (screen + audio) and keep it on the presenting laptop. If the Pi fails to boot, USB enumeration reorders, or the venue is too noisy, you present the video and keep your credibility. **Also prepare pre-recorded before/after audio pairs** from `results/baselines/deepfilternet/` — those work even with no hardware at all.

---

## 6. P2 — Stretch / Round 2 Differentiators

| Item | Value | Cost |
|---|---|---|
| **Full training framework with perceptual loss** (SI-SNR + L1/L2 + perceptual, tuned hyper-parameters) — PS26052 deliverable #3 | High — the only fully unmet deliverable | 12–20 h |
| **Sub-band / full-band feature analysis** — PS mentions models processing "both full-band and sub-band features" | Medium — good technical depth in Q&A | 6–10 h |
| **Speaker-conditioned enhancement** (target-speaker enrollment) — the *actual* solution to crowd babble | Very high — turns a documented limitation into a solved problem | 15–25 h |
| **Jetson AGX Orin comparison** — PS names it as the reference platform | Medium — a Pi-vs-Jetson scaling table is a strong slide | Hardware-dependent |
| **Power consumption measurement** — PS mentions "latency and power constraints" | Medium — cheap with a USB power meter, and nobody else will have it | 2 h |
| **MOS / subjective listening test** — small human panel scoring enhanced samples | Medium-high — complements objective metrics credibly | 4–6 h |

---

## 7. Consolidated Latency Engineering Plan

A single reference for the highest-priority technical work.

### 7.1 Instrument first

Add startup logging to `live/pipeline.py` that prints the **actual** negotiated values rather than the requested ones:
```
[pipeline] input  stream latency: <stream_in.latency> s
[pipeline] output stream latency: <stream_out.latency> s
[pipeline] chunk: <n> samples (<ms> ms) | priming: <k> chunks (<ms> ms)
[pipeline] theoretical standing latency: <sum> ms
```
This makes the budget visible at every run and is itself a good demo artifact.

### 7.2 Make the budget configurable

Promote hardcoded values into `config/audio_config.yaml`:
```yaml
pipeline:
  priming_chunks: 1        # was hardcoded 3
audio:
  chunk_duration_sec: 0.02 # was 0.1
  device_latency_sec: 0.01 # explicit PortAudio hint
```

### 7.3 Sweep, measure, choose

Build `scripts/sweep_chunk_size.py` producing:

| Chunk (ms) | Median RTF | P95 RTF | Dropouts (60 s) | Measured E2E latency |
|---|---|---|---|---|
| 100 | | | | |
| 50 | | | | |
| 20 | | | | |
| 10 | | | | |

**Selection rule:** smallest chunk with **p95 RTF ≤ 0.6** and **0 dropouts over 60 s**. Then confirm with a full 10-minute run.

### 7.4 Report honestly

Final documentation should carry a clean table:

| Quantity | Value | How measured |
|---|---|---|
| Per-chunk model inference (Pi 5) | e.g. 29.18 ms / RTF 0.29 | `live/latency_test.py`, in-memory, 20 reps |
| **End-to-end round-trip latency** | e.g. **~85 ms** | `live/e2e_latency_test.py`, physical loopback, 20 reps |
| Algorithmic lookahead | 0 samples | Cross-correlation, `pad=True` |
| Sustained stability | 0 dropouts / 600 s | `live/stress_test.py`, real microphone |

---

## 8. Demo Day Runbook

### 8.1 Pre-demo checklist (run the morning of)
- [ ] Pi boots, SSH reachable, correct branch checked out
- [ ] `python live/main.py detect` — **confirm device indices still match** the config (USB re-enumeration is the classic demo killer)
- [ ] `python scripts/run_all_selftests.py` — all green
- [ ] 60-second BYPASS run — audible pass-through
- [ ] 60-second ENHANCE run — audible suppression
- [ ] Spectrogram renders in the actual demo terminal
- [ ] Backup video on the presenting laptop, tested
- [ ] Pre-recorded before/after audio pairs loaded and tested
- [ ] Pi power supply is the official 27 W unit (undervoltage throttles CPU and will wreck your RTF)
- [ ] Headphones tested at a comfortable, safe volume

### 8.2 Demo sequence (target ~4 minutes)
1. **Frame it (20 s)** — "Real-time defence speech enhancement on a ₹6,000 Raspberry Pi 5, no cloud, no GPU."
2. **Start in BYPASS (30 s)** — let them hear raw noise. Point at the spectrogram: the whole band is lit up.
3. **Press `b` → ENHANCE (30 s)** — the noise drops out. The spectrogram visibly darkens except the speech band. **This is the moment that wins the round — let the silence sit for a beat before speaking over it.**
4. **Toggle back and forth twice (30 s)** — proves it is live, not pre-recorded.
5. **Show the dashboard (45 s)** — live RTF, CPU %, temperature, 0 dropouts. "It has run 10 minutes continuously without a single dropout at 50 °C."
6. **Quote the measured latency (20 s)** — the honest P0-2 number.
7. **Show the results chart (45 s)** — impulsive passes all three DRDO targets; NLMS collapses at −7.10 dB where DeepFilterNet gains +10.75 dB.
8. **Own the limitation (20 s)** — crowd babble, the cocktail-party problem, and the dual-mic roadmap. **Volunteering a well-understood limitation reads as competence, not weakness.**

### 8.3 Environment hardening
- Test in a **noisy** room beforehand — evaluation venues are loud and echoey
- Watch for **acoustic feedback** (mic hearing the headphones) — keep them separated, or use closed-back headphones
- Have a **wired** network/serial fallback if SSH-over-WiFi fails
- Bring a spare SD card with a known-good image

---

## 9. Risk Register & Contingencies

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **USB device indices reorder on reboot/re-plug** | High | Demo fails | Hardcode indices; re-run `detect` in the pre-demo checklist; consider matching by device *name* with an index fallback |
| **Reducing priming causes underruns** | Medium | Audible glitches | Sweep 1/2/3 chunks; validate each with a 10-min run; keep the working value in git |
| **Small chunks push RTF too high** | Medium | Dropouts | Selection rule p95 RTF ≤ 0.6; fall back one step; ONNX (P1-3) buys margin |
| **Acoustic feedback howl during demo** | Medium | Embarrassing | Closed-back headphones; physical separation; test in-venue; know where the volume control is |
| **Pi undervoltage throttling** | Medium | RTF degrades mid-demo | Official 27 W PSU; watch `vcgencmd get_throttled`; add throttle status to the dashboard |
| **Quantization degrades quality silently** | Medium | Weaker results | Mandatory full re-evaluation vs FP32 before adopting |
| **Fine-tuning breaks strong categories** | High | Loses best results | Prefer dual-mic; if fine-tuning, keep the pretrained checkpoint and re-evaluate all categories |
| **Venue too noisy for live demo** | Medium | Demo unconvincing | Backup video + pre-recorded A/B pairs; closed-back headphones for the evaluator |
| **Zenodo corpus unavailable on a fresh checkout** | Low | Cannot rebuild dataset | Already documented in `data/SOURCES.md` §5 with manual-download instructions; keep the 1.5 GB zip backed up on external media |

---

## 10. Suggested Execution Schedule

Assuming a short runway. **If you do nothing else, do Day 1.**

### Day 1 — Make it genuinely real-time (P0)
| Block | Task |
|---|---|
| Morning | **P0-1** hardware integration + `detect` + hardcode config + verify BYPASS audibly works |
| Midday | **P0-2** build `e2e_latency_test.py`, measure the honest baseline (expect a sobering number) |
| Afternoon | **P0-3** Step 1 (priming 3→1) then Step 2 (chunk sweep); re-measure after each |
| Evening | **P0-4** 10-minute stress test with real mic; **P0-5** spectrogram smoke test |

**End-of-day goal:** a real microphone in, real headphones out, measured end-to-end latency under 150 ms, 0 dropouts over 10 minutes.

### Day 2 — Satisfy explicit PS requirements (P1)
| Block | Task |
|---|---|
| Morning | **P1-3** ONNX export + quantization + **mandatory re-evaluation** |
| Afternoon | **P1-2** dual-mic capture, or **P1-1** LMS residual stage (pick by hardware availability) |
| Evening | **P0-6** documentation correction pass |

### Day 3 — Presentation and rehearsal
| Block | Task |
|---|---|
| Morning | **P1-6** deck |
| Afternoon | **P1-6** backup video + pre-recorded A/B pairs |
| Evening | Full demo rehearsal against the runbook, at least 3 times, including deliberate failure drills |

### Day 4 — Buffer
Reserved deliberately. Something will go wrong. If nothing does, spend it on **P1-4** (augmentation) or additional rehearsal.

---

## 11. Answering Evaluator Questions

Prepared, honest answers to the questions most likely to be asked.

**"What is your end-to-end latency?"**
> Quote the measured P0-2 number, state whether it is round-trip or one-way, and describe the budget breakdown (input block + inference + output block). **Never** quote 29.18 ms here — that is per-chunk inference time, and conflating them is exactly the kind of error a sharp evaluator will catch.

**"Did you train the model yourself?"**
> "Round 1 uses pretrained DeepFilterNet3 deliberately — to establish a rigorous, honestly-measured baseline and identify exactly where it fails before optimizing. We characterized the failure precisely: crowd babble, driven by the cocktail-party problem, which is architectural rather than data-limited. Round 2 targets it with dual-microphone capture rather than blind fine-tuning, because a second spatial channel addresses the actual root cause."

**"Your PESQ misses 2.5 in two categories."**
> "Correct, and we report it rather than averaging it away. Impulsive — the hardest and most defence-critical category — passes all three targets at 2.58. Stationary misses by 0.018. Non-stationary misses by 0.37, driven specifically by crowd babble; helicopter alone scores 0.91 STOI. At operating SNRs of +10 dB and above, the majority of mixtures clear 2.5 in every category, and 100% of stationary mixtures at +15 dB."

**"Why is NLMS worse than doing nothing on gunshots?"**
> "Convergence lag. Gradient-based adaptive filters need time to converge, and a gunshot transient is over before adaptation completes — so the filter is still adapting to the *previous* acoustic state and actively subtracts the wrong thing. We verified this is genuine and not an implementation artifact via zero-lag cross-correlation ablation: peak correlation 1.0000 at 0 samples. Notably, NLMS had an oracle noise reference our deployed system doesn't have — and it still lost 7.10 dB where DeepFilterNet gained 10.75 dB from a single channel."

**"Is this really running on the Pi, not your laptop?"**
> Show the SSH session, `vcgencmd measure_temp`, the live dashboard, and `results/rtf_pi.json` / `stress_test_report.json`. Every Pi claim in this project carries pasted-back hardware evidence under Rule 29 — no benchmark was ever taken from the dev machine and reported as edge performance.

**"What doesn't work?"**
> "Three things. Crowd babble — root-caused to the cocktail-party problem, addressed by dual-mic in Round 2. Non-stationary PESQ. And we have not yet built the full training framework — DeepFilterNet's training path requires a Rust-compiled HDF5 dataloader we scoped at 4–8 hours of setup, which we judged out of Round-1 critical path." *(Answering this crisply and specifically is worth more than pretending everything works.)*

---

## Summary — The Five Things That Matter Most

1. **Measure true end-to-end latency (P0-2).** You are currently quoting the wrong number, and the real one is likely ~530 ms.
2. **Engineer that latency down to < 150 ms (P0-3).** Cut output priming, shrink the chunk. Mostly configuration; enormous payoff.
3. **Put a real microphone on it (P0-1).** The system has never heard an actual sound. PS26052 requires microphone and headset integration.
4. **Re-validate stability with real audio (P0-4)** and smoke-test the spectrogram on the Pi (P0-5).
5. **Then pursue the explicit PS requirements** — ONNX/quantization, dual-mic, LMS residual stage, augmentation — in that order.

Everything upstream of the live pipeline (dataset, baselines, evaluation, compliance reporting) is complete, verified, and honest. **The remaining work is almost entirely about the last few centimetres: microphone in, headphones out, and the milliseconds between them.**

---

*Plan compiled 2026-08-24. Companion document: `summary/01_PROJECT_ACCOMPLISHMENTS.md`. All gap claims traceable to Section 13 of that record.*
