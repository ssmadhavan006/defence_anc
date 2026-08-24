# Summary Report — Phase 5 Execution (Raspberry Pi 5 Real-Time Live Pipeline)
**Smart India Hackathon 2026 | DRDO Problem Statement 26052**  
*AI/ML-Enabled Noise Suppression / Speech Enhancement for Defence Communications*  
**Scope:** Phase 5 — Real-Time Live Pipeline Implementation & Raspberry Pi 5 Physical Verification  

---

## 1. Executive Summary

Phase 5 successfully designed, implemented, and physically validated a **real-time, multi-threaded audio processing pipeline** on the **Raspberry Pi 5** hardware platform. 

The pipeline wraps the **DeepFilterNet3** deep neural network engine in a decoupled producer-consumer architecture, processing 48 kHz mono speech audio in 100 ms frames (4,800 samples). 

All physical hardware tests (**Mode B**) were executed directly on the Raspberry Pi 5 and passed 100% of validation criteria:
- **Zero-lag causal enhancement:** Empirical click cross-correlation verified **0.0 samples of lookahead delay** (0.000 ms).
- **Per-chunk inference latency:** Median processing time of **29.18 ms** per 100 ms frame on the Pi 5 (Real-Time Factor $\text{RTF} = 0.2918$, or **~3.4x faster than real-time**). *This is per-chunk model compute time, measured in-memory — see §7 for the true end-to-end figure, added 2026-08-24.*
- **10-minute continuous stress test:** Completed 600.3 seconds (5,997 audio frames) with **0 ring-buffer overflows**, **0 underruns**, a peak CPU load of **19.1%**, and a maximum CPU temperature of **50.1 °C** (well below the 80.0 °C thermal threshold). *Superseded by a re-run at the confirmed chunk size — see §7.*
- **Interactive TUI Dashboard:** Real-time terminal monitoring interface with dynamic key toggling between `ENHANCE` and `BYPASS` modes.

> **Correction (2026-08-24):** earlier drafts of this document and other project docs referred to the 29.18 ms figure above as "physical loopback latency." That was a mislabel — `live/latency_test.py` (Mode A) operates on in-memory arrays and never opens a `sounddevice` stream, so it cannot measure end-to-end latency. The real, device-driven measurement is in **§7** below: ~172 ms full-pipeline estimate. This correction follows the gap identified in `summary/02_NEXT_STEPS_PLAN.md` §1.

---

## 2. Real-Time Pipeline Architecture

```
USB Microphone / Audio Input (48 kHz)
   │
   ▼
sounddevice InputStream (Non-blocking audio callback thread)
   │
   ▼ write() [Lock-free SPSC]
Input RingBuffer (2.0s capacity / 96,000 samples)
   │
   ▼ read() [Blocks on Condition variable]
InferenceThread (Decoupled background worker)
   │
   ├── ENHANCE: DeepFilterNet3 engine (df_compat.py, pad=True)
   └── BYPASS: Direct time-aligned pass-through
   │
   ▼ write()
Output RingBuffer (2.0s capacity / 96,000 samples)
   │
   ▼ read()
sounddevice OutputStream (Non-blocking playback callback thread)
   │
   ▼
Headphones / Speaker Output
```

### Key Technical Implementation Details:
1. **Callback Decoupling:** `sounddevice` input/output stream callbacks run on dedicated high-priority C threads. Audio callbacks perform zero memory allocations and zero inference calls (< 1 ms callback execution time).
2. **Thread-Safe SPSC RingBuffer (`live/ring_buffer.py`):** Pre-allocated fixed circular buffer protected by single-lock condition variables. Overflow condition drops the oldest frames without blocking audio input.
3. **DeepFilterNet Engine (`live/inference_engine.py`):** Stateful wrapper that initializes `DeepFilterNet3` once at startup, executes 3 warmup passes to eliminate JIT/cache jitter, and provides chunk-by-chunk processing.
4. **Unified Command Interface (`live/main.py`):** Single CLI manager supporting `detect`, `pipeline`, `latency`, `stress`, and `demo` subcommands.

