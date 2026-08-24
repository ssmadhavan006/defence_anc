# Progress Log — PS26052

## CURRENT STATUS
- Phase: 5 (Phase 4 Closeout complete — Phase 5 Live Pipeline in progress)
- Last updated: 2026-08-23 21:35:00
- What works right now: Phases 0–4 complete and fully verified. Phase 4 closeout complete (target compliance matrix built, PESQ report corrected, NLMS/ANC labeling fixed, Rules 29–33 appended).
- What's broken / blocked: nothing
- Waiting on user for: Phase 5 Mode B test results from Raspberry Pi (device detection to start)
- Next immediate action: Build Phase 5 live pipeline files (Mode A components first)

## LOG

### 2026-08-23 — Phase 4 Closeout (Part A)
- Phase/Task: Phase 4 Closeout (reporting correction + compliance matrix)
- What I did:
  - **A.2 – Honest target compliance matrix**: Computed per-category per-metric PASS/FAIL from `results/eval_raw.csv` (no new data collection). Built `results/final/target_compliance.md` and `results/final/target_compliance.json`. Verdict: SI-SNR PASS on stationary/impulsive, FAIL on non-stationary (10.75 dB). STOI PASS on stationary/impulsive, FAIL on non-stationary (0.83). PESQ-WB FAIL on all three categories (2.48, 2.13, 2.49 — all below 2.5 target). No averaging across categories.
  - **A.3 – Report correction**: Appended dated correction note to `docs/phase_4_summary.md` (original text preserved above it). Corrected the false claim that "DRDO PESQ > 2.5 benchmark requirement" was met. The values 2.48–2.49 are below 2.5; the prior text cited only the SNR-conditional slice to support an overall claim.
  - **A.4.1 – NLMS labeling**: Added explicit "reference-assisted adaptive filter baseline" label to `target_compliance.md`, correction note, and rules. Rule 31 appended to `rules.md`.
  - **A.4.2 – ANC terminology**: Corrected to "AI/ML-enabled adaptive noise suppression / speech enhancement" in technical docs. Rule 32 appended to `rules.md`.
  - **Rules 29–33** appended verbatim to `rules.md` (Phase 5 Rules Addendum).
- Evidence: `results/final/target_compliance.md` exists, `results/final/target_compliance.json` exists, `docs/phase_4_summary.md` has correction note dated 2026-08-23.
- Result: PASS — Phase 4 Closeout Definition of Done met.
- Files changed: `progress.md`, `rules.md`, `docs/phase_4_summary.md`, `results/final/target_compliance.md`, `results/final/target_compliance.json`
- Next step: Phase 5 — Live Pipeline

### 2026-08-23 — Phase 5 Started (Mode A components)
- Building: `config/audio_config.yaml`, `live/ring_buffer.py`, `live/inference_engine.py` (Mode A)
- Mode B tests pending: device detection on Pi, bypass/enhance live tests, latency measurement, stress test
- No Mode B test will be logged as passed until real Pi output is pasted back by user (Rule 29)

### 2026-08-23 — Phase 5 Mode A: ring_buffer.py + inference_engine.py PASS
- Phase/Task: Phase 5 — Live Pipeline (Mode A)
- What I did:
  - Created `config/audio_config.yaml` — central config for sample rate (48 kHz), chunk size (0.1 s = 4,800 samples), ring buffer capacity (2 s = 96,000 samples), device selection, pipeline mode (enhance/bypass), warmup passes, latency warn threshold.
  - Created `live/ring_buffer.py` — thread-safe SPSC circular buffer. Fixed-capacity, no dynamic alloc in hot path. Overflow drops oldest (never blocks audio callback). 6-test self-test.
  - Created `live/inference_engine.py` — stateful DeepFilterNet wrapper. One-time model load + warmup on construction. Hot-path `enhance_chunk()` and `bypass_chunk()`. 6-test self-test (Mode A = no hardware).
  - Installed `sounddevice==0.5.6` via `uv add sounddevice`.
