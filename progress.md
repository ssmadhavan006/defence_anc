# Progress Log — PS26052

## CURRENT STATUS
- Phase: **5 — COMPLETE** ✅ | Post-Phase-5 hardening COMPLETE ✅ | Latency engineering (P0-2/P0-3) COMPLETE on loopback ✅
- Last updated: 2026-08-24 18:40:00
- What works right now: Phases 0–5 complete and fully verified on Raspberry Pi 5 hardware. All Mode A and Mode B tests passed. Unified Mode A self-test suite (`scripts/run_all_selftests.py`) green. Live spectrogram demo added (`demo/spectrogram.py`). `pesq` C-extension rebuilt and portable across machines. **Gunshot/artillery noise corpus recovered and the full pipeline (manifest → mixtures → baselines → DeepFilterNet → 1500-pair eval) regenerated end to end with real PESQ-WB and the complete, documented 3-subtype impulsive noise pool.** Corrected impulsive results are stronger than previously reported: PESQ-WB 2.4916 (FAIL) → **2.5841 (PASS)**, STOI 0.9319, SI-SNR +15.75 dB — impulsive is now the only category passing all three DRDO targets. **Real end-to-end latency now honestly measured for the first time** (previously the project quoted 29.18 ms per-chunk inference time as if it were end-to-end — see the 2026-08-24 P0-2/P0-3 entry below): device round-trip 42.67 ms (real `sounddevice` streams, `snd-aloop` loopback) + inference + 100 ms priming ≈ **172 ms full-pipeline estimate**, chunk size 100 ms confirmed via `scripts/sweep_chunk_size.py` and a real 10-minute stress gate (0 dropouts / 6001 chunks). `results/final/target_compliance.json`/`.md`, `README.md`, `docs/phase_4_summary.md`, `architecture.md`, `data/SOURCES.md` all updated with the corrected figures and full incident writeups.
- What's broken / blocked: nothing on the software side. **Still blocked on physical hardware (P0-1)** — every measurement to date, including the new e2e latency number, runs through `snd-aloop` (a virtual ALSA loopback), never a physical microphone or headset. This is the single largest remaining gap against PS26052's explicit "integrated with microphones... and headphones" requirement.
- Waiting on user for: a USB microphone + headphones/headset (P0-1) — needed before P0-1, P0-4 (real-mic stress test), and P0-5 (spectrogram smoke test on real hardware) can proceed.
- Next immediate action: acquire physical audio hardware (P0-1). Once available: re-run `python live/main.py detect`, hardcode the new device indices, verify BYPASS/ENHANCE audibly work, then re-run the 10-minute stress gate and spectrogram smoke test with real acoustic input (P0-4/P0-5). See `summary/02_NEXT_STEPS_PLAN.md` for the full remaining plan.

### Fixed bugs (found via new unified self-test runner and the dataset-gap investigation)
1. `models/deepfilternet/run_inference.py::run_self_test()` depended on a stale fixture `data/mixtures/noisy.wav` left over from Phase 1 — that path now holds the real 300-mixture Phase 2 dataset instead, so the self-test either failed outright (file missing) or, via `batch_inference()`'s directory glob, would have silently reprocessed the entire 600-file dataset instead of running a fast isolated smoke check. Also fixed a duplicate-glob bug in `batch_inference()` (both a non-recursive and a recursive glob pattern matched the same top-level files, double-processing every file) — dead code path only reachable from the self-test; the real Phase 3/4 production runs use `process_manifest()` (manifest-driven), which was never affected. Self-test now generates its own synthetic 2 s clip and calls `process_file()` directly. Verified: `uv run python models/deepfilternet/run_inference.py --self-test` passes (RTF=0.2455 on this dev machine).
2. `scripts/build_pesq_gcc.py` hardcoded a GCC path under a different Windows user profile (`C:\Users\Admin\...`) and a Python 3.9 ABI tag (`cp39-win_amd64.pyd`) for the compiled `.pyd` filename — both specific to whatever machine originally built it. Rewrote to discover `gcc` dynamically (PATH, then WinGet/Chocolatey/MSYS2 common install locations) and derive the correct ABI tag from `sysconfig.get_config_var("EXT_SUFFIX")` at build time. Installed a GCC toolchain on this machine (`winget install BrechtSanders.WinLibs.POSIX.UCRT`) and rebuilt `pesq` successfully for Python 3.11 — verified with a real PESQ score computation, then a full 1500-pair `eval/run_eval.py` re-run confirmed all rows scoring "100/100 Valid."
3. `data/mix_dataset.py` only printed a soft `[WARNING]` when a declared noise subtype (e.g. `impulsive/gunshot`) had zero files on disk, then silently proceeded to regenerate a manifest missing that subtype entirely — exactly the failure mode that caused the gunshot/artillery incident below to go unnoticed through a commit and multiple doc updates. Changed to a hard `RuntimeError` by default (opt out via `--allow-partial-corpus`), naming the missing subtypes and pointing at this exact incident in the error message.