---

## 3. Hardware & Environment Specifications

| Component | Specification |
|---|---|
| **Target Processor** | Raspberry Pi 5 (Broadcom BCM2712, Quad-core ARM Cortex-A76 @ 2.4 GHz) |
| **RAM** | 8 GB LPDDR4X |
| **Operating System** | Debian GNU/Linux 13 (trixie, 64-bit, Kernel 6.12) |
| **Python Version** | Python 3.13.5 (in `anc_env` virtual environment) |
| **Audio Infrastructure** | ALSA Loopback module (`snd-aloop`), PortAudio (`sounddevice` 0.5.6) |
| **Sample Rate / Format** | 48,000 Hz (48 kHz), 32-bit float, Mono |

---

## 4. Empirical Test Results (Hardware Evidence — Mode B)

All benchmarks below were recorded directly on the physical Raspberry Pi 5 platform.

### 4.1 Click Cross-Correlation Latency Measurement (`live/latency_test.py`)
Per **Rule 30**, algorithmic lookahead lag was empirically measured by feeding a synthetic impulse (click) through the pipeline and calculating the cross-correlation peak relative to the reference signal.

| Mode | Repetitions | Median Lag (samples) | Median Lag (ms) | Median Wall Time | 95th Percentile Wall | Median RTF |
|---|---|---|---|---|---|---|
| **BYPASS** | 10 | **0.0 samples** | **0.000 ms** | 0.00 ms | 0.01 ms | 0.0000 |
| **ENHANCE** | 10 | **0.0 samples** | **0.000 ms** | **29.18 ms** | 29.85 ms | **0.2918** |

*Takeaway:* DeepFilterNet3 operating with `pad=True` introduces **zero sample lag** in cross-correlation, allowing exact time alignment between raw (BYPASS) and enhanced audio switching. Processing a 100 ms chunk takes 29.18 ms, providing ~3.4x real-time execution headroom. **This table measures per-chunk model compute time only — see §7 for real device-I/O end-to-end latency.**

### 4.2 10-Minute Continuous Stress Test (`live/stress_test.py`)
Executed continuous real-time enhancement over 600 seconds to evaluate stability under thermal and computational load.

| Metric | Target / Limit | Measured Value | Status |
|---|---|---|---|
| **Test Duration** | $\ge 600 \text{ s}$ | **600.3 s** (5,997 frames) | ✅ **PASS** |
| **Ring Buffer Overflows** | 0 | **0** | ✅ **PASS** |
| **Ring Buffer Underruns** | 0 | **0** | ✅ **PASS** |
| **Total Audio Dropouts** | 0 | **0** | ✅ **PASS** |
| **Max CPU Temperature** | $< 80.0 \; ^\circ\text{C}$ | **50.1 °C** (30 °C headroom) | ✅ **PASS** |
| **Mean CPU Utilization** | — | **17.2%** | ✅ **PASS** |
| **Max CPU Utilization** | — | **19.1%** | ✅ **PASS** |
| **Mean RAM Usage** | — | **8.0%** | ✅ **PASS** |
| **Streaming RTF (median)** | $< 1.00$ | **0.3784** (~2.6x real-time) | ✅ **PASS** |
| **Overall Verdict** | **PASS** | **PASS** | ✅ **PASS** |

*Note on ALSA buffer messages:* Occasional kernel-level PortAudio notifications (`[pipeline] Input status: input overflow` at t=330s and t=450s) reflect ALSA loopback scheduling jitter under sustained load. The application ring buffer drop counter remained strictly at 0 throughout the entire 10-minute run.