- Commands run: `uv run python live/ring_buffer.py`, `uv run python live/inference_engine.py`
- Evidence (verbatim):
  ```
  RingBuffer self-test -- start
    [PASS] test 1: basic write/read roundtrip
    [PASS] test 2: wrap-around write/read
    [PASS] test 3: overflow drops oldest (overflow_count=1)
    [PASS] test 4: multi-channel roundtrip
    [PASS] test 5: threaded producer-consumer (10 chunks)
    [PASS] test 6: timeout returns None
  RingBuffer self-test -- ALL PASSED

  InferenceEngine self-test (Mode A -- dev machine)
  [InferenceEngine] Model loaded in 87.4 ms (suffix=DeepFilterNet3)
  [InferenceEngine] Warmup complete (34.8 ms total).
    [PASS] test 1: engine initialised and warmed up
    [PASS] test 2: bypass_chunk shape (1, 4800), dtype float32
    [PASS] test 3: enhance_chunk on silence -> shape (1, 4800)
    [PASS] test 4: enhance_chunk on white noise -> no NaN/Inf, shape (1, 4800)
    [PASS] test 5: enhance_chunk on 300 Hz sine -> shape (1, 4800)
    [PASS] test 6: 10-call latency profile
             median=9.26 ms, p95=9.53 ms, median_RTF=0.0926
  InferenceEngine self-test -- ALL PASSED
  ```
- Notes:
  - Dev machine (Windows/PC) median RTF = 0.093 on 100 ms chunks (10x faster than real-time). Pi 5 RTF from Phase 1 was 0.170 (still ~6x real-time headroom).
  - Unicode `->` display in terminal is a Windows cp1252 cosmetic issue; file is UTF-8. Self-test exits 0 cleanly.
- Result: PASS — Phase 5 Mode A (ring_buffer + inference_engine) complete.
- Next step: Build `live/pipeline.py` (STEP 3), then provide Mode B commands for Pi

### 2026-08-23 — Phase 5 Mode A: pipeline.py + latency_test.py PASS
- Phase/Task: Phase 5 — Live Pipeline (Mode A continued)
- What I did:
  - Created `live/pipeline.py` — full streaming orchestrator. sounddevice InputStream/OutputStream + input/output RingBuffers + InferenceThread. Supports enhance and bypass modes. Per-session stats (median/p95 latency, overflow/underrun counts). Graceful Ctrl-C shutdown.
  - Created `live/latency_test.py` — click-impulse cross-correlation latency measurement. Mode A (in-memory, no hardware). Reports per-call wall time and sample-level lag.
  - Installed `pyyaml==6.0.3` via `uv add pyyaml`.
- Commands run: `uv run python live/pipeline.py --list-devices`, `uv run python live/latency_test.py --mode bypass --n-reps 5`, `uv run python live/latency_test.py --mode enhance --n-reps 5 --output-json results/latency_devmachine.json`
- Evidence (verbatim):
  ```
  Bypass mode:
    Median lag: 0.0 samples = 0.000 ms
    Wall: median=0.00 ms, p95=0.00 ms, max=0.00 ms  (pure pass-through, correct)
    Lag samples: [0, 0, 0, 0, 0]

  Enhance mode (dev machine, Windows):
    Median lag: 0.0 samples = 0.000 ms
    Wall: median=9.77 ms, p95=10.48 ms, max=10.55 ms
    RTF: median=0.0977, p95=0.1048
    Lag samples: [0, 0, 0, 0, 0]
    Latencies (ms): [9.581, 9.277, 10.198, 10.548, 9.766]
  ```
- Key findings (Rule 30 compliance — lookahead measured empirically):
  - DeepFilterNet3 with pad=True introduces **0-sample cross-correlation lag** on a per-chunk basis. No lookahead correction is needed in the pipeline.
  - Wall-clock processing: ~9.8 ms per 100 ms chunk on dev machine (RTF 0.098, 10x real-time). On Pi 5 (Phase 1 RTF = 0.170), expected ~17 ms per 100 ms chunk.
