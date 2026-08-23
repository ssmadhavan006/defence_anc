# Summary Report — Phase 0 & Phase 1 Execution
**Smart India Hackathon 2026 | DRDO Problem Statement 26052**  
*AI/ML-Enabled Adaptive Noise Cancellation (ANC) for Defence Communications*  
**Deployment Target:** Raspberry Pi 5 Edge System  

---

## 1. Executive Summary

The objective of **PS26052** is to build a real-time AI/ML-enabled Adaptive Noise Cancellation (ANC) system capable of suppressing intense defence noise (stationary engine hums, non-stationary vehicle/helicopter rotor noise, and impulsive gunshot/artillery noise) while preserving high speech intelligibility (`SNR > 15 dB`, `STOI > 0.85`, `PESQ > 2.5`) on edge hardware.

This report summarizes **Phase 0 (Repository & Environment Setup)** and **Phase 1 (DeepFilterNet Baseline & Edge RTF Benchmarking)**. All software components were developed on the development computer and benchmarked directly on the target **Raspberry Pi 5** hardware.

---

## 2. Phase 0 — Repository & Memory System Architecture

### 2.1 Two-Machine Operational Model
- **COMPUTER (Development Lab):** Dataset synthesis, DSP baseline development, metric evaluation engine, DeepFilterNet packaging, and model fine-tuning.
- **RASPBERRY PI 5 (Edge Deployment Target):** Quad-core ARM Cortex-A76 @ 2.4GHz running Debian GNU/Linux 13 (trixie 13.6). Serves as the product runtime platform.

### 2.2 Persistent Memory Files
Three external memory documents were established to preserve context and maintain strict engineering discipline:
1. `progress.md`: Live status header and append-only chronological log with empirical command evidence for every completed task.
2. `rules.md`: Strict rules governing anti-hallucination, mandatory command output validation, and scope discipline.
3. `architecture.md`: Living repository structure, Mermaid data flow diagrams, component matrix, and dated decisions log.

### 2.3 Verified Environment Specs
- **Computer Stack:** Python `3.9.25` virtual environment managed via `uv`, PyTorch `2.5.1`, `deepfilternet` `0.5.6`.
- **Raspberry Pi 5 Stack:** Python `3.13.5`, PyTorch `2.6+` CPU-only build, `soundfile`, `sounddevice`.

---

## 3. Phase 1 — DeepFilterNet Baseline & Software Engineering

### 3.1 Model Selection
- **Model Core:** Pretrained **DeepFilterNet3** operating natively at **48,000 Hz** (48 kHz).
- **Architecture:** Multi-stage deep filtering using ERB-scale complex spectrogram filtering combined with deep neural feature extraction.

### 3.2 Key Software Components
1. **Universal Compatibility Polyfill (`models/deepfilternet/df_compat.py`)**:
   - Solved PyTorch 2.6+ / Python 3.13 deprecations on Linux/Raspberry Pi (`ModuleNotFoundError: No module named 'torchaudio.backend'` and `ImportError: TorchCodec is required for load_with_torchcodec`).
   - Overrode `df.io.load_audio`, `df.io.save_audio`, `torchaudio.load`, `torchaudio.save`, and `torchaudio.info` with pure `soundfile` + `torch` implementations, completely isolating the audio I/O pipeline.
2. **Automated Batch Inference Engine (`models/deepfilternet/run_inference.py`)**:
   - Batch-processes directory trees of `.wav` audio files.
   - Includes an internal assertion self-test verifying output sample rates (48 kHz), output existence, and duration preservation.
3. **Edge Benchmark Suite (`models/deepfilternet/benchmark_rtf.py`)**:
   - Implements the strict 20-run benchmarking protocol (3 warmup runs discarded, 17 measured runs).
   - Computes median and 95th-percentile (p95) latency and Real-Time Factor (RTF).
   - Measures performance under both single-thread and 4-thread PyTorch execution modes.
   - Tracks CPU temperature before and after execution via `/sys/class/thermal/thermal_zone0/temp` and `vcgencmd`.