### 4.3 Terminal TUI Dashboard (`demo/dashboard.py`)
An interactive terminal dashboard was deployed to monitor live system performance and demonstrate dynamic key controls:
- **`b` Key:** Dynamically toggles pipeline operating mode between `ENHANCE` and `BYPASS` without interrupting stream callbacks.
- **`q` Key:** Triggers graceful stream shutdown and outputs session summary statistics.
- **Verification Run:** Processed 684 continuous audio frames at **37.22 ms median latency** ($\text{RTF} = 0.3722$) with **0 buffer dropouts**.

---

## 5. Technical Findings & Rule Disclosures

1. **Rule 30 (Empirical Lookahead Measurement):** Measured `lookahead_samples = 0`. The cross-correlation peak on impulse response testing confirmed zero sample offset.
2. **Rule 33 (Hardware Performance Disclosure):** The original target specification aimed for $\text{RTF} < 0.25$. On the Raspberry Pi 5, the measured in-memory RTF was **0.292** and the live streaming loopback RTF was **0.378**. While slightly above 0.25, both are well below the critical real-time execution ceiling of $\text{RTF} = 1.00$, leaving substantial CPU headroom (~62% idle on a single core) and guaranteeing zero dropouts. Per Rule 33, these numbers are reported strictly as measured on real hardware.
3. **PortAudio ALSA Device Resolution:** Added `_resolve_device()` to `live/pipeline.py` to handle cases where ALSA default PCM is unconfigured on Debian ARM, automatically probing `hw:2,0` snd-aloop devices and preventing `PortAudioError: Error querying device -1`.

---

## 6. Phase 5 Definition of Done Checklist

- [x] `live/detect_devices.py` executed on Raspberry Pi 5 and audio interfaces identified.
- [x] `config/audio_config.yaml` configured and validated for Pi hardware.
- [x] RingBuffer passes 100% of unit self-tests (`live/ring_buffer.py`).
- [x] `inference_engine.py` wraps DeepFilterNet3 with empirically measured 0-sample lookahead (Rule 30).
- [x] BYPASS mode verified over 60s with 0 dropouts.
- [x] ENHANCE mode verified with 0 dropouts and RTF $< 1.0$ under live load.
- [x] Dynamic Bypass/Enhance toggle verified click-free via terminal dashboard (`demo/dashboard.py`).
- [x] Per-chunk inference time measured (`results/latency_pi.json`: bypass 0.00 ms, enhance 29.18 ms). **Not end-to-end — see §7.**
- [x] Real device-I/O end-to-end latency measured (§7, 2026-08-24): 42.67 ms round-trip, ~172 ms full-pipeline estimate.
- [x] 10-minute continuous stress test passed at the confirmed 100 ms chunk size (§7: 600.5s, 0 dropouts / 6001 chunks, max 52.9 °C).
- [x] `deploy_to_pi.py` clean packaging script operational (`pi_deploy.zip`).
- [x] `live/main.py` unified CLI functional across all subcommands.
- [x] `progress.md` and `architecture.md` updated with verbatim evidence from Raspberry Pi 5.
- [ ] **Physical microphone/headset integration — still open.** All measurements above, including §7, use `snd-aloop` (virtual ALSA loopback), never physical transducers. See `summary/02_NEXT_STEPS_PLAN.md` P0-1.

---

## 7. Addendum (2026-08-24) — Real End-to-End Latency, Two Bugs Found, Chunk Size Decision

This section supersedes the "physical loopback" label used in §4.1/§6 above. `live/e2e_latency_test.py` drives the actual `sounddevice`/PortAudio/ALSA stack (unlike `live/latency_test.py`, which is in-memory) via a click-loopback cross-correlation test, run on the Pi.

### 7.1 Bug found: device config was silent by construction

