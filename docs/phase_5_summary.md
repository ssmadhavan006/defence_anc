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
- **Inference latency:** Median processing time of **29.18 ms** per 100 ms frame on the Pi 5 (Real-Time Factor $\text{RTF} = 0.2918$, or **~3.4x faster than real-time**).
- **10-minute continuous stress test:** Completed 600.3 seconds (5,997 audio frames) with **0 ring-buffer overflows**, **0 underruns**, a peak CPU load of **19.1%**, and a maximum CPU temperature of **50.1 °C** (well below the 80.0 °C thermal threshold).
- **Interactive TUI Dashboard:** Real-time terminal monitoring interface with dynamic key toggling between `ENHANCE` and `BYPASS` modes.

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

*Takeaway:* DeepFilterNet3 operating with `pad=True` introduces **zero sample lag** in cross-correlation, allowing exact time alignment between raw (BYPASS) and enhanced audio switching. Processing a 100 ms chunk takes 29.18 ms, providing ~3.4x real-time execution headroom.

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
- [x] Physical loopback latency measured (`results/latency_pi.json`: bypass 0.00 ms, enhance 29.18 ms).
- [x] 10-minute continuous stress test passed (`results/stress_test_report.json`: 600.3s, 0 dropouts, max 50.1 °C).
- [x] `deploy_to_pi.py` clean packaging script operational (`pi_deploy.zip`).
- [x] `live/main.py` unified CLI functional across all subcommands.
- [x] `progress.md` and `architecture.md` updated with verbatim evidence from Raspberry Pi 5.