---

## 4. Empirical Raspberry Pi 5 Benchmark Results

The benchmark was executed directly on the **Raspberry Pi 5** using a 3.0-second 48 kHz synthetic speech-plus-noise mixture (`data/mixtures/noisy.wav`).

### 4.1 Benchmark Metrics Summary

| Parameter | Single-Thread (1 Core) | Multi-Thread (4 Cores) | Unit / Impact |
|---|---|---|---|
| **Audio Frame Duration** | `3.00` | `3.00` | seconds |
| **Sample Rate** | `48,000` | `48,000` | Hz (Native) |
| **Median Processing Latency** | `660.98` | **`511.10`** | milliseconds |
| **P95 Processing Latency** | `702.76` | **`545.57`** | milliseconds |
| **Median Real-Time Factor (RTF)** | `0.22033` | **`0.17037`** | ratio (lower is better) |
| **P95 Real-Time Factor (RTF)** | `0.23425` | **`0.18186`** | ratio |
| **Real-Time Execution Speedup** | `~4.5x` | **`~5.8x`** | **x real-time** |
| **CPU Temperature Range** | `41.1 → 45.0` | `43.9 → 47.2` | °C (No thermal throttling) |

### 4.2 Key Performance Findings
- **Real-Time Headroom:** At **RTF = 0.17037** on 4 threads, 1 second of 48 kHz audio requires only **~170 ms** of CPU time to enhance. This provides a **5.8x computational headroom**, proving that real-time live streaming ANC on the Raspberry Pi 5 is fully viable.
- **Thermal Behavior:** Under sustained 4-thread neural inference, CPU temperature rose slightly from 43.9°C to 47.2°C, remaining far below the Pi 5 thermal throttling threshold (80°C).

---

## 5. Phase 0 & Phase 1 Definition of Done Checklist

| Requirement / Milestone | Status | Validation Evidence |
|---|---|---|
| Repository tree matching specification | **PASSED** | Folder structure initialized with `.gitkeep` placeholders |
| Persistent memory files created & updated | **PASSED** | `progress.md`, `rules.md`, `architecture.md` online and up to date |
| Computer virtual environment operational | **PASSED** | `uv` venv running Python 3.9.25 with PyTorch & DeepFilterNet3 |
| Pi 5 OS & hardware environment confirmed | **PASSED** | Debian 13 trixie, Python 3.13.5, dual HDMI audio hardware logged |
| Enhanced audio produced on Computer | **PASSED** | `noisy_DeepFilterNet3.wav` generated and verified (48 kHz) |
| Batch inference engine operational | **PASSED** | `run_inference.py --self-test` passed with 0 errors |
| DeepFilterNet installed on Pi 5 | **PASSED** | End-to-end inference confirmed working on Pi 5 |
| Empirical Pi 5 RTF measured on Pi | **PASSED** | `results/rtf_pi.json` recorded (Median RTF: 0.17037) |
| Zero PC benchmarks mislabeled as Pi results | **PASSED** | PC (`rtf_computer.json`) and Pi (`rtf_pi.json`) explicitly separated |

---

## 6. Next Steps & Roadmap

With Phase 0 and Phase 1 complete, the project is ready to enter **Phase 2**:
1. **Defence Noise Dataset Synthesis**: Generating mixed clean speech + defence noise datasets (impulsive gunshots/explosions, non-stationary rotor hums, engine noise).
2. **DSP Baseline Engine Implementation**: Building classical filters (Spectral Subtraction, Wiener Filter, NLMS adaptive filter) in `baselines/`.
3. **Objective Metrics Evaluation Suite**: Implementing PESQ, STOI, and SI-SNR calculation pipeline in `eval/` to benchmark DeepFilterNet against classical baselines.