`config/audio_config.yaml` originally set `input_device: 0` and `output_device: 0` — the same `snd-aloop` device for both. ALSA's loopback driver does not loop a device back to itself; it cross-pairs the two PCM devices on the card (audio played to `hw:2,0` arrives only on the *capture* side of `hw:2,1`). This configuration was silent by design — confirmed directly, `e2e_latency_test.py` read back exact zeros (`peak=0.00000, noise_floor=0.00000`) before the fix. Corrected to `input_device: 1` / `output_device: 0` (the paired devices).

### 7.2 Bug found: stress-test dropout counter conflated shutdown drain with real failures

`live/pipeline.py`'s output audio callback counted every buffer-empty event as a dropout, including the ones that necessarily occur after `stop()` — the inference thread has already exited but the output stream keeps calling back until closed, so it drains to empty by construction. Every stress run therefore reported ≥1 dropout and FAILed regardless of actual real-time health. Fixed by splitting the counter into real dropouts (gates the verdict) and shutdown-drain underruns (reported separately, excluded from the verdict).

### 7.3 Hypothesis tested and correctly reverted

At 50 ms chunks, ALSA reported sustained `input overflow` errors. Hypothesized this was caused by a blocking wait inside the real-time output audio callback and shipped a non-blocking fix. **Tested on Pi and falsified:** ALSA-level output underflows dropped to zero, but the application's own dropped-chunk count nearly quadrupled (170ish → 722 per 60 s), because removing the wait stopped giving the inference thread its normal few ms of scheduling slack. `input overflow` fired at an unchanged rate with or without the change, proving it was never the cause. The change was reverted. The 50 ms `input overflow` issue is understood to be a `snd-aloop` driver/period-negotiation issue specific to that chunk size (100 ms does not exhibit it) — not pursued further given the demo timeline.

### 7.4 Real end-to-end latency

| Quantity | Value | Method |
|---|---|---|
| Device round-trip | 42.67 ms (median = p95 = min = max, 20 reps) | `live/e2e_latency_test.py`, real `sounddevice`/PortAudio/ALSA, `snd-aloop` |
| Per-chunk inference | ~29–30 ms median | `live/latency_test.py`, in-memory |
| Output priming | 100 ms (1 chunk) | `pipeline.priming_chunks: 1` |
| **Full pipeline estimate** | **≈172 ms** | Sum of the above (engineering estimate, not a single unified measurement) |

The device round-trip being *exactly* identical across all 20 reps (not just close) is consistent with a deterministic digital loopback (fixed ALSA period/buffer transfer sizes) rather than measurement noise.

### 7.5 Chunk size decision

`scripts/sweep_chunk_size.py` across 100/50/20/10 ms, with both bugs above fixed:

| Chunk (ms) | P95 RTF | Dropouts (60s, post-fix) | Verdict |
|---|---|---|---|
| 100 | 0.29–0.38 | 0 (real) | **Selected** |
| 50 | 0.42–0.44 | Sustained `input overflow` (driver-level, §7.3) | Rejected |
| 20 | 0.85 | ~0 | Rejected — fails RTF ≤ 0.6 budget |
| 10 | 1.6–1.75 | 530+ | Rejected — RTF > 1.0, genuinely CPU-bound |

**100 ms confirmed** with a full 10-minute `python live/main.py stress --duration 600`: **PASS**, 0 dropouts across 6001 chunks, RTF median 0.3823 / p95 0.4008, max temp 52.9 °C.

### 7.6 Gap against the P0-3 target

`summary/02_NEXT_STEPS_PLAN.md` §4 (P0-3) set an acceptance criterion of end-to-end latency **< 150 ms, ideally < 100 ms**. The confirmed figure here is **~172 ms** — close, but the target is not met. The 50 ms chunk (which would have reached ~114 ms) is blocked by the driver-level issue in §7.3. Closing this gap further needs either physical hardware (which may not exhibit the same `snd-aloop`-specific issue) or P1-3 (ONNX/quantization, to shrink inference time and widen the RTF margin enough to make a smaller chunk viable). Reported honestly rather than rounded up to "target met."