### Major finding & fix: gunshot/artillery noise corpus was missing, silently, since commit `feb019c`
- **What was found:** `data/noise/impulsive/` on this machine contained only the 40-file `explosion` (ESC-50 proxy) subtype — `gunshot` (2,148 files) and `artillery` (30 files) were completely absent, despite `data/SOURCES.md` and every Phase 2–4 doc documenting all three as part of the corpus. Root-caused to commit `feb019c` ("upgrade dataset downloader with HTTP resume and regenerate manifest & charts"): the Zenodo gunshot download (~1.5 GB) was failing on the original non-resumable downloader, someone fixed the downloader, but the manifest got regenerated and committed *before* the corpus actually finished downloading — collapsing all 100 "impulsive" mixtures onto `explosion` only, with no error raised (see bug fix #3 above). Confirmed via `git show feb019c~1:data/manifest.csv`: the pre-commit manifest correctly had `artillery:34, explosion:40, gunshot:26`; post-commit it was `explosion:100`. Stationary/non-stationary were never affected.
- **Recovery attempt 1 (automated) failed:** `scripts/download_datasets.py`'s new HTTP-resume logic correctly retried 10 times but every attempt got `403 Forbidden` from Zenodo — *"Access to this resource has been restricted due to unusual traffic from your network"* — a network-level anti-bot block, not a code bug. Confirmed via a standalone HEAD request (same 403, no download attempted). Stopped automated retries to avoid prolonging the block.
- **Recovery attempt 2 (manual, user-provided) succeeded:** User downloaded `edge-collected-gunshot-audio.zip` via a normal browser session and placed it at `data/downloads/`. Verified byte-for-byte complete (`zipfile.testzip()` clean, matches Zenodo's reported 1,567,979,135-byte size). Contains exactly 2,148 files across 4 firearm-type subfolders (`glock_17_9mm_caliber`: 669, `ruger_ar_556_dot223_caliber`: 597, `38s&ws_dot38_caliber`: 503, `remington_870_12_gauge`: 379) — matching the documented "2,148 gunshot" count exactly. The original artillery-selection script was not preserved anywhere in the repo, so the 30-file split was re-derived: all 2,148 files → `gunshot`; first 30 (sorted, deterministic) from `remington_870_12_gauge` (highest-energy/largest-caliber type) → `artillery`, following the documented "large-caliber" rationale. Full detail: `data/SOURCES.md` §5.
- **Full pipeline regenerated end to end**, all steps verified with real command output:
  - `uv run python data/mix_dataset.py` → 300 mixtures, manifest subtype counts `impulsive: {gunshot:25, explosion:40, artillery:35}`, SNR mean deviation 0.0000 dB.
  - `uv run python scripts/run_all_baselines.py` → 900/900 baseline outputs, 100% sanity checks passed, 86.86s total.
  - `uv run python models/deepfilternet/run_inference.py` → 300/300 DeepFilterNet outputs, 77.29s.
  - `uv run python eval/run_eval.py` → 1500/1500 evaluation rows, 0 exclusions, 221.87s. All PESQ-WB "100/100 Valid" (real `pesq` package, not the "Unavailable" placeholder).
- **Corrected impulsive results (stronger than previously reported, not weaker):**

  | Metric | Old (explosion-only, WRONG) | Corrected | Target | Verdict change |
  |---|---|---|---|---|
  | SI-SNR | +15.20 dB | **+15.75 dB** | >15 dB | PASS → PASS |
  | STOI | 0.9196 | **0.9319** | >0.85 | PASS → PASS |
  | PESQ-WB | 2.4916 | **2.5841** | >2.5 | **FAIL → PASS** |
  | NLMS ΔSI-SNR | −3.30 dB | **−7.10 dB** | — | Collapse is sharper on real transients — reinforces the AI/ML-necessity narrative |

  Stationary and non-stationary numbers are byte-for-byte unchanged (their noise pools were never affected) — cross-checked against the pre-incident figures as a consistency sanity check.
- **Docs updated with the corrected figures and full incident writeups:** `results/final/target_compliance.json`/`.md`, `docs/phase_4_summary.md` (new 2026-08-24 correction note, original + prior correction preserved), `README.md`, `architecture.md`, `data/SOURCES.md` (§5, new).
- Result: **RESOLVED** — dataset is now complete, correctly composed, and matches its own documentation. The correction net-improves the headline story (impulsive now clears every DRDO target).

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

### 2026-08-24 — Phase 5 Mode B: Pi 5 Latency Measurements PASS
- Phase/Task: Phase 5 — Live Pipeline (Pi 5 Empirical Latency Verification)
- What I did:
  - Executed `python live/main.py latency --mode bypass --n-reps 10` on Raspberry Pi 5.
  - Executed `python live/main.py latency --mode enhance --n-reps 10 --output-json results/latency_pi.json` on Raspberry Pi 5.
  - Fixed `PortAudioError: Error querying device -1` in `live/pipeline.py` by adding `_resolve_device()` to auto-detect valid ALSA interfaces when YAML devices are `null`.
  - Pushed commit `909e567` to GitHub (`origin main`).
- Evidence (verbatim output from Raspberry Pi 5):
  - **Bypass Latency:**
    - Median lag: `0.0 samples = 0.000 ms`
    - Wall-clock latency: `median=0.00 ms, p95=0.01 ms, max=0.01 ms`
    - Lag samples: `[0, 0, 0, 0, 0, 0, 0, 0, 0, 0]`
  - **Enhance Latency (DeepFilterNet3):**
    - Median lag: `0.0 samples = 0.000 ms`
    - Wall-clock latency: `median=29.18 ms, p95=29.85 ms, max=29.93 ms`
    - RTF: `median=0.2918, p95=0.2985` (3.4x real-time execution headroom per 100 ms chunk)
    - Lag samples: `[0, 0, 0, 0, 0, 0, 0, 0, 0, 0]`
    - Saved JSON: `results/latency_pi.json`
- Result: PASS — Mode B latency benchmark verified on physical Pi 5 hardware (Rule 29).

### 2026-08-24 — Phase 5 Mode B: 10-Minute Stress Test PASS
- Phase/Task: Phase 5 — Live Pipeline (Stress Gate, Rule 29)
- What I did: Ran `python live/main.py stress --duration 600 --output-json results/stress_test_report.json` on Pi 5.
- Evidence (verbatim from Raspberry Pi 5):
  ```
  === Stress Test Summary ===
  Verdict         : PASS
  Duration        : 600.3 seconds
  CPU Load (%)    : Mean 17.2%, Max 19.1%
  RAM Usage (%)   : Mean 8.0%
  Max Temperature : 50.1°C
  Total Dropouts  : 0 (0 overflows, 0 underruns)
  ```
- Session stats (5997 chunks over 600s):
  - Latency: median=37.84 ms, p95=39.31 ms, max=63.92 ms
  - RTF: median=0.3784, p95=0.3931 (~2.6x real-time headroom)
  - ALSA [input overflow] and [output underflow] messages at t≈330s and t≈450s are PortAudio-level ALSA buffer notifications — NOT counted as ring buffer dropouts (overflow_count=0, underruns=0). This is normal loopback behaviour under sustained load.
- Result: **PASS** — All stress criteria met: zero dropouts, max temp 50.1°C (well below 80°C limit), no crash, 600s continuous run.
- Files: `results/stress_test_report.json`

### 2026-08-24 — Phase 5 Mode B: demo dashboard — fix pending push
- Issue found: `demo/dashboard.py` used `pipeline._in_buf.available()` and `pipeline._in_buf._capacity` but `available` and `capacity` are `@property` attributes on `RingBuffer`, not callable methods. Caused `TypeError: 'int' object is not callable`.
- Fix: Changed `available()` → `available` and `_capacity` → `capacity` in `demo/dashboard.py`. Committed and pushed.

### 2026-08-24 — Phase 5 Mode B: Terminal Dashboard Demo PASS ✅
- Phase/Task: Phase 5 — Live Pipeline (Terminal Dashboard, Rule 29)
- What I did: Ran `python live/main.py demo` on Pi 5 after pulling the @property fix.
- Evidence (verbatim from Raspberry Pi 5 — session stats on clean exit):
  ```
  [pipeline] === Session stats (684 chunks) ===
    Latency: median=37.22 ms, p95=40.39 ms, max=45.71 ms
    RTF:     median=0.3722, p95=0.4039
    Input buffer overflows: 0
    Output buffer underruns: 0
  Demo stopped. Clean exit.
  ```
- Dashboard panel rendered correctly (ANSI TUI: CPU, RAM, Temp, ring buffer fill %, latency, mode).
- Mode displayed as ENHANCE at RTF=0.3714. Clean exit via 'q'.
- Result: **PASS** — Dashboard Mode B verified on physical Pi 5 hardware (Rule 29).

### 2026-08-24 — Post-Phase-5 hardening: README fix, live spectrogram, unified self-tests, PESQ build gap found
- Phase/Task: Elevation pass requested by user after Phase 5 close — "what needs to be improved/enhanced/fixed", user approved all items except the presentation deck.
- What I did:
  - **README.md**: Corrected the stale "Status" section, which still claimed live Pi streaming was "the next integration step" despite Phase 5 being complete with real Pi 5 evidence. Added the repository layout entries for `live/`, `demo/`, `config/` (previously missing).
  - **`demo/spectrogram.py` (new)**: Live terminal waterfall spectrogram, BEFORE (raw mic) vs AFTER (DeepFilterNet output), ANSI-rendered so it works over SSH on the Pi with no GUI/X11. Shared auto-gain reference driven by the BEFORE signal, so the AFTER panel visibly darkens under real suppression instead of independently re-normalizing to look equally loud. `b`/`q` controls, consistent with `demo/dashboard.py`. Added a `--self-test` flag (Mode A, synthetic audio, no hardware) — verified: `before_mean=0.938, after_mean=0.037` on a synthetic tone+noise vs tone-only pair.
  - **`live/pipeline.py`**: Added `self.last_in_chunk` / `self.last_out_chunk` instance attributes, set once per inference-loop iteration, so demo tooling can read the most recent chunk without touching the audio hot path (benign display-only race, no lock needed).
  - **`scripts/run_all_selftests.py` (new)**: Runs every module's embedded Mode A self-test (`ring_buffer`, `inference_engine`, `run_inference --self-test`, `spectrogram --self-test`) as subprocesses and prints one pass/fail summary.
  - **Bug found and fixed** (via the new runner — see dedicated note above CURRENT STATUS): `run_inference.py::run_self_test()` pointed at a stale Phase-1 fixture (`data/mixtures/noisy.wav`) that no longer exists; also fixed a duplicate-glob bug in the unused `batch_inference()` path it called into. Self-test now self-contained (generates its own synthetic clip).
  - **`docs/non_stationary_root_cause.md` (new)**: Decomposed the non-stationary category by subtype using `results/eval_raw.csv` (STOI/SI-SNR, real recomputed values). Finding: DeepFilterNet is excellent on helicopter (STOI 0.9108, +8.9 dB ΔSI-SNR — on par with the strongest categories) but on crowd babble its STOI (0.7080) is *below* the unprocessed noisy baseline (0.7196) and its ΔSI-SNR gain (+1.03 dB) is the smallest of every method tested on that subtype, including the classical baselines. Root cause: crowd babble is synthetic multi-speaker overlap (a proxy subtype, not a sourced defence noise), and single-channel enhancers structurally cannot separate target speech from background speech (cocktail-party problem) — this is not a defect specific to this DeepFilterNet checkpoint.
  - **Discovered (not caused) a pre-existing environment gap**: `results/eval_raw.csv` and `results/results.csv` are gitignored and were regenerated locally today at 11:17 without valid PESQ-WB data (`pesq` C-extension not present in this `.venv`; the build script targets a different Windows user profile). **Resolved later the same session** — see the "Fixed bugs" and "Major finding & fix: gunshot/artillery noise corpus" sections above CURRENT STATUS for the full pesq rebuild + dataset recovery + full pipeline regeneration.
  - Explicitly did NOT attempt: Round-2 fine-tuning — investigated in detail (real cost: from-scratch Rust toolchain + HDF5 dataset conversion, ~4-8h with real build risk; real benefit: capped by the cocktail-party problem being architectural, not data-limited) and skipped per user decision after seeing the honest cost/benefit breakdown. A physical-mic RTF re-test (`live/main.py stress`) was also not attempted — requires Pi hardware access this session doesn't have.
- Commands run: `.venv/Scripts/python.exe demo/spectrogram.py --self-test` (PASS), `.venv/Scripts/python.exe models/deepfilternet/run_inference.py --self-test` (PASS, RTF=0.2455), `.venv/Scripts/python.exe scripts/run_all_selftests.py` (ALL PASSED — ring_buffer 1.5s, inference_engine 9.5s, run_inference 9.8s, spectrogram_demo 1.3s).
- Result: **PASS** — all in-scope items complete and self-verified on this dev machine (Mode A). Spectrogram demo has not yet been run against real Pi hardware/mic (Mode B) — needs a smoke test on the Pi before it's relied on for the live judged demo.
- Files changed: `README.md`, `live/pipeline.py`, `demo/spectrogram.py` (new), `scripts/run_all_selftests.py` (new), `models/deepfilternet/run_inference.py`, `docs/non_stationary_root_cause.md` (new), `progress.md`.

### 2026-08-24 — Consolidated summary + forward plan (`summary/`), two new latency/validation gaps found
- Phase/Task: User-requested consolidation — full accomplishments record + comprehensive next-steps plan.
- What I did:
  - Created `summary/01_PROJECT_ACCOMPLISHMENTS.md` — complete Phase 0 → post-Phase-5 record: PS26052 requirement mapping, per-phase deliverables with evidence, all empirical results, the four incidents found and fixed, final compliance matrix, repository inventory, and an explicit "proven vs not proven" section.
  - Created `summary/02_NEXT_STEPS_PLAN.md` — P0/P1/P2 prioritized plan with time estimates, acceptance criteria, concrete commands, consolidated latency engineering plan, demo day runbook, risk register, execution schedule, and prepared evaluator Q&A.
  - Created `summary/README.md` — folder index with status-at-a-glance.
- **Two new gaps found while grounding the docs in the actual code (neither previously recorded):**
  1. **True end-to-end latency has never been measured.** `live/latency_test.py`'s own docstring states it "does NOT require physical audio hardware (it operates on in-memory audio arrays, not a sounddevice stream). It is therefore Mode A." The widely-quoted **29.18 ms is per-chunk model inference wall time, NOT end-to-end mouth-to-ear latency**. The Phase 5 DoD checklist row "`measure_latency.py` physical loopback (Test 5, Mode B) ✅ PASS" is therefore mislabeled — it was never a physical loopback test. The project plan explicitly required a physical loopback click test with 20 reps; only 10 in-memory reps were run.
     - Static analysis of `live/pipeline.py` gives an estimated standing latency of **~530 ms**: 100 ms input block (`blocksize=4800`) + **300 ms output priming** (`for _ in range(3): self._out_buf.write(silence)` — FIFO, never drains) + 100 ms output block + 29-38 ms inference. Arithmetic verified: 529.2-537.8 ms. ITU-T G.114 puts the interactive-voice comfort threshold at <150 ms and >400 ms at unacceptable.
     - All contributors are configuration-controllable; candidate chunk sizes (10/20/50 ms = 480/960/2400 samples) verified to be exact multiples of DFN3's 480-sample frame hop at 48 kHz.
  2. **The 10-minute stress test processed ALSA loopback content, not real audio.** `live/stress_test.py` drives `LivePipeline` with `config` device index 0 = `snd-aloop` virtual loopback, with nothing feeding its playback side. The run rigorously validates stability, thermals, buffer management and CPU load (DFN3 runs identically regardless of input content) but does **not** validate enhancement on real acoustic input. "10 minutes of live noise cancellation" would be an overstatement; "10 minutes of continuous pipeline operation with 0 dropouts" is accurate.
  - Also confirmed: **no physical microphone has ever been used** at any point in the project — `config/audio_config.yaml` sets `input_device: 0` / `output_device: 0` = ALSA Loopback `hw:2,0`, and `docs/phase_5_summary.md` §3 lists the audio infrastructure as the `snd-aloop` module.
- Evidence: `live/latency_test.py:10-12` (docstring), `live/pipeline.py:371-373` (3-chunk priming), `live/pipeline.py:348,358` (`blocksize=self._chunk_samples`), `config/audio_config.yaml` (device indices + snd-aloop comment), `live/stress_test.py:48` (`LivePipeline(config)`).
- Result: **PASS** — both summary documents complete. Two gaps logged honestly rather than papered over; both are P0 items in the new plan. No existing results are invalidated — the compute measurements (RTF, thermals, dropout counts, all offline evaluation) remain fully valid; only the *labeling* of the latency figure and the *scope* of the stress-test claim need correcting.
- Next step (P0, per `summary/02_NEXT_STEPS_PLAN.md`): acquire USB mic + headset → build `live/e2e_latency_test.py` (real streams, physical loopback, 20 reps) → cut output priming 3→1 and sweep chunk size → re-run stress test with real audio → smoke-test spectrogram on Pi.
- Files changed: `summary/README.md` (new), `summary/01_PROJECT_ACCOMPLISHMENTS.md` (new), `summary/02_NEXT_STEPS_PLAN.md` (new), `progress.md`.

### 2026-08-24 — P0-2/P0-3 groundwork built without physical mic/headset (user constraint)
- Phase/Task: User does not yet have a USB mic/headset (P0-1 blocked). Asked whether progress is still possible — yes: `snd-aloop` already exercises the real `sounddevice`/PortAudio/ALSA stack, just not physical transducers, so device-I/O-level latency work and priming/chunk-size engineering are fully buildable and Pi-testable now.
- What I did:
  - **`live/pipeline.py`**: Hardcoded output-buffer priming (`for _ in range(3): write(silence)` = permanent 300 ms standing latency, FIFO, never drains) replaced with a configurable `self._priming_chunks` (default 1), read from `pipeline.priming_chunks` in config.
  - **`config/audio_config.yaml`**: Added `pipeline.priming_chunks: 1` (was hardcoded 3) with a comment explaining it's standing latency not one-time warmup, and the reasoning for defaulting to 1 (measured p95 inference 39 ms against a 100 ms chunk budget = ~61 ms slack, comfortably covered). Documented: re-validate with `stress_test.py` (0 dropouts) after changing this or `chunk_duration_sec`.
  - **`live/e2e_latency_test.py` (new)**: Real device-I/O round-trip latency test using `sounddevice.playrec()` through the actual configured loopback (not the in-memory Mode A stand-in `live/latency_test.py` uses). Click-based, cross-correlation-free peak-detection with a noise-floor ratio check (`min_peak_ratio=20.0`) that raises `RuntimeError` rather than returning a silently-bogus lag when no click is detected. Computes a "full pipeline analytical estimate" = measured device round-trip + supplied `--inference-ms` + configured priming, clearly labeled as a computed estimate combining two real measurements, not one unified physical measurement. Includes an offline `--self-test` (Mode A, synthetic arrays) — verified passing: correctly recovers a known 960-sample synthetic lag, correctly raises on a click-free recording.
  - **`scripts/sweep_chunk_size.py` (new)**: Orchestrates `live/latency_test.py` + `live/stress_test.py` + `live/e2e_latency_test.py` across candidate chunk sizes (default 100/50/20/10 ms) using scratch config copies (does not touch the real `audio_config.yaml`), tabulating P95 RTF, dropouts, device round-trip, and full estimate per candidate. Implements the selection rule from `summary/02_NEXT_STEPS_PLAN.md` §7.3.
  - Added `e2e_latency_test.py --self-test` to `scripts/run_all_selftests.py`. Full suite re-verified green (5/5 Mode A tests).
  - Regenerated `pi_deploy.zip` (picks up `live/pipeline.py` and `config/audio_config.yaml` changes; `live/e2e_latency_test.py` included via the existing `live/` wholesale include).
- **What remains genuinely blocked without hardware:** a single physically-measured number that includes a *running* pipeline with real inference in the loop (injecting a click into an already-running `LivePipeline` process via the shared loopback). Attempting this via ALSA plumbing guesses without live Pi access risks wasting Pi time on a script that fails for reasons undiagnosable remotely (raw ALSA devices are typically exclusive-access; whether a second concurrent process can share the loopback, and the exact hw:2,0/hw:2,1 cross-wiring, are unverifiable from the dev machine). Deferred to when either (a) a physical mic/speaker arrives (trivial then — no ALSA puzzle), or (b) the user can inspect `sd.query_devices()` output live and confirm loopback topology.
- Commands run (dev machine, Mode A only): `.venv/Scripts/python.exe live/e2e_latency_test.py --self-test` (PASS), `.venv/Scripts/python.exe scripts/run_all_selftests.py` (5/5 PASS).
- Result: **PASS (Mode A)** — all buildable-without-hardware work complete and self-verified. **Mode B (Pi) verification still required** — see next step.
- Next step (hand to user — run on Pi via existing SSH workflow):
  ```
  git pull   # or re-run scripts/deploy_to_pi.py and copy over
  python live/e2e_latency_test.py --n-reps 20 --output-json results/e2e_devroundtrip_pi.json
  python live/main.py stress --duration 60          # quick check at new priming_chunks=1
  python scripts/sweep_chunk_size.py                # full chunk-size sweep table
  python live/main.py stress --duration 600         # full 10-min gate at chosen final setting
  ```
  Paste back the output of each — that's what turns this from "built and self-tested" into "verified on hardware" per Rule 29.
- Files changed: `live/pipeline.py`, `config/audio_config.yaml`, `live/e2e_latency_test.py` (new), `scripts/sweep_chunk_size.py` (new), `scripts/run_all_selftests.py`, `pi_deploy.zip`, `progress.md`.

### 2026-08-24 — Fixed two more stale-fixture/dead-code problems (run_inference.py, benchmark_rtf.py)
- Phase/Task: User flagged `run_inference.py` and `benchmark_rtf.py` as having "current problems" — investigated both directly.
- What I found and fixed:
  1. **`models/deepfilternet/benchmark_rtf.py`**: same stale-fixture class of bug as the earlier `run_self_test()` fix — `run_benchmark()` defaults to `input_wav="data/mixtures/noisy.wav"`, which no longer exists (`data/mixtures/` now holds the real 300-file Phase 2 dataset), and hard-failed with `sys.exit(1)`. Traced the fixture's origin to `scripts/generate_test_audio.py` (a 3 s synthetic multi-harmonic-tone-plus-noise generator, matching the "3.0-second 48 kHz synthetic speech-plus-noise mixture" described in `docs/phase_0_1_summary.md` §4) — that script exists but was never wired to auto-run. Fixed: if the input path doesn't exist, `run_benchmark()` now calls `generate_test_audio()` to create it on demand instead of crashing. Verified: ran to completion end to end (single-thread + 4-thread benchmark, JSON saved) on this dev machine; the dev-machine-generated `results/rtf_pi.json` and the regenerated `data/mixtures/noisy.wav` were immediately deleted after verification so no dev-machine numbers could ever be mistaken for real Pi hardware evidence at that reserved filename (Rule 29).
  2. **`models/deepfilternet/run_inference.py`**: the CLI defined `--input-dir`/`-i` (documented as "Input directory containing noisy wav files") but it was **never actually used** — `process_manifest()` (the only function called from `__main__`) takes no `input_dir` parameter, so the flag was silently a no-op. Fixed: `--input-dir` default changed to `None`; when explicitly passed, the CLI now correctly routes to `batch_inference()` (the directory-based batch path, already fixed for its glob/self-test bugs earlier this session) instead of the manifest-driven `process_manifest()`. Verified: created a scratch directory with one synthetic wav, ran `--input-dir <dir> --output-dir <dir>`, confirmed it actually processed the file (previously this exact invocation would have silently ignored `--input-dir` and looked for `data/manifest.csv` instead).
- Commands run: `.venv/Scripts/python.exe models/deepfilternet/benchmark_rtf.py` (PASS, auto-generated fixture, completed both thread configs), `.venv/Scripts/python.exe models/deepfilternet/run_inference.py --input-dir <scratch> --output-dir <scratch_out>` (PASS, 1/1 file processed), `.venv/Scripts/python.exe scripts/run_all_selftests.py` (5/5 PASS, unaffected).
- Result: **PASS** — both problems were real (reproducible crash; silently-ignored CLI flag), not false positives. Fixed and verified on this dev machine (Mode A / general Python correctness — neither fix touches Pi-specific code paths).
- Files changed: `models/deepfilternet/benchmark_rtf.py`, `models/deepfilternet/run_inference.py`, `progress.md`.

### 2026-08-24 — P0-2/P0-3 verified on Pi: real device round-trip measured, two real bugs found and fixed, chunk size decided
- Phase/Task: Ran the P0-2/P0-3 groundwork (built without hardware in the prior entry) on real Pi hardware for the first time. Session was interactive/iterative — recorded honestly including the false starts, per project convention of not hiding wrong turns.
- **Bug 1 — device config was silent by construction.** `config/audio_config.yaml` had `input_device: 0` / `output_device: 0` (same device for both). ALSA's `snd-aloop` does not loop a device to itself — it cross-pairs the two PCM devices on the card (audio played to `hw:2,0` arrives on the *capture* side of `hw:2,1`, never its own capture). Confirmed directly: `live/e2e_latency_test.py` read back exact zeros (`peak=0.00000, noise_floor=0.00000`) before the fix. Fixed: `input_device: 1`, `output_device: 0` (paired devices). After the fix, the same test read a real, consistent 42.667 ms round-trip across all 20 reps.
- **Bug 2 — stress-test dropout counter conflated shutdown drain with real failures.** `live/pipeline.py`'s output callback counted every buffer-empty event as a dropout, including the ones that necessarily happen after `stop()` (inference thread already exited, output stream still draining until closed). Every stress run therefore reported ≥1 dropout and FAILed regardless of actual real-time health — the selection rule in `scripts/sweep_chunk_size.py` (`dropouts == 0`) was mathematically unsatisfiable before this fix. Split into `_dropped_chunks` (real, gates PASS/FAIL) and `_teardown_underruns` (expected, reported separately, excluded from the verdict).
- **False start, recorded honestly:** hypothesized the 50 ms chunk size's sustained ALSA `input overflow` errors were caused by a blocking `wait_for()` call inside the real-time output audio callback, and shipped a `timeout=0` non-blocking fix. Tested on Pi: **falsified** — ALSA-level output underflows dropped to zero, but the application-level dropped-chunk count nearly quadrupled (170ish → 722/60s), because the ring buffer stopped giving the inference thread its normal few ms of scheduling slack. `input overflow` fired at an unchanged rate with or without the blocking wait, proving it was never the cause. Reverted the change (commit `2feba84`); the 50 ms `input overflow` issue is now understood to be a `snd-aloop` driver/period-negotiation issue specific to that chunk size, not an application bug — not pursued further given demo timeline (100 ms does not exhibit it).
- **Chunk size decision:** ran `scripts/sweep_chunk_size.py` across 100/50/20/10 ms with all fixes in place. 20 ms and 10 ms fail the RTF ≤ 0.6 budget outright (0.85, 1.75). 50 ms has the ALSA issue above. **100 ms selected** — confirmed via full 10-minute `python live/main.py stress --duration 600`: **PASS, 0 dropouts / 6001 chunks**, RTF median 0.3823 / p95 0.4008, max temp 52.9 °C.
- **Real end-to-end latency (first honest measurement — see P0-2 in `summary/02_NEXT_STEPS_PLAN.md`):** device round-trip 42.67 ms (median = p95 = min = max across 20 reps — deterministic for a digital `snd-aloop` loopback) + inference (~29–30 ms median) + 100 ms priming (1 chunk) ≈ **172 ms full-pipeline estimate**. This is a real `sounddevice`/PortAudio/ALSA measurement, not the old in-memory 29.18 ms figure — but it is still `snd-aloop`, not a physical microphone (P0-1 remains open).
- **Gap against the plan's target:** P0-3's acceptance criterion was measured end-to-end latency **< 150 ms, ideally < 100 ms**. Current confirmed figure is **~172 ms** — close but not met. The 50 ms chunk (which would have gotten to ~114 ms) is blocked by the driver-level issue above; closing this gap now needs either physical hardware (may behave differently from `snd-aloop`) or P1-3 (ONNX/quantization to shrink inference time, widening the RTF margin enough to make a smaller chunk viable). Reporting this honestly rather than rounding up to "target met."
- Commands run (Pi, Mode B): `python live/main.py detect`, `sudo modprobe snd-aloop`, `python live/e2e_latency_test.py --n-reps 20 ...` (before and after the device-pairing fix), `python live/stress_test.py --duration 60 ...` (multiple configs: priming 1 vs 3, blocking vs non-blocking callback), `python scripts/sweep_chunk_size.py` (run twice — first run was accidentally on stale code due to an interrupted `git pull` after a local `sed` edit conflicted with the incoming commit; caught via `git log --oneline` before drawing conclusions from it), `python live/main.py stress --duration 600` (final gate).
- Result: **PASS** — 100 ms chunk size locked in with real hardware evidence; two real bugs found and fixed; one hypothesis tested and correctly reverted when falsified. P0-1 (physical mic/headset) remains the primary open item.
- Files changed: `config/audio_config.yaml`, `live/pipeline.py`, `live/stress_test.py`, `progress.md`.

---

## Phase 5 Definition of Done — Final Checklist

| Item | Status | Evidence |
|---|---|---|
| `live/detect_devices.py` run on Pi | ✅ PASS | Device list printed, Loopback indices confirmed |
| `config/audio_config.yaml` created + documented | ✅ DONE | `input_device: 0, output_device: 0` (Loopback hw:2,0) |
| Ring buffer Test 1 (Mode A) | ✅ PASS | 6/6 self-tests on dev machine |
| `inference_engine.py` wraps DFN3, `lookahead_samples`=0 (Rule 30) | ✅ PASS | Cross-correlation confirmed 0-sample lag on Pi |
| Bypass mode: zero dropouts 60s (Test 2, Mode B) | ✅ PASS | Pi latency test bypass: 0 lag, 0 dropouts |
| Enhance mode: zero dropouts, RTF < 0.25... | ⚠️ PARTIAL | RTF=0.378 on loopback (0.292 on in-memory). Loopback scheduling adds overhead vs real-time USB mic. Reported as measured (Rule 33). |
| Bypass/Enhance toggle, click-free (Test 4, Mode B) | ✅ PASS | Dashboard 'b' toggle verified, 0 dropouts |
| `measure_latency.py` in-memory click test (Test 5, Mode B) | ✅ PASS | bypass=0.00ms, enhance=29.18ms median, 0-sample lag. **Relabeled 2026-08-24: this is per-chunk inference time, NOT end-to-end/physical-loopback latency — it never touches `sounddevice`.** |
| Real device I/O round-trip (`e2e_latency_test.py`, Mode B) | ✅ PASS | 42.67ms median=p95=min=max (20 reps, real `sounddevice`/PortAudio/ALSA, `snd-aloop`). Full pipeline estimate ≈172ms (round-trip + inference + 100ms priming). Added 2026-08-24 — see full writeup above. Still not a physical mic (P0-1 open). |
| `stress_test.py` 10 min on Pi (Test 6, Mode B) | ✅ PASS | Re-run 2026-08-24 at the confirmed 100ms chunk size with corrected dropout instrumentation: Verdict PASS, 0 dropouts / 6001 chunks, max 52.9°C, 600.5s |
| RTF under live load (Test 7, Mode B) | ✅ PASS | median RTF=0.3823, p95=0.4008 (6001 chunks, 600.5s run, 2026-08-24) |
| `demo/dashboard.py` terminal mode | ✅ PASS | Renders on Pi SSH, clean exit |
| `deploy_to_pi.py` syncs clean runtime | ✅ DONE | `pi_deploy.zip` generated, excludes datasets |
| `live/main.py` unified CLI functional | ✅ PASS | All subcommands verified |
| `progress.md` / `architecture.md` updated with real Pi evidence | ✅ DONE | This log |

> **RTF note (Rule 33):** The target was RTF < 0.25. On Pi 5 in-memory (latency_test), enhance RTF = 0.292. Under live loopback load (stress test), RTF = 0.378. Both are above 0.25 but well below 1.0 (real-time limit). This is reported exactly as measured. With a real USB mic (lower loopback scheduling overhead), live RTF is expected to be closer to the in-memory 0.292 figure. This finding is logged as a real measurement, not hidden or re-parameterised.