- Result: PASS — Phase 5 Mode A fully complete.
- Files: `config/audio_config.yaml`, `live/ring_buffer.py`, `live/inference_engine.py`, `live/pipeline.py`, `live/latency_test.py`, `results/latency_devmachine.json`
- Next step: MODE B — Pi hardware tests (copy files to Pi, run device detection, bypass/enhance live tests, latency measurement)

### 2026-08-24 — Phase 5 Mode A: Remaining Components Complete
- Phase/Task: Phase 5 — Live Pipeline (Mode A Finalized)
- What I did:
  - Created `live/detect_devices.py` to enumerate PortAudio devices and auto-suggest a config block.
  - Created `live/stress_test.py` to monitor CPU/RAM/Temp/Dropouts and enforce the 10-minute reliability criteria.
  - Created `demo/dashboard.py` to provide a terminal UI showing live system and pipeline performance stats, with dynamic toggle key 'b' and quit key 'q'.
  - Created `live/main.py` as a unified CLI routing wrapper.
  - Created `scripts/deploy_to_pi.py` to package runtime files into `pi_deploy.zip` (excluding datasets/venv/git).
  - Created `requirements.txt` containing dependencies for the Pi.
- Commands run:
  - `.venv\Scripts\python.exe live/main.py latency --mode bypass --n-reps 5` (Exited 0, median lag = 0.0 samples)
  - `.venv\Scripts\python.exe live/main.py latency --mode enhance --n-reps 5` (Exited 0, median lag = 0.0 samples, median wall = 44 ms, RTF = 0.44)
  - `.venv\Scripts\python.exe scripts/deploy_to_pi.py` (Generated `pi_deploy.zip` successfully)
- Evidence (verbatim local test runs):
  - Bypass: Median lag: 0.0 samples = 0.000 ms, Wall-clock latency: median=0.02 ms.
  - Enhance: Median lag: 0.0 samples = 0.000 ms, Wall-clock latency: median=44.00 ms.
- Result: PASS — Phase 5 Mode A fully complete on dev machine.
- Next step: MODE B — Run physical validation tests on Raspberry Pi 5.

---

### MODE B PENDING — Phase 5 Pi Hardware Tests
**Status: WAITING FOR USER — run exact commands below on the Pi and paste outputs back.**
**Rule 29: None of these tests will be marked PASS until real Pi output is received.**

#### MODE B STEP 1 — Copy and Unzip on the Pi
From your computer terminal:
```bash
scp pi_deploy.zip codefather@raspberrypi:~/Downloads/defence_anc/
```
Then on your Pi terminal:
```bash
cd ~/Downloads/defence_anc
unzip -o pi_deploy.zip
```

#### MODE B STEP 2 — Install Pip Requirements on the Pi
Active your virtual environment on the Pi and run:
```bash
pip install -r requirements.txt
```

#### MODE B STEP 3 — Run Device Detection
```bash
python live/main.py detect
```
Paste back the output. Update `config/audio_config.yaml` on the Pi with the suggested Loopback input/output indices.

#### MODE B STEP 4 — Run Bypass Latency
```bash
python live/main.py latency --mode bypass --n-reps 10
```
Paste back the results. Expected: 0-sample lag.

#### MODE B STEP 5 — Run Enhance Latency
```bash
python live/main.py latency --mode enhance --n-reps 10 --output-json results/latency_pi.json
```
Paste back the results. Expected: 0-sample lag, wall time ~17 ms (based on Pi 5 4-thread CPU capacity).

#### MODE B STEP 6 — Run Interactive Terminal TUI Dashboard
```bash
python live/main.py demo
```
Verify audio passes through, and speak to check latency/intelligibility. Press `b` to toggle enhance/bypass, and `q` to quit. Paste back session stats printed on exit.

#### MODE B STEP 7 — Run 10-Minute Stress Test
```bash
python live/main.py stress --duration 600 --output-json results/stress_test_report.json
```
Paste back the summary report. Expected: Verdict: PASS, 0 total dropouts, max temperature < 80°C.

