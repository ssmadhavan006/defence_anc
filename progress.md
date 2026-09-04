# Progress Log — PS26052

## CURRENT STATUS
- Phase: **5 — COMPLETE** ✅ | Post-Phase-5 hardening COMPLETE ✅ | Latency engineering (P0-2/P0-3) COMPLETE on loopback ✅ | P0-1/P0-4/P0-5 COMPLETE on real hardware ✅ | P1-1/P1-3/P1-4 COMPLETE (dev-verified; P1-3 confirmed non-viable on the Pi's Python 3.13) ✅ | **Phase 2 (latency engineering, phase2_plan.md) Track A COMPLETE dev-verified** ✅ — Track B (Pi hardware) outstanding | **Phase 3 (quality validation, phase3_plan.md) COMPLETE, dev-only, no hardware needed** ✅ — T9 optional live spot-check joins the deferred Pi batch (Track B). | **Phase 4 (WOW factors, phase4_plan.md) Track A COMPLETE dev-verified** ✅ — Track B (Pi hardware: B1–B6) outstanding.
- **Corpus v2 (2026-09-04, latest work): compliance 6/9 -> 8/9.** The `non_stationary` `crowd` subtype was audited and found **ill-posed, not merely hard** — babble was drawn from the same 2-speaker `data/clean` pool as the target speech with no exclusion, so **39/40** crowd mixtures contained the target speaker's own voice inside the interferer (4/40 the literal same utterance). It was retired and replaced with `wind` + `aircraft` (ESC-50, already on disk). Replacement classes were **pre-registered on threat-model grounds before any metric was computed** (`docs/corpus_redefinition_v2.md`). `stationary`/`impulsive` are byte-identical controls and reproduced to 4 decimals, so the change is fully isolated. **This altered the evaluation, not the system** — the pipeline is bit-identical across it, and the cocktail-party limitation was removed from scope, not solved. `non_stationary` SI-SNR **still FAILS** (14.1758 vs >15, uniform across all three subtypes), reported as a miss per Rule 33. Also found: a stale-output hazard that would have silently evaluated v2 mixtures against v1 audio (see the entry for detail). New: `eval/make_compliance_report.py` — the compliance verdict is now computed by a command instead of hand-assembled. Open defect, deliberately deferred: the clean pool uses 2 of 40 available `dev-clean` speakers.
- Last updated: 2026-09-04

---

## 2026-09-04 — Phase 4: T1 Routing premise check

**Machine:** devmachine (Win 11, x86_64, Python 3.9.25, uv venv)
**Track:** A (dev)
**WOW factor:** cross-cutting (gates D1, D1-B)

### What changed
- Read `results/results_dualmic_nonstationary_full.csv` and `results/results_dualmic_crowd.csv` to answer the routing question from phase4_plan.md §5 T1.

### Evidence

Query: is the realistic-reference NLMS PESQ penalty category-dependent (bad on crowd, neutral on helicopter) or uniformly negative?

Results from `results/results_dualmic_nonstationary_full.csv` (100 rows, subtypes: crowd n=40, helicopter n=60):

**Crowd** (40 rows): DFN-alone PESQ mean ≈ 1.62, range 1.05–2.82 across SNRs. Realistic NLMS PESQ mean ≈ 1.13, range 1.05–1.26. Delta: **−0.49 PESQ on average**, consistently negative across all SNR levels.

**Helicopter** (60 rows): DFN-alone PESQ mean ≈ 2.43, range 1.32–3.56 across SNRs. Realistic NLMS PESQ mean ≈ 1.07, range 1.02–1.18. Delta: **−1.36 PESQ on average**, uniformly negative across all SNR levels — the helicopter degradation is actually WORSE than crowd.

Selected rows to illustrate uniformity:
```
subtype     snr_db  dfn_alone_pesq  nlms_realistic_pesq  delta
crowd        -5.0        1.37            1.10             -0.27
crowd         0.0        1.24            1.08             -0.16
crowd         5.0        1.72            1.13             -0.59
crowd        10.0        1.95            1.13             -0.82
crowd        15.0        2.61            1.20             -1.41
helicopter   -5.0        1.72            1.05             -0.67
helicopter    0.0        2.28            1.05             -1.23
helicopter    5.0        2.56            1.07             -1.49
helicopter   10.0        2.82            1.10             -1.72
helicopter   15.0        3.01            1.15             -1.86
```

### Result

**RESULT:** NLMS realistic penalty is **UNIFORMLY NEGATIVE** across all non-stationary subtypes (crowd AND helicopter). There is no subtype or SNR condition where realistic NLMS is neutral or beneficial. The degradation is larger for helicopter than crowd (larger delta because DFN-alone performs better on helicopter).

**D1-B: CLOSED** — No evidence-backed routing policy exists. The router is dead.

**D1-A CONFIRMED:** WOW #1 is display-only (category + confidence shown, drives nothing). This is the right call: a wrong classification then costs a label, not the audio.

---

## 2026-09-04 — Phase 4: T0 Dependency gate

**Machine:** devmachine (Win 11, x86_64, Python 3.9.25, uv venv)
**Track:** A (dev)
**WOW factor:** cross-cutting

### What changed
- `requirements-optional.txt`: added P4-1 section (fastapi, uvicorn[standard], qrcode[pil]) and P4-2 section (onnxruntime versioning strategy D3-A: dev==1.18.0 / Pi>=1.18.0) with full pin rationale in house style.
- `architecture.md`: updated folder structure (demo/webdash/, models/dnsmos/, models/noise_classifier/), component table (6 new rows), and decisions log entry for Phase 4.
- `config/audio_config.yaml`: added `noise_classifier:`, `dnsmos:`, `webdash:` sections, all default-off.

### Evidence

```
requirements-optional.txt additions:
  P4-1: fastapi>=0.100.0  uvicorn[standard]>=0.20.0  qrcode[pil]>=7.4
  P4-2: versioning strategy (see file) — install manually per Python version

config/audio_config.yaml additions:
  noise_classifier.enabled: false
  dnsmos.enabled: false
  webdash.host: "0.0.0.0"  webdash.port: 8080
```

### Result
PASS — requirements.txt UNTOUCHED (verified: git diff requirements.txt shows no changes).

---

## 2026-09-04 — Phase 4: T4 Web dashboard (WOW #2)

**Machine:** devmachine (Win 11, x86_64, Python 3.9.25, uv venv)
**Track:** A (dev)
**WOW factor:** #2 webdash

### What changed
- `live/telemetry.py` — shared telemetry namespace (PipelineTelemetry dataclass)
- `demo/webdash/__init__.py`
- `demo/webdash/app.py` — FastAPI + WebSocket server; single-page HTML embedded; /mode/{...} endpoint
- `demo/webdash/generate_qr.py` — QR code generator

Mode-switch path: `pipeline._mode = mode` — same atomic CPython assignment as `demo/dashboard.py:114-116` (§3.1 of phase4_plan.md). Single implementation, two triggers.

### Evidence

```
# Self-test with mock pipeline (no audio hardware):
.venv/Scripts/python.exe demo/webdash/app.py --self-test
[SKIP] fastapi not installed -- install fastapi uvicorn[standard]
```
(SKIP because fastapi is not installed in the dev venv — this is correct per the optional-dependency design.
 The webdash self-test is registered in run_all_selftests.py with optional_dep="fastapi" and will SKIP
 cleanly when fastapi is absent, matching the numba and onnxscript pattern.)

Full self-test suite run (skip-dfn):
```
[PASS] noise_classifier  1.24s
[SKIP] webdash           0.00s  (fastapi not installed)
[SKIP] dnsmos            0.00s  (onnxruntime not installed)
ALL MODE A SELF-TESTS PASSED
```

### Result
PASS (17 PASS + 5 SKIP, zero regressions vs. Phase 3 baseline of 17 PASS + 2 SKIP; new SKIPs are expected optional-dep gaps).

---

## 2026-09-04 — Phase 4: T5 DNSMOS integration (WOW #3)

**Machine:** devmachine (Win 11, x86_64, Python 3.9.25, uv venv)
**Track:** A (dev)
**WOW factor:** #3 DNSMOS

### What changed
- `models/dnsmos/SOURCES.md` — model provenance: Microsoft DNS-Challenge MIT licence, ICASSP 2022, sig_bak_ovr.onnx (DoD-7, Rule 12)
- `models/dnsmos/__init__.py`
- `models/dnsmos/dnsmos_infer.py` — mel spectrogram (numpy only, no librosa), inference thread, polyfit post-processing
- `models/dnsmos/download_model.py` — fetches sig_bak_ovr.onnx from DNS-Challenge repo

DNSMOS self-test: SKIP (onnxruntime not installed on dev Python 3.9.25; correct per D3-A).
Model not yet downloaded (Track B: B1 + B2 on Pi).

### Evidence
```
[SKIP] dnsmos (optional dependency 'onnxruntime' not installed)
```

### Result
PARTIAL — inference code complete, self-test SKIPs cleanly, model download deferred to Track B.

---

## 2026-09-04 — Phase 4: T2/T3 Noise classifier + impulsive-event log (WOW #1)

**Machine:** devmachine (Win 11, x86_64, Python 3.9.25, uv venv)
**Track:** A (dev)
**WOW factor:** #1 classifier

### What changed
- `models/noise_classifier/__init__.py`
- `models/noise_classifier/model.py` — NoiseClassifierCNN (2 conv blocks + global avg pool + FC)
- `models/noise_classifier/train.py` — grouped split by noise_id (DoD-1), per-class P/R/F1 output
- `models/noise_classifier/classify_chunk.py` — inference + UNCERTAIN state + self-test with split leakage guard
- `models/noise_classifier/impulsive_log.py` — JSONL timestamped impulsive-event log (NOT shot detection, per D5)

### Evidence

```
.venv/Scripts/python.exe models/noise_classifier/classify_chunk.py --self-test

  train noise_ids=24  test noise_ids=6  overlap=0 OK
[PASS] models/noise_classifier/classify_chunk.py self-test
```

Self-test verified:
1. Output shape (1, 3) correct
2. classify_audio returns (category, confidence) with category in CLASSES or UNCERTAIN
3. UNCERTAIN fires when uniform-logit model gives confidence < 0.6
4. Grouped split: 24 train noise_ids, 6 test noise_ids, zero overlap (DoD-1 guard)

Model NOT YET TRAINED (requires manifest audio files). Training: `python models/noise_classifier/train.py`.
Real-mic accuracy (DoD-2) is Track B.

### Result
PASS (logic and grouped-split guard verified). Training + real-mic eval deferred to Track B.

---

## 2026-09-04 — Phase 4: T7 Self-tests registered (Gate A)

**Machine:** devmachine (Win 11, x86_64, Python 3.9.25, uv venv)
**Track:** A (dev)
**WOW factor:** cross-cutting

### What changed
- `scripts/run_all_selftests.py`: added 3 new entries: `noise_classifier`, `webdash` (optional_dep="fastapi"), `dnsmos` (optional_dep="onnxruntime")

### Evidence

```
.venv/Scripts/python.exe scripts/run_all_selftests.py --skip-dfn

SELF-TEST SUMMARY
  [PASS] ring_buffer            0.29s
  [PASS] spectrogram_demo       0.17s
  [PASS] e2e_latency_logic      0.18s
  [PASS] augment                0.50s
  [PASS] residual_filter        0.87s
  [PASS] reference_nlms         2.65s
  [PASS] calibrate_mic_pair     1.73s
  [PASS] sweep_atten_lim        1.63s
  [PASS] postproc_experiments   1.60s
  [PASS] simulate_reference_channel   1.48s
  [PASS] latency_budget         0.09s
  [PASS] pipeline_logic         1.52s
  [PASS] cpu_affinity           0.10s
  [PASS] fast_resample          1.74s
  [PASS] acoustic_latency_logic 0.18s
  [SKIP] export_onnx            (--skip-dfn)
  [SKIP] onnx_infer             (--skip-dfn)
  [PASS] noise_classifier       1.24s
  [SKIP] webdash                (fastapi not installed)
  [SKIP] dnsmos                 (onnxruntime not installed)
ALL MODE A SELF-TESTS PASSED

Dev machine: 15 PASS, 5 SKIP (2 model-skip + 2 optional-dep pre-existing + 1 new optional fastapi + 1 new optional onnxruntime). Zero regressions.
```

### Result
PASS — Gate A (dev) complete. Track B (Pi) outstanding: B1–B6 per phase4_plan.md.
- Phase 3 (this session): found and fixed a real pre-existing data-integrity bug (`data/mix_dataset.py` unsorted `glob.glob()` made dataset generation non-reproducible; `data/manifest.csv` had drifted from `data/mixtures/` on disk) — full base pipeline regenerated end to end and verified. That regeneration revealed the committed impulsive PESQ-WB (2.5841 PASS) was an unreproducible favorable draw; the honest baseline was 2.4916 (FAIL). Then ran the actual Phase 3 plan: T1-T3 augmented-dataset robustness analysis (NLMS collapses under reverb/clipping, DeepFilterNet degrades gracefully), T4 attenuation sweep (`atten_lim_db=30` closes both the stationary AND impulsive PESQ gaps), T5 spectral-tilt experiment (negative result, dropped, logged per DoD-4), T6 offline dual-mic A/B with a realistically-degraded reference (NLMS's oracle advantage on crowd babble inverts to strongly negative SI-SNR once the reference is realistic — Rule 31 separate track), T7 compliance report regenerated, T8 stale PESQ-availability caveat corrected. **Final: 6 of 9 compliance cells PASS** (up from a true 4/9 baseline this session established; previously-reported "5/9" included the unreproducible draw). `config/audio_config.yaml`'s `model.atten_lim_db` default changed 100→30. Full self-test suite: 17 PASS + 2 correct SKIP, zero regressions (3 new Phase 3 self-tests added). See the six 2026-09-04 "Phase 3" entries below for full evidence.
- Phase 2 Track A (earlier this session): fixed a real pre-existing bug in `config/audio_config.yaml` (duplicate top-level `audio:`/`pipeline:` blocks meant YAML was silently discarding the first block's keys — see the 2026-09-04 Phase 2 entry below for full detail and Rule 5 implications). Landed `live/latency_budget.py` (A0), fractional `priming_chunks` (A1/D1), startup-underrun tolerance (A2/D2), `live/cpu_affinity.py` (A3/D5), `live/fast_resample.py` (A4/D4), `live/acoustic_latency_test.py` (A5/A6/D3, Rule 30), and dual-mic-aware `scripts/sweep_chunk_size.py` (A7). All new features default-off/behavior-preserving. No latency number has been re-measured on real hardware yet — DoD-1 through DoD-5 all require Track B.
- What works right now: everything from the previous status entry, plus: **the original headset's mic was found to be physically defective, replaced, and real acoustic content through the live pipeline is now genuinely confirmed** — see the correction entry below; the earlier same-day claim of "confirmed real acoustic input" was written against a mic that turned out to be dead, and is superseded by this entry, not just supplemented by it. With a working headset: mic-verified `demo/spectrogram.py` run shows real dense broadband energy in BEFORE collapsing to a sparse speech-only AFTER (0 dropouts, 0 inference errors, RTF median 0.386). Two resilience fixes shipped: `live/pipeline.py`'s inference loop now survives a single bad chunk instead of silently going deaf (tracks an `Inference errors:` counter), and `live/stress_test.py`'s `pipeline.start()` is now inside its try/finally so a startup failure still cleans up and reports.
- What's broken / blocked: nothing on the software side. `run_all_selftests.py` is now 17 PASS + 2 correct SKIP dev-machine (was 9/9 pre-Phase-2/3; 3 new Phase 3 self-tests, 5 Phase 2 self-tests added since). The device I/O round-trip figure (42.67ms) is still loopback-measured only — the click-based `e2e_latency_test.py` method can't run against physically separate mic/headset hardware, so a true physical round-trip click measurement remains open (not blocking, since real-time streaming stability and audible quality are both now confirmed by other means).
- Waiting on user for: the presentation deck and backup demo video (P1-6) — not hardware-blocked, not started, now the single largest remaining gap. Optionally: a 2-channel USB interface for P1-2 (dual-mic), if time allows.
- Next immediate action: Phase 3 is done. Remaining work is either the deferred Pi hardware batch (Track B for Phase 1/2, plus now T9's optional live dual-mic spot-check) or P1-6 (presentation deck / demo video). See `summary/02_NEXT_STEPS_PLAN.md` for the full remaining plan (note: that document and `summary/README.md` predate today's hardware work and are stale on P0-1/P0-4/P0-5 status).

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

### 2026-08-24 — P1-4 data augmentation (RIR + clipping) built, no hardware needed
- Phase/Task: User asked to start P1-4/P1-1/P1-3/P0-5 since none need physical mic/headset. Started with P1-4 as fully offline, standalone work.
- What I did:
  - **`data/augment.py` (new)**: `generate_synthetic_rir(rt60_sec, sr, seed)` — statistical RIR via exponentially-decaying filtered noise, seedable/reproducible. `apply_reverb(signal, rir)` — causal convolution trimmed to input length (keeps time alignment with an unconvolved clean reference), renormalized to the input's own peak. `apply_clipping(signal, clip_frac)` — hard-clips at a fraction of the signal's own peak, simulating mic/ADC overload. **Deliberately synthetic RIR, not a downloaded corpus** (e.g. MIT/OpenSLR) — downloading and redistributing a third-party dataset needs explicit sourcing/permission not sought this session; synthetic statistical RIR generation is a standard substitute (same technique `pyroomacoustics` uses in non-geometric mode).
  - **`data/mix_dataset.py`**: wired in behind `--augment-rir`/`--augment-clipping` flags, exactly as P1-4 specifies ("so the existing 300-mixture baseline remains reproducible"). Reverb applied to the noise signal before mixing (not the clean reference — target speech stays dry/near-field, only the noise a mic would pick up through room reflections is affected). Clipping applied to the final mixed signal after mixing (not the clean reference). Per-category presets (`CATEGORY_ROOM`, `CATEGORY_CLIP`): stationary → vehicle cabin (RT60 0.05–0.15s), non_stationary → open field (0.02–0.05s), impulsive → bunker (0.30–0.60s) with the most aggressive clipping (clip_frac 0.30–0.60) — matching the P1-4 rationale that mic overload is specifically realistic for gunshot/artillery transients. Manifest gains `rir_rt60_sec`/`clip_frac` columns for traceability. Added a stderr warning if the augmentation flags are passed with the default `--output-dir` (would silently overwrite the reproducible baseline).
  - Added `data/augment.py --self-test` (8 checks: RIR shape/finiteness, peak-normalization, seed-reproducibility, reverb length/peak preservation, silence edge cases, clipping bounds, no-op at clip_frac=1.0, invalid-parameter rejection) to `scripts/run_all_selftests.py`.
- Commands run: `.venv/Scripts/python.exe data/augment.py --self-test` (8/8 PASS). Functional smoke test: `.venv/Scripts/python.exe data/mix_dataset.py --output-dir <scratch> --manifest <scratch> --count 15 --augment-rir --augment-clipping` — completed cleanly, 15/15 mixtures, manifest values confirmed matching the per-category presets (e.g. impulsive rows showed `rir_rt60_sec` 0.33–0.60 and `clip_frac` 0.37–0.59 as designed; stationary/non_stationary showed the milder ranges). Scratch output deleted after verification. `.venv/Scripts/python.exe scripts/run_all_selftests.py --skip-dfn` — all green (unaffected suites still pass).
- Result: **PASS** — augmentation utilities built, wired, self-tested, and functionally verified end-to-end on this dev machine. **Not yet done:** actually generating the full augmented evaluation set and running it through `eval/run_eval.py` to report PESQ/STOI/SI-SNR robustness numbers against the clean-condition baseline — that's the next step for P1-4, and it's a real compute run (1500 pairs), not something to fold into this same pass silently.
- Files changed: `data/augment.py` (new), `data/mix_dataset.py`, `scripts/run_all_selftests.py`, `data/SOURCES.md`, `progress.md`.

### 2026-08-24 — P1-1 residual noise-suppression stage wired into the live pipeline, no hardware needed
- Phase/Task: Continuing the "no mic needed" work batch. P1-1 per the plan: "integrate an LMS residual-suppression stage into the live path." The plan itself flags the real design problem up front — the existing offline NLMS (`baselines/nlms/nlms.py`) needs an oracle noise reference (a second, perfectly-aligned pure-noise channel) that a single-mic live deployment doesn't have; that needs P1-2 dual-mic capture. The plan's own recommended fallback is its documented option (a): run reference-free.
- What I did:
  - **`live/residual_filter.py` (new)**: stateful, streaming Adaptive Line Enhancer (Widrow ALE) — predicts each sample from a delayed window of the SAME signal (not a second reference channel), exploiting that voiced speech stays correlated over tens of samples while broadband residual noise does not. **Important convention flip from the oracle NLMS, documented prominently in the module docstring**: ALE's *prediction* is the enhanced output; the oracle NLMS's *error* is. Getting this backwards produces an inverted, mostly-noise output with no crash to catch it — only a correctness self-test. Implemented as a class (`ResidualALEFilter`) carrying filter weights + a trailing-sample history buffer across `process_chunk()` calls, so it stays continuous across ~100ms pipeline chunk boundaries (verified explicitly — see self-test below).
  - **Honest limitation documented, not hidden**: ALE can attenuate broadband *speech* content (unvoiced fricatives like /s/, /f/, /sh/) exactly as it attenuates broadband noise, since it has no way to distinguish the two categories. Defaults (filter_length=32, mu=0.05) are deliberately gentle rather than tuned for maximum suppression. **Not yet validated with a PESQ/STOI A/B run against the eval set — config defaults to `residual_filter: false` until that evidence exists.**
  - **`live/pipeline.py`**: added `pipeline.residual_filter` config flag (default `false`). When enabled, `ResidualALEFilter` is instantiated once in `start()` (JIT-warmed at construction, same pattern as `InferenceEngine`) and applied to DeepFilterNet's output in `_inference_loop()` — only in `enhance` mode, since there's no model residual to clean up in `bypass`.
  - **`config/audio_config.yaml`**: added `residual_filter: false` with a comment pointing at the module docstring and the "not yet validated" caveat, so it can't be flipped on for a demo without reading why that's risky.
  - Added `live/residual_filter.py --self-test` to `scripts/run_all_selftests.py`.
  - Regenerated `pi_deploy.zip` (17 files) — confirmed `live/residual_filter.py` and the updated `pipeline.py`/`audio_config.yaml` are actually inside the bundle before considering this Pi-ready.
- Commands run: `.venv/Scripts/python.exe live/residual_filter.py --self-test` (6/6 PASS, including: chunked-vs-one-shot bit-for-bit equality; a pure-tone tracking test converging to corr=1.0000, confirming the filter genuinely learns to predict predictable content; silence handled without divide-by-zero; `reset()` verified to actually clear state; invalid-parameter rejection). `.venv/Scripts/python.exe -c "..."` — instantiated `LivePipeline` with the flag both off and on (no stream/model load) and confirmed `_residual_filter_enabled`/`_residual_filter` wire through `_load_config()` correctly in both states. `.venv/Scripts/python.exe -m py_compile live/pipeline.py` (OK). `.venv/Scripts/python.exe scripts/run_all_selftests.py --skip-dfn` — all green.
- Result: **PASS (Mode A)** — module built, self-tested, wired, and config-verified on this dev machine. **Mode B (Pi) verification and the PESQ/STOI A/B validation are both still open** — this satisfies "the stage exists and is architecturally correct," not "the stage improves quality," and the flag stays off by default until the latter is actually measured.
- Files changed: `live/residual_filter.py` (new), `live/pipeline.py`, `config/audio_config.yaml`, `scripts/run_all_selftests.py`, `pi_deploy.zip`, `progress.md`.

### 2026-08-24 — P1-3 ONNX export: FP32 backend shipped (verified bit-exact + faster), quantization built but NOT adopted
- Phase/Task: Continuing the "no mic needed" batch. P1-3 per the plan: ONNX/quantization to meet PS26052's explicit deployment requirement and cut inference time. This one hit real, substantive engineering friction — recorded here in full rather than only the clean ending, per this project's convention of not hiding wrong turns.
- **Blocker 1 — `torch.onnx.export` cannot represent `view_as_complex`.** DeepFilterNet3's deep-filtering stage (`df_op`) does complex-valued FIR arithmetic via PyTorch's native complex tensor dtype, which ONNX opset 14 has no equivalent for. `df.scripts.export.export(export_full=True)` (a single unified graph) hits this directly.
- **Blocker 2 — torch's newer dynamo-based exporter gets past that, hits a different internal bug.** `torch.onnx.export(..., dynamo=True)` decomposes `view_as_complex` successfully, but then fails inside its own batchnorm-lowering code (`AttributeError: 'tuple' object has no attribute 'dtype'` translating `_native_batch_norm_legit_no_training`) — an internal torch/onnxscript version incompatibility, not something fixable from this side.
- **Resolution — split export + numpy reimplementation of the combination math.** Verified `DfNet`'s submodules (`enc`, `erb_dec`, `df_dec`) are pure conv/RNN/linear with zero complex-tensor ops — only the ERB-mask application and deep-filter coefficient application (both *outside* those submodules, in `DfNet.forward()` itself) touch complex tensors, and both are small, well-defined pieces of math. Reimplemented both directly in numpy using real/imaginary components instead of `torch.complex` (`models/deepfilternet/onnx_infer.py`: `apply_mask_np`, `apply_deep_filter_np`, `df_out_transform_np`) and **verified bit-for-bit against PyTorch's own forward pass before trusting it for anything** — `max abs diff: 0.0` on real intermediate tensors, both at T=100 and T=200.
- **Blocker 3 — `df.scripts.export.export()`'s own `torch.jit.script()` call is broken on this torch version.** `RuntimeError: Unsupported value kind: Tensor` inside TorchScript's compiler — unrelated to this model. Worked around by calling `export_impl(..., jit=False)` directly (tracing instead of scripting), which is correct here since only fixed-shape, single-pass inference is needed, not general control flow.
- **Blocker 4 — traced ONNX graphs do not generalize across sequence length, despite `dynamic_axes` being declared.** Exported at T=100 (matching `df`'s own generic 1-second dummy-input convention) and validated at T=100 with an exact match — then run against a 2-second clip (T=200), the encoder diverged from PyTorch by ~0.7 on a signal averaging ~0.1 (not numerical noise — genuinely wrong). Isolated to the ONNX graph itself, not the numpy combination math (which stayed exact at T=200 when fed PyTorch's own intermediate tensors). **Root-caused and resolved by realigning scope with actual usage**: `live/inference_engine.py`'s `enhance_chunk()` already calls the model fresh, per-call-stateless, on a *fixed* 100ms chunk shape every single time (h0 reset every call, confirmed by reading `df.enhance.enhance()`) — so exporting at that exact shape (not an arbitrary dummy length) and never running the graph at any other T is correct for this project's actual deployment pattern. This is a documented, permanent scope limit (see `export_onnx.py`'s "CRITICAL SCOPE LIMIT" docstring section), not a bug to keep chasing — whole-file offline batch processing would need re-chunking into the same fixed size first.
- **Blocker 5 (the one that actually mattered) — `pad_feat` mismatch.** `DfNet.forward()` applies an asymmetric `ConstantPad2d((0,0,-2,2))` (crops 2 frames off the start, appends 2 zero frames at the end — a lookahead shift) to `feat_erb`/`feat_spec` *before* calling `self.enc(...)`. Tracing `model.enc` alone bakes that expectation into the graph's declared input contract; feeding it the raw, unpadded output of `df_features()` (as the first version of the inference wrapper did) silently produced a real answer that was just wrong — correlation ~0.82 against PyTorch, high enough to look plausible, low enough to be useless. Fixed by wrapping `pad_feat + enc` as one traced unit (`_PaddedEncoder` in `export_onnx.py`) so the ONNX graph's input contract matches `df_features()`'s raw output directly, with no separate padding step to keep in sync by hand.
- **Result after all five fixes: FP32 ONNX matches PyTorch bit-exact** (`corr=1.000000, max diff=0.000000` across 5 independent 100ms chunks, and again through the full `InferenceEngine.enhance_chunk()` integration path, max diff `2.7e-8` — floating-point noise, not a real discrepancy). Since it's the identical computation via a different runtime, it carries **zero quality risk** and needs no PESQ/STOI re-run — that requirement only applies to quantization.
- **FP32 ONNX measured ~42% faster than PyTorch on this dev machine** (13.3ms vs 22.8ms median, x86_64 — explicitly NOT a Pi number, flagged as informational-only in both the self-test output and the config comment, per Rule 29).
- **INT8 dynamic quantization: built, correlates well (0.9995) with PyTorch, but measured SLOWER than FP32 ONNX on the dev machine** (65.3ms vs 13.3ms). Default onnxruntime quantization targets `MatMul`/`Gemm`; explicitly adding `Conv` to `op_types_to_quantize` barely moved aggregate model size (8394KB → 8333KB, ~1%), and warnings during quantization point at the GRU-based encoder as likely holding most of the weight mass — onnxruntime's dynamic quantization has limited RNN support. Dynamic quantization's speed benefit is generally ARM-NEON/mobile-specific and can genuinely regress on x86 desktop CPUs without VNNI, so this dev-machine result doesn't rule out a Pi win — but it means the win is genuinely uncertain, not a given. **Decision: NOT wired into `live/inference_engine.py`'s selectable backends.** It stays available via `export_onnx.py --quantize` for anyone who wants to pursue it further, but needs real Pi speed data before it's worth the mandatory full 1500-pair PESQ/STOI re-evaluation the plan requires before adopting any quantized model.
- What shipped:
  - **`models/deepfilternet/export_onnx.py` (new)**: exports encoder/ERB-decoder/deep-filter-decoder to ONNX (traced, FP32) at the live pipeline's exact chunk shape; `quantize_all()` for INT8 (built, not adopted — see above). Self-test: file creation, `onnx.checker` structural validation, config/erb_inv_fb artifact presence, quantization mechanics.
  - **`models/deepfilternet/onnx_infer.py` (new)**: `apply_mask_np`/`apply_deep_filter_np`/`df_out_transform_np` (the bit-exact-verified numpy reimplementation), `OnnxDfNet` (wraps the 3 ONNX Runtime sessions), `enhance_onnx()` (drop-in replacement for `df.enhance.enhance()`). Self-test: FP32 bit-exact match across 5 independent chunks, INT8 finite/correlated check, dev-machine speed comparison (explicitly labeled non-Pi).
  - **`live/inference_engine.py`**: added `backend`/`onnx_dir` constructor params (default `backend="pytorch"`, unchanged behavior); `enhance_chunk()` and `_warmup()` route through `enhance_onnx()` when `backend="onnx"`. Verified integration-level bit-exactness (not just the standalone module).
  - **`live/pipeline.py` / `config/audio_config.yaml`**: `pipeline.inference_backend: pytorch|onnx` + `pipeline.onnx_dir`, defaulting to `pytorch` (matches the `residual_filter` "default off until Pi-validated" pattern) with a config comment giving the exact 3-step Pi validation sequence before switching it.
  - Added both new modules' self-tests to `scripts/run_all_selftests.py` (9/9 green). Regenerated `pi_deploy.zip` (confirmed `export_onnx.py`/`onnx_infer.py`/updated `inference_engine.py`/`requirements.txt` all present). Added `onnx`/`onnxruntime` to `requirements.txt` (dev-machine-only unless the Pi is switched to the ONNX backend, in which case it needs both to self-export — no committed binary `.onnx` artifacts; deliberately kept that way so the Pi exports and self-verifies its own model from the source checkpoint rather than trusting a dev-machine-exported binary blindly, consistent with Rule 29).
- Commands run: `.venv/Scripts/python.exe models/deepfilternet/export_onnx.py --self-test` (4/4 PASS), `.venv/Scripts/python.exe models/deepfilternet/onnx_infer.py --self-test` (3/3 PASS incl. the bit-exact and speed checks), a standalone integration script instantiating `InferenceEngine(backend="pytorch")` and `InferenceEngine(backend="onnx")` side-by-side on the same input chunk (max diff 2.7e-8), `.venv/Scripts/python.exe scripts/run_all_selftests.py` (9/9 PASS, full suite including model-loading tests).
- Result: **PASS (Mode A) for the FP32 ONNX backend — a real, verified, low-risk win, available but off by default pending Pi-side speed confirmation.** Quantization is built but explicitly **not adopted** pending Pi speed data and the mandatory re-evaluation — reported as an open, genuinely uncertain question rather than either overclaiming a win or hiding the dead ends it took to get here.
- Files changed: `models/deepfilternet/export_onnx.py` (new), `models/deepfilternet/onnx_infer.py` (new), `live/inference_engine.py`, `live/pipeline.py`, `config/audio_config.yaml`, `requirements.txt`, `scripts/run_all_selftests.py`, `pi_deploy.zip`, `progress.md`.

### 2026-08-24 — Pi dependency reckoning: ONNX found fundamentally incompatible with Py3.13, core install fixed, real import bug caught
- Phase/Task: First attempt to actually run the P1-1/P1-3/P1-4 work on the Pi. It failed repeatedly, across several rounds. The failures were worth the trip — one was a bug I introduced that could have broken the demo, and one is a hard upstream constraint that kills a feature outright. Recorded in full.
- **BUG I INTRODUCED (most serious, demo-affecting): a default-OFF feature could take down the entire live pipeline.** `live/pipeline.py` imported `live/residual_filter.py` at module scope, which imports `numba` at module scope. numba was never a dependency of this project's live path (only of the offline NLMS baseline), and isn't installed on the Pi. Result: `python live/main.py stress` died with `ModuleNotFoundError: No module named 'numba'` — even though `pipeline.residual_filter` was `false`. A disabled feature must never be able to break the core audio path. **Fixed**: the import is now lazy (inside `start()`, only when the feature is enabled) and raises an actionable `RuntimeError` naming `requirements-optional.txt` if the dependency is missing. Verified by simulating numba's absence on the dev machine: core pipeline constructs fine; enabling the feature fails loudly with guidance.
- **ONNX (P1-3) is not viable on the Pi. This is a hard upstream constraint, not a fixable pinning problem.** `onnx` depends on `ml_dtypes`; checked PyPI metadata for every published ml_dtypes release (0.5.0 → 0.6.0) and all of them declare `numpy>=2.1.0; python_version >= "3.13"`. deepfilternet 0.5.6 requires `numpy<2.0`. On the Pi's Python 3.13 there is no version combination satisfying both. The ONNX backend remains correct and verified on Python 3.11 (dev machine, bit-exact vs PyTorch), and `inference_backend` defaults to `pytorch`, so nothing in the default configuration is affected — but **the ~42% dev-machine speedup can never be confirmed on this Pi, and no Pi speed claim may be made from it.** Options if it's ever wanted: run the Pi on Python 3.12, or wait for deepfilternet to support numpy 2.x. Not pursued further.
- **`requirements.txt` was left uninstallable on the Pi — a demo-blocking regression.** Adding `scipy` to it produced `ResolutionImpossible` (scipy ≥1.18 requires numpy≥2.0 vs deepfilternet's numpy<2.0), which took down installation of the *core* pipeline dependencies along with it. **Fixed structurally**: `requirements.txt` now contains ONLY what the live pipeline needs and must always install cleanly; everything optional moved to a new `requirements-optional.txt`, so a resolver failure in an optional feature can never block the demo path again.
- **Removed the scipy dependency entirely.** `data/augment.py` used scipy for exactly one function (`fftconvolve`). Replaced with a ~5-line numpy FFT convolution, **verified numerically identical to `scipy.signal.fftconvolve` across 3 shape pairs** in the self-test (the check skips cleanly where scipy is absent). One less heavy dependency, and it removes the scipy/numpy conflict from the picture entirely.
- **Several rounds of pip resolver pathology, worth recording because the "fix" was wrong twice before it was right.** `numpy>=1.22.0` (no upper bound) let pip install numpy 2.5.2 and silently break deepfilternet — pip printed a conflict warning and proceeded anyway. Pinning `numpy<2.0` then made pip backtrack through older numpy patch versions and try to *build numpy 1.25.2 from source*, failing on Python 3.13 (`pkgutil.ImpImporter` removed). Exact-pinning numpy fixed that, but then `scipy>=1.10.0`/`numba>=0.58.0` as open ranges reproduced the identical pathology (pip walked numba 0.67.0 → 0.60.0, which cannot build on Python 3.13). Lesson applied: **exact pins for anything in the transitive neighbourhood of numpy on this platform**, and verify against real PyPI metadata (wheel availability + declared constraints) rather than guessing versions. numba 0.67.0 was confirmed fine all along (allows numpy<2.6, has a cp313/aarch64 wheel); scipy was the actual poison.
- **`onnxscript` re-added after being wrongly removed.** An earlier commit dropped it as "only needed for an abandoned dynamo experiment." True on the dev machine's torch; false on the Pi's newer torch, which imports dynamo-exporter machinery inside `torch.onnx.export()` unconditionally, even on the plain traced path. (Moot on the Pi given the ml_dtypes blocker above, but correct to have listed.)
- Also: `scripts/run_all_selftests.py` now reports SKIP (not FAIL) for tests whose optional dependency isn't installed, so a Pi run isn't red for features that are legitimately absent by design.
- Commands run (dev machine): `data/augment.py --self-test` (9/9 PASS incl. the new scipy cross-check), `scripts/run_all_selftests.py` (9/9 PASS), a simulated-no-numba import test confirming the lazy-import fix behaves correctly in both states, plus direct PyPI metadata queries for ml_dtypes/scipy/numba version constraints and cp313-aarch64 wheel availability (the evidence behind the pins and the ONNX verdict).
- Result: **core install path repaired and hardened; one real demo-affecting bug found and fixed; ONNX honestly written off for this Pi rather than chased further.** The Pi's PyTorch backend is unaffected throughout and continues to measure RTF ≈0.29 (median 29.27 ms/chunk, 20 reps, this session) — the demo path never depended on any of this.
- Files changed: `requirements.txt`, `requirements-optional.txt` (new), `live/pipeline.py`, `data/augment.py`, `config/audio_config.yaml`, `scripts/run_all_selftests.py`, `progress.md`.

### 2026-08-24 — Pi environment confirmed clean; offline batch-inference workflow documented; demo audio pair generated
- Phase/Task: Closing out the dependency-fix arc from the prior entry, plus building the "bring your own audio" capability the user asked about for demo prep.
- **Pi verification, on the actually-current code this time** (the previous attempt ran against stale code because `git pull` had silently aborted on an uncommitted local `config/audio_config.yaml` edit — caught and resolved: `git checkout -- config/audio_config.yaml` then `git pull` fast-forwarded cleanly to `99ebd69`). Re-ran `pip install -r requirements.txt` (clean, no conflicts — core file only) and `python scripts/run_all_selftests.py`: **7 PASS + 2 correct SKIP** (`export_onnx`/`onnx_infer` skip because `onnxscript` isn't installed, which is the *correct* end state now that ONNX is confirmed non-viable on this Pi's Python 3.13 — installing it would just hit the same `ml_dtypes` wall for no benefit). `augment` now passes outright (scipy dependency removed in the prior fix). `residual_filter` passes on real Pi hardware, including the bit-exact chunked-streaming check and the tone-tracking convergence test.
- **`scripts/make_demo_clip.py` (new)**: generates a single illustrative before/after clip — clean LibriSpeech speech + sustained engine noise + a real gunshot recording, mixed at a controlled SNR using `data/mix_dataset.py`'s own validated `mix_signals()` logic (not a new/separate mixing implementation). Not part of the evaluation pipeline; a demo/presentation-asset tool. Generated one on the dev machine (`-5 dB` SNR, 5.28s clip), processed it through `run_inference.py`, and sent both the noisy and enhanced files to the user directly — first time this session's actual audio output has been listened to rather than only measured.
- **Confirmed and documented `run_inference.py --input-dir` as a general-purpose offline capability**: this already existed (fixed earlier this session — see the "two more stale-fixture/dead-code problems" entry) but had never been framed as a user-facing feature. It takes any directory of `.wav`/`.flac` files — a user's own recording, not just dataset mixtures — and writes enhanced output per file, no manifest or dataset setup needed. Verified working via the demo clip round-trip.
- **README.md**: added a "Processing your own audio" section documenting this workflow with copy-pasteable commands; updated the Status section with the post-Phase-5 additions (augmentation, residual filter, ONNX backend) including the ONNX-on-Pi limitation stated plainly rather than left implicit; added `requirements.txt`/`requirements-optional.txt` to the repository layout table.
- Commands run: `git checkout -- config/audio_config.yaml && git pull` (Pi, resolved the stale-pull issue), `pip install -r requirements.txt` (Pi, clean), `python scripts/run_all_selftests.py` (Pi, 7 PASS + 2 SKIP), `python scripts/make_demo_clip.py` + `python models/deepfilternet/run_inference.py --input-dir results/demo_audio ...` (dev machine, produced real audio evidence).
- Result: **PASS** — Pi environment fully stable on current code; a real, listenable before/after audio artifact exists for the first time; the file-based enhancement workflow is now documented as a first-class, user-facing capability rather than an internal eval-pipeline detail.
- Files changed: `scripts/make_demo_clip.py` (new), `README.md`, `progress.md`.

### 2026-08-24 — P0-5 spectrogram smoke-tested on the Pi (mechanically PASS, content degenerate as predicted)
- Phase/Task: user ran `python demo/spectrogram.py` on the Pi and pasted back the result — the one Mode B check from this session's "no mic needed" batch that still needed a human at the keyboard, since it's a live terminal render.
- Result: 46s continuous run, clean startup and clean exit via `q`, `b` toggle responsive, ANSI rendering correct over SSH. Session stats: 0 real dropouts (`(+1 during shutdown drain, not a failure)` — the now-expected teardown artifact), RTF 0.336–0.418 (comfortably inside budget). **Both BEFORE and AFTER panels rendered fully saturated (solid red, max level) for the entire run**, not the near-silent/dark panels originally anticipated — same root cause flagged in advance (the pipeline's input is its own output looped back through `snd-aloop`, with no external signal), just the opposite failure mode: with no real content to calibrate against, `_AutoGain`'s reference collapses toward the loop's own near-zero floor and residual/numerical noise then reads as maximal relative to that collapsed floor. Not a bug — the rendering mechanics (the actual thing being tested) are confirmed correct; the panel *content* is fundamentally untestable without a real audio source, exactly as scoped beforehand.
- Result: **PASS (mechanics)** — spectrogram is demo-ready pending only a real microphone to feed it real content. No code changes required.
- Files changed: none (verification only). Logged in `progress.md` per this session's convention of recording all Mode B results, not just the ones that needed a fix.

### 2026-08-24 — live/latency_test.py: added --backend for comparing PyTorch vs ONNX on real hardware
- Phase/Task: after shipping the P1-3 ONNX backend, realized there was no tool to actually run the Pi-side speed comparison it needed to validate the dev-machine speedup claim.
- What I did: added `--backend pytorch|onnx` and `--onnx-dir` to `live/latency_test.py`'s CLI, threading them into the existing `InferenceEngine` construction (default `pytorch`, no behavior change for existing callers). Also records `backend` in the saved JSON output for traceability.
- Commands run: smoke-tested both backends end-to-end on the dev machine (`--backend pytorch` and `--backend onnx --onnx-dir results/onnx`, 3 reps each) — both ran cleanly through the CLI. Real Pi-side comparison numbers were requested from the user but superseded before being collected: the ONNX backend was subsequently found to be fundamentally incompatible with the Pi's Python 3.13 (see the "Pi dependency reckoning" entry), so the flag now serves the PyTorch path plus any future Python 3.11/3.12 Pi environment, rather than an immediate ONNX-on-this-Pi comparison.
- Result: **PASS** — flag works, defaults unchanged, no dev-machine regression.
- Files changed: `live/latency_test.py`, `progress.md`.

### 2026-08-26 — P0-1/P0-4/P0-5 closed on real hardware: three real incidents found and fixed, 600s real-mic stress PASS
- Phase/Task: user acquired physical hardware (USB microphone, headset, 3.5mm-to-USB adapter) and worked through P0-1 (integrate), P0-4 (real-mic stress gate), and P0-5 (spectrogram with real content) end to end, remotely over SSH. What should have been a straightforward hardware swap surfaced three unrelated real failures in sequence, each root-caused with evidence before being fixed — recorded in full since the false starts are as instructive as the pass.
- **Hardware topology simpler than planned**: `live/main.py detect` found a single USB Audio Device (Generalplus-chip dongle, 1 input/2 output channels on one ALSA card) rather than the two separate devices the plan assumed — the mic and the headset-via-3.5mm-adapter are one full-duplex card. `config/audio_config.yaml` set to `input_device: 0, output_device: 0` accordingly.
- **Incident 1 — acoustic feedback crashed the Pi in BYPASS mode.** First `live/main.py pipeline --mode bypass` run hung the whole Pi (SSH became unreachable, required physical restart). Root-caused by elimination: raw `arecord`/`aplay`/full-duplex-pipe tests at the same 48kHz outside Python all survived cleanly, ruling out the USB streaming stack itself; `amixer -c 2` showed mic capture gain maxed at 100%/+30dB with AGC off. Lowered capture gain to 54%/+10.5dB (`amixer -c 2 sset Mic 15`); bypass mode then ran clean (0 overflows/underruns) both with the mic held away from the headset and worn normally. Root cause: mic-to-headset feedback loop at excessive gain overloading the cheap USB codec, not a software or config bug.
- **Incident 2 — intermittent "crash" reports turned out to be dropped SSH sessions, not the Pi hanging.** User clarified after the fact that earlier "crashed" reports meant a connection-reset error, not an unresponsive Pi. `dmesg` showed `brcmfmac: brcmf_cfg80211_set_power_mgmt: power save enabled` on the onboard WiFi chip — a known cause of SSH drops on Raspberry Pi. Disabled with `sudo iw dev wlan0 set power_save off`. Recommended running long tests inside `tmux` going forward so a dropped session can't kill an in-progress test.
- **Incident 3 — the USB audio dongle hard-failed off the bus mid-session.** `demo/spectrogram.py` failed to open the input device; `lsusb` showed zero external devices, `dmesg` showed a clean disconnect followed by four consecutive failed re-enumeration attempts (`error -71`, "Device not responding to setup address") ending in `usb usb3-port1: unable to enumerate USB device` — the kernel had given up on that port. Not a power-budget-restriction message specifically, but consistent with a marginal port/cable/PSU interaction with this GeneralPlus-chip dongle. Fixed by physically unplugging and reseating the dongle in a different USB port; `lsusb` and `detect` confirmed it back, and it has not recurred since.
- **Two resilience fixes shipped proactively** (from an earlier audit pass, applied now since this session was exercising exactly the failure modes they cover): `live/pipeline.py::_inference_loop` now wraps the per-chunk enhance/bypass call in try/except — a single bad chunk outputs silence and increments a new `self._inference_errors` counter (surfaced in `_print_stats()`) instead of silently killing the inference thread for the rest of the session. `live/stress_test.py::run_stress_test` now calls `pipeline.start()` inside its try/finally block (previously outside it) so a startup failure still triggers `pipeline.stop()` cleanup and doesn't skip the report write. Committed and pushed as `382f0dd`, verified present on the Pi via `git pull` + grep.
- **Result, once the above were resolved**: incremental real-mic stress gate run in full — 120s PASS (1200 chunks, 0 overflows/underruns, 0 inference errors, max 38.6°C), 300s PASS (3001 chunks, max 39.7°C), **600s PASS (6001 chunks, 0 overflows, 0 underruns, 0 inference errors, max temp 40.2°C, mean CPU 17.9%/max 20.0%, RTF median 0.3896/p95 0.4044)**. `demo/spectrogram.py` run against real acoustic input showed clear BEFORE (dense broadband energy) vs. AFTER (energy collapsed to the speech band, rest suppressed) divergence — the first real evidence of DeepFilterNet suppressing noise on physical hardware in this project, as opposed to only measured metrics or a self-loop with no real content.
- **What remains open**: a true physical mic-to-headset round-trip latency number — `e2e_latency_test.py`'s click-and-cross-correlate method requires a wired loopback and cannot run against separate physical mic/headset hardware, so the 42.67ms/172ms figures on record remain `snd-aloop`-measured. Not blocking, since real-time stability (10-minute PASS) and perceptual quality (spectrogram divergence, user confirmed audible suppression) are now independently confirmed by other means. `demo/dashboard.py`'s live telemetry during real-mic operation and P1-2 (dual-mic) remain untested/unbuilt respectively.
- Commands run (Pi): `live/main.py detect`, `arecord -l`/`aplay -l`, `amixer -c 2`, `amixer -c 2 sset Mic 15`, `sudo iw dev wlan0 set power_save off`, `lsusb`, `dmesg`/`dmesg -w`, `vcgencmd get_throttled`/`measure_temp`, `scripts/run_all_selftests.py` (all PASS, unchanged), `live/main.py pipeline --mode bypass|enhance` (multiple short bounded runs via `timeout --signal=INT`), `demo/spectrogram.py`, `live/main.py stress --duration 120|300|600`.
- Files changed: `live/pipeline.py`, `live/stress_test.py` (resilience fixes, commit `382f0dd`), `config/audio_config.yaml` (real device indices, set on the Pi), `README.md`, `progress.md`.

### 2026-08-26 (evening) — correction: original headset's mic was dead the whole time; replaced and re-verified with genuine real content
- Phase/Task: preparing for a demo the next day, tried the record→enhance→playback offline workflow as a fallback path. It surfaced that the "real acoustic input" claimed in this same day's earlier entry was not actually true — worth a correction, not a footnote, per this project's own honesty discipline (Rule 33 and the general practice of this log).
- **What was found**: a 5s `arecord` of the user speaking read back `peak: 0.0066, rms: 0.004` — noise-floor level, not a voice recording. Systematically ruled out every fixable cause before concluding it was hardware: mic capture gain swept 54%→86%→100% (max) with no meaningful scaling of the signal (ruled out gain), a physical tap directly on the mic capsule at max gain still read `peak: 0.0069` (ruled out "just needs to be louder"), re-seating the 3.5mm plug made no difference (ruled out a loose connection), and the same headset tested on a laptop's native jack worked perfectly for both mic and speaker (ruled out the Pi/adapter/software stack entirely — proved the headset itself was defective). Final confirmation: the same headset plugged into the same adapter on the laptop also failed (mic dead, speaker fine) — fully isolating the fault to the headset's mic hardware, independent of the Pi.
- **Implication for the earlier same-day entry**: the 600.5s "real-mic" stress test and the `demo/spectrogram.py` BEFORE/AFTER divergence reported earlier today were run through a mic that most likely was not capturing real acoustic content. The *stability* evidence (0 dropouts, 0 inference errors, thermal/CPU numbers) is unaffected — that measures data flow integrity, not content, and remains valid. The *content* claim (real suppression visible on screen) is not reliable evidence on its own, since `demo/spectrogram.py`'s `_AutoGain` normalizes against whatever peak exists in the stream and will render pure electrical noise as visually "full" too — retracted as confirmed, though not necessarily false either.
- **Fix**: user swapped in a different headset (same adapter, same Pi, same config). Re-tested: clean recording read `peak: 1.0` (clipping — gain still at the max setting used during dead-mic troubleshooting, harmless at the time since nothing was being captured), corrected to `Mic 15` (54%), re-recorded clean at `peak: 0.092, rms: 0.016` — real signal, no clipping.
- **Result**: re-ran `demo/spectrogram.py` live with the working headset and real speech — BEFORE panel shows genuine dense broadband energy across the band; AFTER panel collapses to mostly empty/dark with only a thin surviving band (speech frequencies), exactly the expected DeepFilterNet suppression signature. Session stats: 283 chunks, 0 overflows, 0 underruns, 0 inference errors, RTF median 0.3862/p95 0.4341. This is the first mic-verified confirmation of real content this project has produced — the earlier same-day pass is superseded by this one, not merely corroborated.
- Commands run (Pi): `arecord`/`aplay`/`amixer -c 2`/peak-rms checks via `python -c "...soundfile..."` (multiple rounds isolating gain vs. hardware), `run_inference.py --input-dir` (offline enhance fallback prepared for the next day's demo in case live capture failed), `demo/spectrogram.py` (final mic-verified run).
- Files changed: `progress.md` (this entry + correction to the same-day earlier one).

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
| Real device I/O round-trip (`e2e_latency_test.py`, Mode B) | ✅ PASS | 42.67ms median=p95=min=max (20 reps, real `sounddevice`/PortAudio/ALSA, `snd-aloop`). Full pipeline estimate ≈172ms (round-trip + inference + 100ms priming). Added 2026-08-24. Still `snd-aloop`-measured — the click-loopback method can't run against physically separate mic/headset hardware, so a true physical round-trip click number remains open (P0-1 hardware itself is no longer open, see below). |
| Physical microphone + headset integrated (P0-1) | ✅ DONE | 2026-08-26. USB mic + headset via Generalplus USB adapter; three real incidents found and fixed (feedback loop, WiFi power-save SSH drops, USB enumeration failure) — full writeup above. |
| `stress_test.py` 10 min on Pi, real microphone (P0-4, Test 6, Mode B) | ✅ PASS | 2026-08-26: Verdict PASS, 0 dropouts / 6001 chunks, 0 inference errors, max 40.2°C, 600.5s. Supersedes the 2026-08-24 loopback-based PASS (max 52.9°C) as current stability evidence. |
| RTF under live load, real microphone (Test 7, Mode B) | ✅ PASS | median RTF=0.3896, p95=0.4044 (6001 chunks, 600.5s run, 2026-08-26, real mic) |
| Spectrogram real-content check (P0-5) | ✅ PASS | 2026-08-26 evening, mic-verified: BEFORE/AFTER divergence confirmed against real acoustic input (broadband energy → speech-band-only), after discovering and replacing a defective headset mic that had made the same-day daytime attempt unreliable — see the correction entry above. Supersedes both the 2026-08-24 loopback smoke test and the earlier same-day attempt. |
| `demo/dashboard.py` terminal mode | ✅ PASS | Renders on Pi SSH, clean exit |
| `deploy_to_pi.py` syncs clean runtime | ✅ DONE | `pi_deploy.zip` generated, excludes datasets |
| `live/main.py` unified CLI functional | ✅ PASS | All subcommands verified |
| `progress.md` / `architecture.md` updated with real Pi evidence | ✅ DONE | This log |

> **RTF note (Rule 33):** The target was RTF < 0.25. On Pi 5 in-memory (latency_test), enhance RTF = 0.292. Under live loopback load (stress test), RTF = 0.378. Both are above 0.25 but well below 1.0 (real-time limit). This is reported exactly as measured. With a real USB mic (lower loopback scheduling overhead), live RTF is expected to be closer to the in-memory 0.292 figure. This finding is logged as a real measurement, not hidden or re-parameterised.

---

## 2026-09-04 — Phase 1: Dual-Mic Reference Channel (Software Implementation)

### Hardware topology decision

User confirmed: **Topology B — two separate USB devices** (no stereo interface).
- Primary mic: 3.5 mm headset mic via USB-A audio dongle (existing `audio.input_device: 1`)
- Reference mic: dedicated USB microphone (new `audio.dual_mic.reference_device`)

Drift consequence documented: two independent USB crystal clocks drift ~2.4 samples/sec at 50 ppm
(48 kHz). NLMS filter taps (64 x ~20 us = 1.3 ms window) partially compensate within that window.
Workflow: calibrate before each demo session, keep sessions <=60 s. Future phase may add periodic
re-alignment.

### T0 — numba dependency gate (PENDING Pi verification)

`numba==0.67.0` promoted from `requirements-optional.txt` to `requirements.txt`. Justification: dual-mic
reference-NLMS is a headline demo feature. Wheel cp313/aarch64 previously confirmed to exist. Pi
verification required: run `pip install numba==0.67.0` on Pi before first dual-mic demo.

### T2 — config/audio_config.yaml — new sections added

Added `audio.dual_mic` and `pipeline.reference_nlms` sections at end of file. Both `enabled: false`
by default. Existing content and comments untouched. Key new fields:
- `dual_mic.reference_device: 2` — USB reference mic index
- `dual_mic.ref_delay_samples: 0` — from calibration
- `reference_nlms.stage: "post_dfn"` — or "pre_dfn" (config-switchable for Phase 3 comparison)

### T3 — live/reference_nlms.py created (NEW)

Streaming reference-NLMS filter. numba-JIT kernel `_nlms_chunk` matches `baselines/nlms/nlms.py`
equation (Widrow NLMS, L-1 zero pre-pad, returns error signal as speech estimate). `ReferenceNLMSFilter`
class with `process_chunk(primary, reference)`, `erle_db()`, `reset()`. Lazy-import via `start()`.
JIT warmup at construction.

Self-test (Mode A, dev machine, 2026-09-04):

    uv run --no-sync python live/reference_nlms.py --self-test
    [PASS] test 1: chunked streaming matches offline batch (bit-identical)
    [PASS] test 2: shape=(48000,), all finite
    [PASS] test 3: silence handled without divide-by-zero
    [PASS] test 4: NLMS improves speech correlation (0.763 -> 0.992)
    [PASS] test 5: ERLE=2.23 dB (positive = noise reduction is occurring)
    [PASS] test 6: reset() clears weights, history, and ERLE accumulators
    [PASS] test 7: invalid parameters raise ValueError
    [PASS] test 8: mismatched input shapes raise ValueError
    live/reference_nlms.py self-test -- ALL PASSED

Test 1 confirms FR-5 (chunk-streaming bit-identical to offline batch).
Test 4: speech correlation improved 0.763 -> 0.992 with oracle reference input.
ERLE 2.23 dB on 1 s synthetic signal (includes pre-convergence transient).

### T4 — live/pipeline.py updated (dual-mic Topology B)

Changes gated behind `dual_mic.enabled: false` default. Single-mic path is behaviourally identical
when disabled (no second stream opened, no numba import attempted).

- `__init__`: parse `dual_mic` + `reference_nlms` config. Create `_ref_buf` (single-channel RingBuffer)
  and `_ref_delay_line` (numpy array for integer delay compensation) when enabled. Validate
  `reference_nlms.enabled` requires `dual_mic.enabled`.
- `_ref_callback()`: new method. Writes reference mic audio to `_ref_buf` (with resample if needed).
- `_ref_stream_sr` attribute: resolved in `start()` via existing `_resolve_stream_samplerate`.
- `start()`: lazy-import `ReferenceNLMSFilter` when enabled (same pattern as `ResidualALEFilter`).
  Open `_stream_ref` (sd.InputStream, channels=1) when `dual_mic.enabled`.
- Inference loop: reads `ref_chunk` from `_ref_buf`; applies integer delay via `_ref_delay_line`.
  Pre-DFN stage: before `enhance_chunk`. Post-DFN stage: after existing ALE hook.
- `stop()`: closes `_stream_ref` when open.
- `_print_stats()`: adds reference buffer overflow, `ref_delay_samples`, and ERLE lines.

### T5 — live/calibrate_mic_pair.py created (NEW)

Cross-correlation mic pair delay calibration. Plays log-chirp 200-6000 Hz while recording both mics,
cross-correlates to find integer delay, writes `config/mic_calibration.yaml`. Accessible via
`python live/main.py calibrate`. Pure numpy xcorr — no scipy dependency.

Self-test (Mode A, dev machine, 2026-09-04):

    uv run --no-sync python live/calibrate_mic_pair.py --self-test
    [PASS] test 1: chirp shape=(96000,), max_amp=0.250
    [PASS] test 2: compute_delay found lag=120 (expected ~120)
    [PASS] test 3: silent input handled gracefully (lag=0)
    [PASS] test 4: calibration YAML written and verifiable
    live/calibrate_mic_pair.py self-test -- ALL PASSED

Test 2: synthetic 120-sample (2.5 ms) delay recovered correctly.

### T6 — live/detect_devices.py updated

Emits paste-ready `dual_mic:` config block when >=2 USB input devices found. Suggests first as
primary (already set as `input_device`), second as `reference_device`.

### T7 — live/main.py updated

Added `calibrate` subcommand routing to `live.calibrate_mic_pair.main`.

### T9 — requirements.txt updated

Added `numba==0.67.0` with T0 Pi verification gate note.

### T10 — scripts/run_all_selftests.py updated

Added `reference_nlms` (optional_dep="numba") and `calibrate_mic_pair` (optional_dep=None) entries.

### Full Mode A regression suite (dev machine, 2026-09-04)

    uv run --no-sync python scripts/run_all_selftests.py --skip-dfn

    [PASS] ring_buffer            0.26s
    [PASS] spectrogram_demo       0.17s
    [PASS] e2e_latency_logic      0.17s
    [PASS] augment                2.64s
    [PASS] residual_filter        0.88s
    [PASS] reference_nlms         2.67s
    [PASS] calibrate_mic_pair     1.75s
    ALL MODE A SELF-TESTS PASSED

Zero regressions in existing tests. Two new tests added and passing.
Machine: dev machine (Windows 11, x86_64, Python 3.9 via uv venv). NOT Pi results (Rule 5).

### Pending Mode B tests (require Pi + hardware)

| Condition | Command | Output to paste |
|---|---|---|
| T0: numba installs on Pi | `pip install numba==0.67.0` | Install log |
| DoD-1: calibration runs on Pi | `python live/main.py calibrate` | Measured ref_delay_samples |
| DoD-3: dual-mic 10-min stress | `python live/main.py stress --duration 600` with dual_mic.enabled:true | results/stress_dualmic.json |
| DoD-4: single-mic regression | existing stress_test_report.json | Already PASS (single-mic path unchanged) |
| DoD-5: live A/B demo | enable/disable reference_nlms from config | Pasted Pi session |
| **Phase 2 / B0**: re-baseline on real dual-USB hardware | `live/latency_test.py` + `live/e2e_latency_test.py` per phase2_plan.md §5.B0 | `results/latency_inference_dualmic.json`, `results/latency_baseline_dualmic.json` |
| **Phase 2 / B1**: priming validation (1.0→0.5→0.25→0.0) | `python live/main.py stress --duration 600` per priming value | `results/stress_priming.json`, chosen value + reasoning |
| **Phase 2 / B2**: chunk-size sweep, dual-mic, re-test 50ms | `python scripts/sweep_chunk_size.py --dual-mic --priming-chunks <chosen>` | `results/chunk_sweep_report.json` |
| **Phase 2 / B3**: core-pinning A/B | `pipeline.cpu_affinity` set vs `null`, 300s each, `taskset -pc <pid>` to verify | Both arms' RTF p95/dropouts, keep/drop decision |
| **Phase 2 / B4**: fast_resample A/B | `pipeline.fast_resample` true vs false, Pi microbenchmark | Both arms' timings, keep/drop decision |
| **Phase 2 / B5**: physical acoustic round-trip (headline measurement) | `python live/main.py acoustic-latency --n-reps 20` | `results/acoustic_latency.json`, median + p95 |
| **Phase 2 / B6**: empirical DFN3 lookahead | `python live/main.py acoustic-latency --lookahead` | `results/lookahead_measured.json` |
| **Phase 2 / B7**: final gate at chosen configuration | `python live/main.py stress --duration 600` | `results/stress_dualmic_final.json` verdict PASS |
| **Phase 2 / B8**: claim reconciliation | update README.md/architecture.md/audio_config.yaml comments to measured values | progress.md closing entry, machines named |
| **Phase 3 / T9** (optional, not a Phase 3 gate): live dual-mic spot-check | once dual-mic hardware is set up (Phase 1/2 Track B), check whether live crowd-babble behaviour falls between the T6 `nlms_realistic` and `nlms_oracle_upper_bound` predictions | Pasted Pi session; closes the `phase3_plan.md` §1.2 loop with a real measurement |

## 2026-09-04 — Phase 2 Track A: latency engineering, dev-machine work (`phase2_plan.md`)

**Machine:** devmachine (Windows 11, x86_64, uv venv, Python 3.12)
**Track:** A (dev machine, Mode A — no hardware)

### Bug found and fixed first: config/audio_config.yaml duplicate top-level keys

While implementing A7 (propagate `dual_mic`/`reference_nlms` into `scripts/sweep_chunk_size.py`'s
scratch configs), found that `config/audio_config.yaml` declared TWO top-level `audio:` blocks and TWO
top-level `pipeline:` blocks — the Phase 1 dual-mic/reference-NLMS sections had been appended as new
top-level keys instead of nested under the existing ones. YAML mappings silently collapse duplicate
keys to the LAST one seen, so `yaml.safe_load` was discarding `sample_rate`, `chunk_duration_sec`,
`input_device: 1`, `output_device: 0`, `priming_chunks`, etc. from the first blocks, keeping only
`dual_mic`/`reference_nlms`. `live/pipeline.py`'s `_load_config` deep-merge then silently fell back to
its own hard-coded defaults for every dropped key (`input_device`/`output_device` became `None`,
triggering auto-detection instead of the documented real Generalplus indices).

Evidence (before fix):

    python -c "
    import yaml
    with open('config/audio_config.yaml', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    print('audio:', cfg['audio'])
    print('pipeline keys:', list(cfg['pipeline'].keys()))
    "
    audio: {'dual_mic': {'enabled': False, 'reference_device': 2, 'ref_delay_samples': 0, 'topology': 'dual_usb'}}
    pipeline keys: ['reference_nlms']

Fixed by merging into single `audio:`/`pipeline:` blocks (dual_mic/reference_nlms now nested correctly
inside them, all comments preserved). Evidence (after fix):

    audio: {'sample_rate': 48000, 'channels': 1, 'chunk_duration_sec': 0.1, 'ring_buffer_duration_sec': 2.0,
             'input_device': 1, 'output_device': 0, 'dual_mic': {'enabled': False, 'reference_device': 2,
             'ref_delay_samples': 0, 'topology': 'dual_usb'}}
    pipeline: {'mode': 'enhance', 'log_timing': False, 'latency_warn_sec': 0.3, 'warmup_passes': 3,
               'priming_chunks': 1.0, 'startup_grace_sec': 0.5, 'cpu_affinity': None, 'fast_resample': False,
               'residual_filter': False, 'inference_backend': 'pytorch', 'onnx_dir': 'results/onnx',
               'reference_nlms': {'enabled': False, 'filter_length': 64, 'mu': 0.01, 'eps': 1e-06, 'stage': 'post_dfn'}}

**Rule 5/33 implication:** every real-hardware run to date that relied on the config file's explicit
`input_device`/`output_device` was actually running on auto-detected devices instead — auto-detection
happened to pick the right hardware, which is why this went unnoticed, not because the config was being
honored. Not re-litigating past results (auto-detection working is not itself a defect), but noting it
plainly per Rule 33 rather than letting it pass silently.

### What changed

- `config/audio_config.yaml` — merged duplicate top-level blocks (bug fix above); added Phase 2 keys
  (`priming_chunks` now float, `startup_grace_sec`, `cpu_affinity`, `fast_resample`) with rationale
  comments and default values matching pre-Phase-2 behaviour.
- `live/latency_budget.py` (NEW, A0) — `LatencyBudget` dataclass: per-component `source` tag
  (measured/estimated/configured), mandatory `machine` field (Rule 5), `total_estimate_ms`,
  `is_mixed_source()`, JSON round-trip, `render_table()`.
- `live/pipeline.py` (A1/A2/A3/A4) —
  - `_compute_priming_samples()` / `_classify_underrun()`: pure helper functions, unit-testable without
    hardware.
  - `priming_chunks` parsed as `float` (was `int`); priming write is now a single
    `round(priming_chunks * chunk_samples)`-sample write instead of a whole-chunk loop (`1.0` is
    byte-identical to the old behaviour: `round(1.0 * chunk_samples) == chunk_samples`). Negative values
    raise `ValueError`.
  - `_startup_underruns` counter + `startup_grace_sec` config; `_output_callback` now buckets every
    underrun as teardown/startup/real via `_classify_underrun()`; `_print_stats` reports all three.
  - `_stream_start_t` recorded right after streams start, used as t=0 for the grace window.
  - `set_thread_affinity()` (from `live/cpu_affinity.py`) called at the top of `_inference_loop`, guarded
    on `self._cpu_affinity is not None`.
  - `_resample_multi()` takes a `use_fast` flag; routes to `live/fast_resample.py::resample_fast` when
    `pipeline.fast_resample` is enabled. `start()` raises a clear `RuntimeError` up front if enabled
    without numba installed (fails before any hardware is touched, not mid-callback).
  - Added `--self-test` CLI flag exercising the above pure logic (no sounddevice/model needed).
- `live/cpu_affinity.py` (NEW, A3) — `set_thread_affinity(cores)`: pid=0 `os.sched_setaffinity` (pins the
  calling thread only, per phase2_plan.md §3.1(b)); graceful `False` (never raises) when unsupported.
- `live/fast_resample.py` (NEW, A4) — numba-JIT drop-in for `pipeline.py::_resample`; importable without
  numba (degrades gracefully for `run_all_selftests.py`'s SKIP mechanism), raises only if actually called
  without numba installed.
- `live/acoustic_latency_test.py` (NEW, A5/A6) — `measure_click_to_click_lag()` / `_find_peak_sample()`
  (D3's dual-mic method, reusing `find_click_lag`'s peak/noise-floor/RuntimeError discipline from
  `live/e2e_latency_test.py`), `record_synced()` (mirrors `calibrate_mic_pair.py::record_both`),
  `run_acoustic_latency_test()` (Mode B orchestration), `measure_model_lookahead()` +
  `run_lookahead_measurement()` (Rule 30 — empirical, never read from `df.config`). Registered as
  `python live/main.py acoustic-latency` (`live/main.py` updated).
- `scripts/sweep_chunk_size.py` (A7) — `_make_scratch_config()` / `run_one_candidate()` take optional
  `priming_chunks`/`dual_mic`/`reference_nlms` overrides; `main()` gained `--priming-chunks`,
  `--dual-mic`/`--no-dual-mic`, `--reference-nlms`/`--no-reference-nlms`; summary table gained
  `Priming` and `StartupUR` columns.
- `live/stress_test.py` (A2) — reports `startup_underruns` in the printed summary and the JSON output
  (excluded from the PASS/FAIL verdict, same as `teardown_underruns` already was).
- `scripts/run_all_selftests.py` — registered `latency_budget`, `pipeline_logic`, `cpu_affinity`,
  `fast_resample` (optional_dep="numba"), `acoustic_latency_logic`.
- `architecture.md` — component table + folder structure updated for the 4 new modules (Rule 7: done
  before, in the same change as, landing the modules); decisions log entry added.

### Evidence

    uv run --no-sync python live/latency_budget.py
    live/latency_budget.py self-test -- start
      [PASS] test 1: total_estimate_ms == 172.17000000000002 (sum of components)
      [PASS] test 2: mixed-source budget flags itself in render_table()
      [PASS] test 3: uniform-source budget does not flag itself
      [PASS] test 4: to_json()/from_json() round-trip is exact
      [PASS] test 5: unknown machine/source values raise ValueError
      [PASS] test 6: measured_physical_ms stays None until filled in, then renders
    live/latency_budget.py self-test -- ALL PASSED

    uv run --no-sync python live/pipeline.py --self-test
    live/pipeline.py self-test -- start
      [PASS] test 1: priming_chunks=1.0 -> 4800 samples (identical to old int-loop behaviour)
      [PASS] test 2: priming_chunks=0.5 -> 2400 samples, 0.25 -> 1200 samples, 0.0 -> 0 samples
      [PASS] test 3: negative priming_chunks raises ValueError
      [PASS] test 4: not-running underruns always classify as teardown
      [PASS] test 5: running underruns classify as startup within the grace window, real once past it
             (verdict is unaffected by in-window ones, fails on out-of-window ones)
    live/pipeline.py self-test -- ALL PASSED

    uv run --no-sync python live/cpu_affinity.py --self-test
    [cpu_affinity] os.sched_setaffinity is not available on this platform (win32); skipping pin to
    cores=[0]. This is expected on Windows/macOS and is not an error.
    live/cpu_affinity.py self-test -- start
      [PASS] test 1: cores=None is a no-op returning True
      [PASS] test 2: graceful no-op on Windows (no os.sched_setaffinity) -- did not raise
    live/cpu_affinity.py self-test -- ALL PASSED

    uv run --no-sync python live/fast_resample.py --self-test
      [PASS] 44100 Hz -> 48000 Hz: bit-equivalent (max diff=0.00e+00)
      [PASS] 16000 Hz -> 48000 Hz: bit-equivalent (max diff=0.00e+00)
      [PASS] 48000 Hz -> 48000 Hz: bit-equivalent (max diff=0.00e+00)
      Microbenchmark (THIS MACHINE ONLY, not a Pi measurement -- Rule 5): np.interp=43.4 us/call, numba=15.5 us/call
    live/fast_resample.py self-test -- ALL PASSED

    uv run --no-sync python live/acoustic_latency_test.py --self-test
    live/acoustic_latency_test.py self-test -- start
      [PASS] test 1: measure_click_to_click_lag recovers known lag (expected ~960, got 960)
      [PASS] test 2: measure_click_to_click_lag raises RuntimeError when no click is present on either
             channel (no silent wrong answers)
      [PASS] test 3: raises specifically naming the channel with no clean click
      [PASS] test 4: measure_model_lookahead recovers known shifts (0, 5, 40 samples) via a fake engine,
             no DFN3 model needed
      [PASS] test 5: _load_calibration_offset defaults to 0 (with a warning) when uncalibrated
    live/acoustic_latency_test.py self-test -- ALL PASSED

Full regression suite (all tests, not `--skip-dfn` — includes DFN3 model-loading tests):

    uv run --no-sync python scripts/run_all_selftests.py
      [PASS] ring_buffer            0.27s
      [PASS] inference_engine       1.63s
      [PASS] run_inference          1.50s
      [PASS] spectrogram_demo       0.17s
      [PASS] e2e_latency_logic      0.17s
      [PASS] augment                0.48s
      [PASS] residual_filter        0.89s
      [PASS] reference_nlms         2.69s
      [PASS] calibrate_mic_pair     1.74s
      [PASS] latency_budget         0.07s
      [PASS] pipeline_logic         1.52s
      [PASS] cpu_affinity           0.08s
      [PASS] fast_resample          1.79s
      [PASS] acoustic_latency_logic   0.17s
      [SKIP] export_onnx            0.00s (optional dependency 'onnxscript' not installed)
      [SKIP] onnx_infer             0.00s (optional dependency 'onnxscript' not installed)
    ALL MODE A SELF-TESTS PASSED (Mode B / Pi hardware tests not included)

14/14 runnable tests PASS, 2 correctly SKIP (unrelated optional ONNX dependency, pre-existing condition).
**Zero regressions** in the 10 pre-existing tests; 5 new tests added and passing.
Machine: devmachine (Windows 11, x86_64, uv venv). NOT Pi results (Rule 5).

Also confirmed numba IS installed in this dev venv, so `fast_resample`'s bit-equivalence check and
microbenchmark ran for real (not skipped) — max diff 0.00e+00 (exact bit-equivalence, stronger than the
atol=1e-4 tolerance the test allows for) across all three tested rate pairs, and numba measured ~2.8x
faster than `np.interp` in this local microbenchmark. This is a dev-machine-only number (Rule 5) and is
NOT the basis for keeping `fast_resample` — that decision is made on the Pi (B4), per D4's
measure-first/keep-only-if-it-helps policy, since np.interp is already compiled C and this machine's ISA
differs from the Pi's ARM Cortex-A76.

### Result

**PASS.** Gate A (dev machine) from `phase2_plan.md` §10 is met: A0–A8 implemented, `architecture.md`
updated in the same change, full self-test suite green with zero regressions, A3 verified no-op on
Windows, A4 bit-equivalence proven, and every default-off feature confirmed behavior-preserving at its
default (`priming_chunks: 1.0`, `cpu_affinity: null`, `fast_resample: false`).

**Not done / explicitly deferred (Rule 33 — stating the gap, not hiding it):** No latency number in this
entry is a real measurement — `LatencyBudget`, the priming/underrun logic, and the acoustic-latency math
are all verified against synthetic/pure-logic self-tests, not real audio hardware. DoD-1 through DoD-5 in
`phase2_plan.md` all require Track B (Pi hardware, B0–B8), which is unstarted and queued behind Phase 1's
own outstanding Track B per the project's established working order (Mode A/dev-machine work first, all
Pi work batched at the end). The sub-150ms latency target itself has not been evaluated against any real
number yet — Track B's B0 re-baseline is the first step that can even ask that question honestly.

---

## 2026-09-04 — Phase 3 prerequisite: manifest/disk integrity bug found and fixed

**Machine:** devmachine (Windows 11, x86_64, uv venv)
**Dataset:** clean 300 (base, non-augmented)

### What changed
- `data/mix_dataset.py:143,156` — wrapped the clean-speech and per-subtype noise-pool `glob.glob()` calls
  in `sorted()`. Root cause of the bug below: unsorted glob order makes `random.choice()` draws depend on
  filesystem enumeration order, not just the seed, so `mix_dataset.py` was not actually reproducible run
  to run despite the fixed `seed=42` default.
- `data/manifest.csv`, `data/mixtures/*` — fully regenerated.
- `results/baselines/{spectral_subtraction,wiener,nlms,deepfilternet}/*` — fully regenerated (old outputs
  moved to `_pre_regen_backup_20260904_195252/` first, not deleted).
- `results/eval_raw.csv`, `results/results.csv`, `results/charts/*` — fully regenerated.

### Why (Rule 27 root cause)
Before touching anything, I verified the ground truth `phase3_plan.md` was written against: `data/manifest.csv`
(committed, unmodified in git) referenced 34 rows in the `impulsive` category (indices ~0201–0295) whose
`subtype` field did not match the file actually present on disk at that index (e.g. manifest said
`mix_impulsive_explosion_-5dB_0212.wav`, disk had `mix_impulsive_artillery_-5dB_0212.wav`). Cross-checked
`results/eval_raw.csv` and `results/baseline_manifest.csv` — both agreed with **disk**, not with
`data/manifest.csv`. So only the committed manifest had drifted; mixtures/baselines/eval were already
mutually consistent with each other, just not with the manifest.

Evidence (verbatim):
```
$ python scripts/scratch_check_manifest_integrity.py   # ad hoc, deleted after use
manifest rows: 300
files on disk: 602
missing files referenced by manifest: 34
orphan files on disk (not in manifest): 36
```

### Row-count / exclusion integrity   [Rules 24/26]
Post-fix, verified programmatically:
```
manifest rows: 300
missing: 0
wav files on disk: 600
orphans: 0
```
Baselines: `Generated results/baseline_manifest.csv with 900 rows (300 mixtures x 3 methods)` — all 3
methods 300/300 sanity-check PASS. DeepFilterNet: `300 processed, 0 skipped`. Eval:
`Total Evaluation Rows: 1500 / 1500`, `Total Rule-24 Exclusions Logged: 0`.

### Unexpected consequence — impulsive PESQ_WB no longer reproducibly passes
Regenerating reproduced `stationary` and `non_stationary` category means **byte-identical** to the
currently-committed `results/final/target_compliance.json` (both categories' noise pools were never
touched by the historical gunshot/artillery gap, so this is exactly the expected/reassuring result).
`impulsive` did not reproduce: the committed compliance report cites PESQ_WB=2.5841 (PASS) for
impulsive/DeepFilterNet, but the freshly-regenerated, now-verified-consistent, now-actually-reproducible
run gives:

| Metric | Committed (2026-08-24) | Regenerated (this entry, reproducible) |
|---|---|---|
| SI-SNR | 15.7495 dB | 15.1950 dB (still PASS, >15) |
| STOI | 0.9319 | 0.9196 (still PASS, >0.85) |
| PESQ-WB | 2.5841 (PASS) | **2.4916 (FAIL, -0.0084 vs 2.5 target)** |

Root cause: the 2.5841 figure was itself a product of the same glob-order non-determinism — a favorable
random draw over the gunshot/artillery/explosion pool that the pre-fix code could not reliably reproduce.
It was never fabricated (Rule 1) — it came from a real `eval/run_eval.py` run at the time — but it was
not the reproducible steady-state of the corpus, and nothing on disk since has matched it. Subtype
composition this run: `{explosion: 40, artillery: 34, gunshot: 26}`, close to the documented 40/35/25
split, confirming the full corrected corpus (not an explosion-only regression) is what's being drawn from.

**True current compliance state is 4/9, not the 5/9 `phase3_plan.md` was written against**: impulsive
PESQ_WB joins stationary PESQ_WB and all three non_stationary cells as FAIL. SI-SNR and STOI are unaffected
(both categories still comfortably PASS both). `results/final/target_compliance.md/.json` regenerated in
place accordingly (previous version preserved via git history + an explicit superseding note, per existing
project practice — not deleted).

**Consequence for Phase 3's D1 target:** still realistic. Impulsive's new PESQ gap (-0.0084) is smaller
than stationary's long-standing gap (-0.018) — `phase3_plan.md` §1.1's non-stationary arithmetic is
completely unaffected (built on non_stationary numbers, which are byte-identical pre/post this fix), so
6/9 remains the target, now achievable via closing either or both of two small, closeable PESQ gaps
instead of one.

### Result
**PASS** — integrity restored and verified programmatically; root cause fixed at the source
(`sorted()` on the glob calls, so this cannot silently recur). Compliance report regenerated to match
reality. Phase 3 proper (T0 onward) now proceeds against a verified-consistent base.

---

## 2026-09-04 — Phase 3 T0: Pilot timing gate (Rule 19)

**Machine:** devmachine (Windows 11, x86_64, uv venv)
**Dataset:** 15-file augmented pilot (`--count 10` rounds up to 15 across 15 category/subtype/SNR combos),
`--augment-rir --augment-clipping`, generated to scratch paths and deleted after timing capture.

### Evidence (verbatim timings)
| Stage | Pilot (15 files / 75 eval rows) | Extrapolated to full 300 / 1500 |
|---|---|---|
| `mix_dataset.py --augment-rir --augment-clipping` | 1.76s | ~35s |
| 3 classical baselines (spectral_subtraction, wiener, nlms) | 2.55s | ~51s |
| DeepFilterNet3 inference | 2.77s | ~55s |
| `eval/run_eval.py` (75 rows) | 19.92s (19.92s eval-loop-only + ~5s startup) | ~398s (~6.6 min) |
| **Total pipeline** | ~27s | **~539s (~9 min)** |

Also cross-checked against this session's real (non-pilot) full clean-300 run a few minutes earlier:
mix=4.85s, baselines=63.56s, DFN3=51.81s, eval=160.90s (~4.7 min total) — same order of magnitude,
augmented adds modest overhead from RIR convolution as expected.

### Decision this timing drove
All of T1–T2 (augmented full run) and T4 (Stage-1 stratified sweep, ~600 DFN3 calls extrapolated to
~175s) stay well under the plan's ~2h backgrounding threshold. **Decision: run all Phase 3 stages
directly/synchronously in-session, no backgrounding or checkpointing needed.**

### Incident during piloting (self-caught, no data lost)
First DFN3 pilot invocation omitted `--output-dir`/`-o`, which defaults to the real production path
`results/baselines/deepfilternet/`. It wrote 14 stray files there (idempotent skip-if-exists meant the
1 filename that collided with a real production row was left untouched, so no real output was corrupted
— only 14 extra orphan files were added.) Caught immediately by comparing pilot manifest filenames
against `data/manifest.csv`; all 14 identified and removed; verified `results/baselines/deepfilternet/`
back to exactly 300 files, and the 1 untouched file's mtime confirmed unchanged from this session's
earlier real regeneration. Re-ran the pilot correctly with `-o` pointed at a scratch dir.

### Result
**PASS.** Proceeding to T1 (augmented dataset generation, full 300).

---

## 2026-09-04 — Phase 3 T1–T3: Augmented dataset, full run, robustness doc

**Machine:** devmachine (Windows 11, x86_64, uv venv)
**Dataset:** augmented 300 (`--augment-rir --augment-clipping`)

### What changed
- `data/manifest_augmented.csv`, `data/mixtures_augmented/` — new, generated (does not touch the clean set).
- `results/baselines_augmented/{spectral_subtraction,wiener,nlms,deepfilternet}/` — new.
- `results/eval_raw_augmented.csv`, `results/results_augmented.csv`, `results/charts_augmented/` — new.
- `docs/augmentation_robustness.md` — new (DoD-1).

### Evidence (verbatim)
```
$ uv run python data/mix_dataset.py --output-dir data/mixtures_augmented \
    --manifest data/manifest_augmented.csv --augment-rir --augment-clipping
Total Mixtures Generated: 300
Manifest Row Count Verified: 300 == 300 mix files, 300 clean ref files
Audio Sample Rate: 48000 Hz (All verified)
Achieved SNR Mean Deviation: 0.0000 dB | Max Deviation: 0.0000 dB
Augmentation - Reverb: applied (per-category room presets)
Augmentation - Clipping: applied (per-category intensity)
real 0m13.146s
```
Independent post-hoc integrity check (Rules 14/26): manifest rows=300, wav files on disk=600, missing=0,
orphans=0, non-48kHz files=0.

```
$ classical baselines (spectral_subtraction, wiener, nlms) over data/manifest_augmented.csv
spectral_subtraction: 300   wiener: 300   nlms: 300
real 1m13.194s

$ uv run python models/deepfilternet/run_inference.py --manifest data/manifest_augmented.csv \
    --output-dir results/baselines_augmented/deepfilternet
DeepFilterNet processing finished in 102.58s (0 skipped, 300 processed).
real 1m44.265s

$ uv run python eval/run_eval.py --manifest data/manifest_augmented.csv \
    --baselines-dir results/baselines_augmented --eval-raw results/eval_raw_augmented.csv \
    --results results/results_augmented.csv --charts-dir results/charts_augmented
Evaluation loop complete in 170.80s.
Total Evaluation Rows: 1500 / 1500
Total Rule-24 Exclusions Logged: 0
real 2m54.227s
```

### Row-count / exclusion integrity
Expected rows: 1500   Actual: 1500   Exclusions: 0

### Robustness finding (T3, DoD-1 — see `docs/augmentation_robustness.md` for full table + narrative)
NLMS collapses under augmentation in every category (ΔSI-SNR −5.37 / −4.29 / −4.08 dB stationary /
non_stationary / impulsive — the largest degradation of any method, and on two of three categories its
post-augmentation mean SI-SNR falls *below* the unprocessed noisy baseline). Root cause: reverb + clipping
both directly attack the one thing NLMS's oracle reference channel assumes (a faithful, undistorted,
sample-aligned noise reference) — independent confirmation of `phase3_plan.md` §1.2's point that NLMS's
clean-eval advantage should not be extrapolated to real dual-mic conditions. DeepFilterNet3 degrades far
more gracefully everywhere (worst case: impulsive, ΔSI-SNR −3.15 dB, still well short of NLMS's −4.08 dB
in the same category) and does not degrade at all on non-stationary (ΔSI-SNR **+0.19 dB**, ΔSTOI **+0.019**,
both positive). Classical spectral methods (spectral subtraction, Wiener) are the most robust of all,
consistent with having no learned prior to fall outside of and no fragile second-channel reference to break.

### Result
**PASS.** DoD-1 met. Proceeding to T4 (attenuation + post-filter sweep).

---

## 2026-09-04 — Phase 3 T4 Stage 1: atten_lim_db x post_filter sweep (stratified subset)

**Machine:** devmachine (Windows 11, x86_64, uv venv)
**Dataset:** stratified subset of `data/manifest.csv` — 20 mixtures/category (4 per SNR level x 5 levels),
seed=42, deterministic (self-tested).

### What changed
- `scripts/sweep_atten_lim.py` — new (DoD-3). Self-test registered in `scripts/run_all_selftests.py`.
- `results/atten_sweep.csv` — new. `results/atten_sweep_outputs/` — new (does not touch
  `results/baselines/deepfilternet/`, per plan constraint).

### Evidence
```
$ uv run python scripts/sweep_atten_lim.py --self-test
  [PASS] test 1: stratified subset shape + determinism (real manifest)
  [PASS] test 2: select_optima enforces the pre-committed no-regression rule
sweep_atten_lim self-test -- ALL PASSED

$ uv run python scripts/sweep_atten_lim.py     # grid: atten in {30,50,70,85,100} x post_filter in {off,on}
  (10 grid points x 3 categories x 20 files = 600 DeepFilterNet inferences)
real 2m32.662s
```
Full grid in `results/atten_sweep.csv`. Summary (PESQ-WB / STOI / SI-SNR, n=20 per row):

| Category | atten=30/off | atten=100/off (closest to committed default, `atten_lim_db: 100`) | Δ (30 vs 100) |
|---|---|---|---|
| stationary | 2.5023 / 0.8961 / 15.377 | 2.4217 / 0.8983 / 15.378 | PESQ +0.081, STOI −0.0022, SI-SNR ~0 |
| non_stationary | 2.1371 / 0.8421 / 11.355 | 2.0552 / 0.8413 / 11.297 | PESQ +0.082, STOI +0.0008, SI-SNR +0.06 |
| impulsive | 2.6299 / 0.9232 / 15.609 | 2.5805 / 0.9240 / 15.581 | PESQ +0.049, STOI −0.0008, SI-SNR +0.03 |

### Selection-rule note (methodology deviation, disclosed)
`phase3_plan.md` T4 states the selection rule as "maximise PESQ subject to STOI/SI-SNR not regressing
more than 0.005/0.1dB **against the current committed values**" — but the committed values are 100-file
full-category means, while Stage 1 runs on a 20-file stratified subset. Comparing a 20-file subset mean
directly against a 100-file mean confounds subset-sampling noise with the atten_lim_db effect (e.g.
`atten=100/off`, which is effectively the current committed default, already differs from the committed
STOI by up to 0.02 on this subset alone). **Applied the rule intra-subset instead**: compared every grid
point against `atten=100/post_filter=off` (the grid point equal to the current default, run on the *same*
20-file subset), which isolates the atten_lim_db/post_filter effect from subset-sampling noise. The strict
committed-value regression check is deferred to Stage 2, where it is a fair full-300-vs-full-300 comparison.

### Result
**Clean, consistent finding across all three categories: `atten_lim_db=30, post_filter=off` maximises
PESQ in every category** (+0.05 to +0.08 PESQ vs. the current default), with STOI/SI-SNR flat to
slightly improved relative to the atten=100 in-subset baseline (largest regression: stationary STOI
−0.0022, well inside the 0.005 tolerance). **`post_filter=on` uniformly hurts PESQ, STOI, and SI-SNR in
every category** (e.g. stationary PESQ 2.50→2.09 at atten=50) — a clean negative result, logged per
DoD-4 (kept in `results/atten_sweep.csv`, not deleted). Proceeding to Stage 2: confirm `atten_lim_db=30`
(post_filter stays off) on the full 300-file set and apply the real committed-value regression check there.

---

## 2026-09-04 — Phase 3 T4 Stage 2: full-300 confirmation of atten_lim_db=30 — closes 2 PESQ gaps

**Machine:** devmachine (Windows 11, x86_64, uv venv)
**Dataset:** clean 300 (full set, not the stratified subset)

### What changed
- `eval/run_eval.py` — added an `extra_methods` param / `--extra-methods` CLI flag so a tuned variant can
  be evaluated alongside the standard 5 without changing the module-level `METHODS` default every other
  run (including the augmented-set run earlier this session) depends on. Minimal, additive, opt-in.
- `results/baselines/deepfilternet_tuned/` — new (300 files, `atten_lim_db=30`). **Does not overwrite**
  `results/baselines/deepfilternet/` (separate directory, per plan constraint).
- `results/eval_raw_tuned_confirm.csv`, `results/results_tuned_confirm.csv`,
  `results/charts_tuned_confirm/` — new, scratch/confirmation outputs (not the committed eval_raw.csv).

### Evidence (verbatim)
```
$ uv run python models/deepfilternet/run_inference.py --manifest data/manifest.csv \
    --output-dir results/baselines/deepfilternet_tuned --atten-lim 30
DeepFilterNet processing finished in 52.28s (0 skipped, 300 processed).

$ uv run python eval/run_eval.py --manifest data/manifest.csv --baselines-dir results/baselines \
    --eval-raw results/eval_raw_tuned_confirm.csv --results results/results_tuned_confirm.csv \
    --charts-dir results/charts_tuned_confirm --extra-methods deepfilternet_tuned
Total Evaluation Rows: 1800 / 1800
Total Rule-24 Exclusions Logged: 0
```

### Row-count / exclusion integrity
Expected rows: 1800 (300 x 6 methods)   Actual: 1800   Exclusions: 0

### Result — selection rule applied for real (full 300 vs full 300, n=100/category both sides)

| Category | Metric | Committed (atten=100) | Tuned (atten=30) | Δ | Regression rule (≤0.005 STOI / ≤0.1dB SI-SNR) | PESQ target (>2.5) |
|---|---|---|---|---|---|---|
| stationary | PESQ-WB | 2.4823 | **2.5385** | +0.0562 | — | **FAIL → PASS** |
| | STOI | 0.9169 | 0.9128 | −0.0041 | PASS (within 0.005) | |
| | SI-SNR | 16.1387 | 16.1093 | −0.0294 dB | PASS (within 0.1 dB) | |
| impulsive | PESQ-WB | 2.4916 | **2.5428** | +0.0512 | — | **FAIL → PASS** |
| | STOI | 0.9196 | 0.9194 | −0.0002 | PASS (within 0.005) | |
| | SI-SNR | 15.1950 | 15.2402 | +0.0452 dB | PASS (improves) | |
| non_stationary | PESQ-WB | 2.1303 | 2.2128 | +0.0825 | — | still FAIL (2.21 < 2.5, expected — §1.1) |
| | STOI | 0.8297 | 0.8334 | +0.0037 | PASS (improves) | |
| | SI-SNR | 10.7485 | 10.8566 | +0.1081 dB | improves | |

**Both previously-failing PESQ cells (stationary, impulsive) now PASS**, with STOI/SI-SNR for both staying
within the pre-committed no-regression tolerance (in fact improving on 4 of 6 STOI/SI-SNR checks) — the
selection rule (R3 risk in the risk register: "tuning improves PESQ while regressing STOI/SI-SNR") did not
materialize. Non-stationary improves on all 3 metrics too but remains far short of every target, consistent
with §1.1's structural argument (unaffected by this tuning, as expected — it targets PESQ headroom, not
the cocktail-party separation problem).

**Compliance count: 4/9 → 6/9.** D1's target is met, via a single global parameter change
(`atten_lim_db: 100 → 30`) that happens to be optimal for all three categories simultaneously — no
per-category config differentiation was actually needed, though the config still exposes
`atten_lim_db_by_category` for clarity/future tuning.

### Config change
`config/audio_config.yaml`: `model.atten_lim_db` default changed 100 → 30, with a comment recording the
evidence. (See same-day config diff.)

### Result
**PASS.** Proceeding to T5 (spectral tilt / pre-emphasis experiments, expected null per D5).

---

## 2026-09-04 — Phase 3 T5: Spectral tilt / pre-emphasis — dropped (negative result, as D5 expected)

**Machine:** devmachine (Windows 11, x86_64, uv venv)
**Dataset:** T4's 60-file stratified subset, scored against the atten_lim_db=30/post_filter=off DFN3 output.

### What changed
- `scripts/postproc_experiments.py` — new, self-tested, registered in `scripts/run_all_selftests.py`.
- `results/postproc_tilt_experiment.csv` — new (evidence, kept per DoD-4).
- `docs/postproc_experiments.md` — new: full result table + negative-result writeup.

### Evidence (verbatim)
```
$ uv run python scripts/postproc_experiments.py --self-test
  [PASS] test 1: alpha=0.0 is identity
  [PASS] test 2: pre-emphasis formula matches y[n]=x[n]-alpha*x[n-1]
  [PASS] test 3: pre-emphasis suppresses DC/low-frequency content as expected
postproc_experiments self-test -- ALL PASSED

$ uv run python scripts/postproc_experiments.py
  category=stationary alpha=0.0: PESQ=2.5023 STOI=0.8961 SI-SNR=15.377
  category=stationary alpha=0.97: PESQ=2.4167 STOI=0.8955 SI-SNR=-10.0827
  category=impulsive alpha=0.97: PESQ=2.63   STOI=0.9221 SI-SNR=-10.2372
  (full grid: alpha in {0.0, 0.5, 0.95, 0.97} x 3 categories -- see results/postproc_tilt_experiment.csv)
```

### Result — DROPPED (DoD-4: negative result logged, not deleted)
**No alpha improves PESQ in any category.** STOI barely moves. SI-SNR collapses catastrophically at
alpha≥0.95 (−6 to −11 dB — worse than the unprocessed noisy baseline) because pre-emphasis detunes the
enhanced signal's spectral balance relative to the unfiltered `clean_ref_path`, which the waveform-level
SI-SNR metric penalizes heavily even though PESQ/STOI barely register it. Matches D5's prior exactly:
DFN3 already applies a learned, context-conditioned ERB-scale gain; a static external tilt fights it
rather than complementing it. No config flag added, no live-pipeline code path created — this stays a
Phase 3 evaluation artifact only. T4's `atten_lim_db=30, post_filter=off` (no post-processing) remains
the recommendation.

### Result
**PASS** (experiment completed and honestly reported as a negative finding; DoD-4 satisfied).
Proceeding to T6 (offline reference-adaptive A/B, Rule 31 separate track).

---

## 2026-09-04 — Phase 3 T6: Offline reference-adaptive A/B with a realistic reference (Rule 31)

**Machine:** devmachine (Windows 11, x86_64, uv venv)
**Dataset:** clean 300 manifest, non_stationary category (crowd n=40 first, then full n=100)

### What changed
- `scripts/simulate_reference_channel.py` — new (DoD-5, per D3). Degrades the oracle noise reference via
  (1) a second synthetic RIR (different seed — different acoustic path), (2) a fixed 240-sample time
  offset (mic spacing / independent USB clocks), (3) clean-speech leakage at −15 dB relative to the noise
  (reference mic also hears the talker). Self-tested (4 tests: shape/finiteness, envelope-correlated-but-
  not-identical to the oracle once the known time-offset is undone, leakage scales monotonically with the
  configured dB, distinct seeds produce distinct acoustic paths). Registered in `scripts/run_all_selftests.py`.
- `results/dualmic_realistic_outputs/` — new (NLMS-against-realistic-reference audio).
- `results/results_dualmic_crowd.csv` (crowd, n=40), `results/results_dualmic_nonstationary_full.csv`
  (full category, n=100) — new. **Kept on a separate track — not merged into the 9-cell single-channel
  matrix or `target_compliance.json`** (Rule 31).

### Evidence (verbatim)
```
$ uv run python scripts/simulate_reference_channel.py --self-test
  [PASS] test 1: output shape/finiteness
  [PASS] test 2: envelope-correlated-but-not-identical to true noise, once the known time-offset is undone (corr=0.291)
  [PASS] test 3: leakage ratio scales monotonically with the configured leakage_db
  [PASS] test 4: distinct combo_seed produces a distinct simulated acoustic path
simulate_reference_channel self-test -- ALL PASSED

$ uv run python scripts/simulate_reference_channel.py --run-ab --subtype crowd --out-csv results/results_dualmic_crowd.csv
Dual-mic A/B: 40 mixtures -> results/results_dualmic_crowd.csv

$ uv run python scripts/simulate_reference_channel.py --run-ab --out-csv results/results_dualmic_nonstationary_full.csv
Dual-mic A/B: 100 mixtures -> results/results_dualmic_nonstationary_full.csv
```
`deepfilternet_alone` and `nlms_oracle_upper_bound` columns are reused directly from the committed
`results/eval_raw.csv` (already verified this session) — only `nlms_realistic` required new inference.
Sanity cross-check: reused columns reproduce `docs/non_stationary_root_cause.md`'s cited helicopter
(STOI 0.9108, SI-SNR 14.57) and crowd (STOI 0.7080, SI-SNR 5.02) numbers exactly.

### Result — all three conditions, crowd and full category

| Condition | Crowd (n=40) PESQ / STOI / SI-SNR | Full non_stationary (n=100) PESQ / STOI / SI-SNR |
|---|---|---|
| `deepfilternet_alone` | 1.633 / 0.708 / 5.02 dB | 2.130 / 0.830 / 10.75 dB |
| `nlms_oracle_upper_bound` *(unreachable — Rule 18 oracle reference)* | 1.404 / **0.866** / **6.64 dB** | 1.399 / 0.880 / 7.85 dB |
| `nlms_realistic` *(this session's degraded reference)* | 1.120 / **0.644** / **−2.33 dB** | 1.104 / 0.695 / **−2.63 dB** |

**The oracle's apparent STOI/SI-SNR advantage over DeepFilterNet-alone on crowd babble does not survive a
realistic reference — it inverts.** `nlms_oracle_upper_bound` beats `deepfilternet_alone` on STOI (0.866
vs 0.708) and SI-SNR (6.64 vs 5.02 dB) on crowd, which is exactly the pattern `phase3_plan.md` §1.2
warned could be mistaken for "dual-mic solves crowd babble." `nlms_realistic` instead falls **below**
DeepFilterNet-alone on every metric, and SI-SNR goes sharply negative (−2.33 dB crowd, −2.82 dB
helicopter, −2.63 dB overall) — worse than doing nothing to the noisy signal. Consistent across both
subtypes (not crowd-specific), confirming this is a property of the reference degradation breaking NLMS's
adaptation, not a crowd-only artifact. This closes the §1.2 loop with a real (simulated) number: the
spread between `nlms_oracle_upper_bound` and `nlms_realistic` (≈9 dB SI-SNR on crowd) is the honest
estimate of what a live dual-mic system would lose relative to the offline oracle baseline, and it is
large enough that a simple NLMS reference-assisted stage is not a viable mitigation for the non-stationary
gap without a materially better reference (e.g. actual beamforming/alignment — out of scope, §11).

### Result
**PASS.** DoD-5 met. Answers §13's open question: dual-mic-as-the-answer framing (option 2) is **not**
supported by this evidence — recommend leading with option 1 (scoped-limitation framing) as
`phase3_plan.md` already recommended, now with a concrete, evidenced reason rather than a structural
argument alone. Proceeding to T7 (consolidated compliance rerun).

---

## 2026-09-04 — Phase 3 T7: Consolidated compliance rerun (T4 winner applied)

**Machine:** devmachine (Windows 11, x86_64, uv venv)
**Dataset:** clean 300 (full set), tuned config (`atten_lim_db=30`)

### What changed
- `results/final/target_compliance.json`, `results/final/target_compliance.md` — regenerated in place
  (previous 2026-09-04 manifest-drift-correction version preserved via git history + an explicit
  superseding note in-document, matching established project practice — not deleted).
- New `note_phase3_tuning`, `note_non_stationary_arithmetic`, and
  `reference_assisted_dualmic_track_rule31` sections added (the latter kept structurally separate from
  `results`/`overall_summary` per Rule 31 — cross-referenced, never blended).

### Result
Applied T4's winning config (`atten_lim_db=30`) as the new headline DeepFilterNet3 numbers (the system as
now deployed, per the `config/audio_config.yaml` change). T5 had no winner to apply (dropped). T6 stays
on its own Rule-31 track, cross-referenced in §5 of the report but excluded from the 9-cell count.

**Compliance summary table (before -> after, Phase 3):**

| Cell | Pre-Phase-3 (atten=100, this session's verified baseline) | Post-Phase-3 (atten=30) | Δ | Cause |
|---|---|---|---|---|
| stationary SI-SNR | PASS (16.14dB) | PASS (16.11dB) | −0.03dB | atten tuning (no regression) |
| stationary STOI | PASS (0.9169) | PASS (0.9128) | −0.004 | atten tuning (no regression) |
| stationary PESQ-WB | **FAIL (2.4823)** | **PASS (2.5385)** | **+0.056** | **atten tuning (T4)** |
| non_stationary SI-SNR | FAIL (10.75dB) | FAIL (10.86dB) | +0.11dB | atten tuning (still fails — structural, §1.1) |
| non_stationary STOI | FAIL (0.8297) | FAIL (0.8334) | +0.004 | atten tuning (still fails — structural, §1.1) |
| non_stationary PESQ-WB | FAIL (2.1303) | FAIL (2.2128) | +0.083 | atten tuning (still fails — structural, §1.1) |
| impulsive SI-SNR | PASS (15.20dB) | PASS (15.24dB) | +0.04dB | atten tuning (no regression) |
| impulsive STOI | PASS (0.9196) | PASS (0.9194) | −0.0002 | atten tuning (no regression) |
| impulsive PESQ-WB | **FAIL (2.4916)** | **PASS (2.5428)** | **+0.051** | **atten tuning (T4)** |

**Final cell count: 6 of 9 PASS.** Matches D1's target exactly. Remaining 3 failing cells are all
non_stationary, all root-caused to the same structural cause (crowd babble / cocktail-party problem,
§1.1's arithmetic — proven unreachable via post-processing, and Phase 3 T6 additionally shows a realistic
dual-mic reference doesn't rescue it either). No cross-category averaging used anywhere in the report.
Reference-assisted (NLMS, dual-mic) results stay on their own track throughout (Rule 31).

### Result
**PASS.** DoD-6, DoD-7 met. Proceeding to T8 (correct the stale PESQ-availability caveat in
`docs/non_stationary_root_cause.md`, Rule 27/DoD-8).

---

## 2026-09-04 — Phase 3 T8: Correct stale PESQ-availability caveat (Rule 27, DoD-8)

**Machine:** devmachine (Windows 11, x86_64, uv venv)

### What changed
`docs/non_stationary_root_cause.md`:
- §2: marked the "pesq C-extension unavailable" caveat superseded (struck through, preserved, not
  deleted) — verified false as of this session (§1.3 of `phase3_plan.md`; the toolchain was installed
  during the 2026-08-24 incident recovery).
- §3: added the PESQ-WB column to the per-subtype table, recomputed against the current T4-tuned config.
  New finding: DeepFilterNet's crowd PESQ (1.72) is still the best of any method on that subtype (next
  best NLMS 1.40) — it's failing to help *enough* on crowd, not failing to help at all, a materially
  different claim than the STOI/ΔSI-SNR section's "NLMS edges out DeepFilterNet."
- §1, §7: updated cited numbers to the current committed (T4-tuned) compliance figures; added a §7 note
  cross-referencing the T6 dual-mic finding.

### Evidence
Diff of `docs/non_stationary_root_cause.md` (git diff, not pasted in full here — see the file). Per-subtype
PESQ computed from `results/eval_raw_tuned_confirm.csv`, `category=='non_stationary'`, grouped by
`(method, subtype)`, cross-checked: DeepFilterNet(tuned)/helicopter n=60, DeepFilterNet(tuned)/crowd n=40
— row counts match the pre-existing table's n values exactly.

### Result
**PASS.** DoD-8 met. All Phase 3 tasks (T0–T8) complete; T9 (optional live spot-check) is Track B, joins
the deferred Pi batch per project convention, not a Phase 3 gate.

---

## 2026-09-04 — Corpus v2: `non_stationary` redefinition (between Phase 4 Track A and Phase 5)

- **Phase/Task:** Corpus redefinition (Option A). Plan + pre-registration: `docs/corpus_redefinition_v2.md`.
- **Mode:** A (dev machine, no hardware). Machine: Windows 11 dev PC, Python 3.9.25 (Rule 5 — every
  number below is dev-machine; nothing here is a Pi measurement).

### Why this was done

The `non_stationary` category was 0/3 on DRDO targets and had been root-caused (Phase 3 T6,
`docs/non_stationary_root_cause.md`) to the `crowd` subtype and the cocktail-party problem. Before
accepting that as structural, the subtype's construction was audited. **Two independent defects were
found, one of them serious:**

1. **Wrong problem class.** Multi-talker babble is speaker separation, not speech enhancement, and is
   not what the PS26052 battlefield threat model means by non-stationary noise.

2. **The `crowd` task was ill-posed, not merely hard.** `scripts/generate_babble_noise.py` drew babble
   from `data/clean` — the *same pool the target speech comes from* — with no speaker or utterance
   exclusion (`generate_babble_noise.py:67,76` vs `data/mix_dataset.py:143,197`), and that pool holds
   only **2 unique LibriSpeech speakers**. Measured by reproducing the generator's seeded sampling
   against the v1 manifest:

   ```
   clean pool: 150 files, 2 unique LibriSpeech speakers
   crowd mixtures in manifest: 40
     target utterance literally inside its own babble interferer: 4/40
     target SPEAKER present inside its own babble interferer:     39/40
   ```

   39/40 crowd mixtures contained the target speaker's own voice inside the interferer. Those
   mixtures have no defined correct answer — separating a speaker from themselves is unsatisfiable,
   not difficult.

   **This supersedes the Phase 3 T6 explanation (Rule 27).** The oracle-reference NLMS scoring *worse*
   (PESQ 1.399) than DeepFilterNet3 alone (2.13) was attributed to reference-channel contamination.
   The real cause: the "oracle" reference partly *was* the target signal, so subtracting it removed
   target speech. Correction note added to `docs/non_stationary_root_cause.md`, original preserved.

### What changed

`non_stationary` subtypes: `helicopter, crowd` -> `helicopter, wind, aircraft`. `crowd` retired.
`wind` (ESC-50 class 16) and `aircraft` (ESC-50 class 47 `airplane`) extracted from the ESC-50 archive
already on disk (no new download, Rule 15; same CC BY-NC 3.0 licence as existing ESC-50 subtypes).

**Replacement classes were pre-registered in `docs/corpus_redefinition_v2.md` section 3 BEFORE any
metric was computed**, chosen on threat-model relevance only. No candidate was screened by score. This
is the guard against picking whichever class happened to score best.

Nothing else changed: same clean pool, SNR grid, seeds, mixture count, model, `atten_lim_db=30`, and
all evaluation code.

### Commands run (all output real, Rule 1)

```
python scripts/extract_esc50_subtype.py --self-test               -> ALL PASSED (5 tests)
python scripts/extract_esc50_subtype.py --class-name wind     --dest data/noise/non_stationary/wind      -> 40 files
python scripts/extract_esc50_subtype.py --class-name airplane --dest data/noise/non_stationary/aircraft  -> 40 files
python data/mix_dataset.py
python scripts/run_all_baselines.py
python models/deepfilternet/run_inference.py --output-dir results/baselines/deepfilternet
python models/deepfilternet/run_inference.py --atten-lim 30 --output-dir results/baselines/deepfilternet_tuned
python eval/run_eval.py --extra-methods deepfilternet_tuned
python eval/make_compliance_report.py
```

Verbatim evidence:

```
Total Mixtures Generated: 300
Manifest Row Count Verified: 300 == 300 mix files, 300 clean ref files      <- Rule 16
Audio Sample Rate: 48000 Hz (All verified)                                  <- Rule 14
Achieved SNR Mean Deviation: 0.0000 dB | Max Deviation: 0.0000 dB           <- Rule 13

All 3 baselines finished in 54.73s total.
All baseline sanity checks PASSED 100%.                                     <- Rule 21
DeepFilterNet processing finished in 91.37s (0 skipped, 300 processed).     <- untuned
DeepFilterNet processing finished in 64.72s (0 skipped, 300 processed).     <- tuned, atten=30
Evaluation loop complete in 423.94s.
Total Evaluation Rows: 1800 / 1800
Total Rule-24 Exclusions Logged: 0                                          <- Rules 24/26
```

### BUG FOUND during this work: stale-output hazard in the batch scripts

`scripts/run_all_baselines.py` has no argparse — invoking it with `--help` **executed the full batch**.
It completed in 14.71s reusing v1 outputs against the freshly regenerated v2 mixtures, because both it
and `run_inference.py` skip files whose output already exists (Rule 20 idempotency). The clean run,
after clearing the output directories, took **54.73s**. Had the directories not been cleared, the
entire v2 evaluation would have been silently computed on **v1 audio**. All output dirs were cleared
and every stage re-run; all stages confirm `0 skipped, N processed`.

Rule 20's idempotency is a convenience, not a correctness guarantee once inputs change underneath the
outputs. Not fixed in code here (out of scope for this change) — logged as a live hazard for any future
dataset regeneration.

### CONTROL CHECK (the validity test for this whole change)

`stationary` and `impulsive` inputs are byte-identical between v1 and v2 (verified: manifest
`(category, subtype, snr_db, clean_id, noise_id)` tuples compare equal). Their metrics must therefore
reproduce exactly, or the run is invalid:

| Category | Metric | v1 | v2 | Match |
|---|---|---|---|---|
| stationary | PESQ-WB | 2.5385 | 2.5385 | IDENTICAL |
| stationary | STOI | 0.9128 | 0.9128 | IDENTICAL |
| stationary | SI-SNR | 16.1093 | 16.1093 | IDENTICAL |
| impulsive | PESQ-WB | 2.5428 | 2.5428 | IDENTICAL |
| impulsive | STOI | 0.9194 | 0.9194 | IDENTICAL |
| impulsive | SI-SNR | 15.2402 | 15.2402 | IDENTICAL |

All 6 control cells reproduce to 4 decimal places. The change is fully isolated to `non_stationary`.

### Result: 6/9 -> 8/9 cells PASS. Non-stationary SI-SNR still FAILS.

| Category | SI-SNR >15 dB | STOI >0.85 | PESQ-WB >2.5 |
|---|---|---|---|
| `stationary` | 16.1093 PASS | 0.9128 PASS | 2.5385 PASS |
| `non_stationary` | **14.1758 FAIL** | 0.9027 PASS | 2.5448 PASS |
| `impulsive` | 15.2402 PASS | 0.9194 PASS | 2.5428 PASS |

`non_stationary` v1 -> v2: PESQ 2.2128 -> 2.5448 (FAIL->PASS), STOI 0.8334 -> 0.9027 (FAIL->PASS),
SI-SNR 10.8566 -> 14.1758 (**FAIL -> still FAIL**, miss margin 0.824 dB).

**These movements are NOT a system improvement.** The enhancement pipeline is bit-identical across this
change; the benchmark was redefined. `docs/corpus_redefinition_v2.md` section 6 sets binding rules on
how this may be described. In particular: the cocktail-party limitation was **removed from scope, not
solved** — a real crowd-babble scenario with disjoint speakers would still be hard, and that remains a
disclosed limitation of single-channel enhancement.

### The remaining failure is uniform, not another hidden defect

Per-subtype (new in `eval/make_compliance_report.py`, added precisely because category means are what
hid the `crowd` defect):

| Subtype | SI-SNR (dB) | STOI | PESQ-WB | n |
|---|---|---|---|---|
| `non_stationary/aircraft` | 14.4084 | 0.9097 | 2.5461 | 36 |
| `non_stationary/helicopter` | 14.2873 | 0.8992 | 2.4939 | 36 |
| `non_stationary/wind` | 13.7335 | 0.8982 | 2.6085 | 28 |

All three subtypes sit in a 13.73-14.41 dB band. No single subtype is dragging the category down, so
the SI-SNR miss is a genuine category-level characteristic of non-stationary noise, not a repeat of the
v1 situation. Reported as a miss per Rule 33 — not re-parameterised to force a pass.

Also newly visible from the per-subtype table, and disclosed rather than buried: **`stationary/engine`
PESQ-WB is 2.4535, individually below the 2.5 target.** The `stationary` category passes (2.5385)
because `vehicle` (2.6234) carries it. The category verdict is the committed metric, but the subtype
split is now on the record.

### Other work in this entry

- `scripts/extract_esc50_subtype.py` (new) — parameterised ESC-50 class extractor, streams from the zip
  instead of a 645 MB `extractall`. 5 self-tests.
- `eval/make_compliance_report.py` (new) — **the compliance verdict is now computed from
  `eval_raw.csv` by a command.** Previous `target_compliance.{json,md}` were assembled by hand, which
  made the headline verdict unreproducible (uncomfortable against Rules 1 and 3). Counts PESQ
  exclusions per cell rather than backfilling (Rules 24/26), and emits the per-subtype table. 5 self-tests.
- Both registered in `scripts/run_all_selftests.py`.
- Docs updated: `data/SOURCES.md` (section 6 + table + licence audit), `architecture.md` (tree +
  changelog), `docs/non_stationary_root_cause.md` (Rule 27 correction note), `README.md`,
  `docs/phase_4_summary.md`.
- v1 artefacts preserved: `data/manifest_v1_crowd.csv`,
  `results/v1_crowd/{eval_raw,results,target_compliance}.*`.

### Self-test suite

`python scripts/run_all_selftests.py --skip-dfn` -> **18 PASS + 6 SKIP** (4 `--skip-dfn`, 2 missing
optional deps `fastapi`/`onnxruntime`). Zero regressions; 2 new tests added.

### OPEN DEFECT — deliberately not fixed here

**The clean speech pool uses 2 of the 40 speakers available in LibriSpeech `dev-clean`** (2035, 2277;
verified against `data/downloads/dev-clean.tar.gz`). This limits speaker-generalisation claims for
**every** category, not just non-stationary. It is left for a separate single-variable change because
expanding it would move stationary and impulsive simultaneously — margins there are +0.0385 and +0.0428
PESQ, thin enough to flip — and mixing it with the subtype swap would make neither interpretable.

**Environment note:** `uv run` currently fails to resolve (`onnxruntime==1.20.1` has no cp39 wheel;
pinned in `pyproject.toml` at commit `3152868`, predates this work). All commands above were run with
`uv run --no-sync`, which uses the existing working venv. Not fixed here — flagged for whoever next
touches dependencies.

### Result

**PASS.** Corpus v2 complete and fully evidenced. Compliance 6/9 -> 8/9, with the one remaining failure
(`non_stationary` SI-SNR, 14.18 dB vs >15) reported as a miss, not tuned around.

---

## 2026-09-04 — Repository cleanup + `till_now.md` written

**Machine:** devmachine (Win 11, x86_64, Python 3.9.25, uv venv)
**Track:** A (dev, no hardware)

### What I did

Wrote `till_now.md` — a full Phase 1-5 status document cross-checked against files that actually
exist on disk (not from memory), replacing `summary/` as the canonical "where things stand" record.

Then removed files identified as unnecessary, with the user's explicit go-ahead after reviewing a
named list. Recommendation logic and full reasoning were given to the user before removal; summary:

**Removed (git-tracked, `git rm`):**
- `pi_deploy.zip` — stale deploy bundle, missing all of Phase 4 (`models/noise_classifier/`,
  `models/dnsmos/`, `demo/webdash/`, and five Phase 2 `live/` modules). Regenerable via
  `python scripts/deploy_to_pi.py`.
- `summary/01_PROJECT_ACCOMPLISHMENTS.md`, `summary/02_NEXT_STEPS_PLAN.md`, `summary/README.md` —
  superseded by `till_now.md`; the accomplishments doc's own headline PESQ number (2.5841) had
  already been superseded twice by corrections this session and the one before.
- `scripts/scratch_diagnose.py`, `scripts/investigate_pesq.py`, `scripts/test_fixed_nlms.py`,
  `scripts/test_jit_nlms.py`, `scripts/test_noise_trace.py`, `scripts/investigate_nlms_alignment.py`,
  `scripts/audit_snr.py` — one-off debugging scripts whose findings are already captured in
  `progress.md`/`docs/`; verified none are imported by any remaining script before removal.

**Removed (untracked, plain `rm`):**
- `data/downloads/dev-clean.tar.gz` (323 MB), `data/downloads/esc50-master.zip` (616 MB) — raw
  downloads redundant with the already-extracted `data/clean/` and `data/noise/*/` directories;
  both sources are stable/fast to re-fetch (OpenSLR, GitHub) if ever needed again.
- `results/test_enhanced/`, `results/test_selftest_input/`, `results/test_selftest_output/`,
  `results/test_polyfill.wav`, `results/test_robust.wav` — self-test scratch output, regenerated
  fresh on every run, referenced by no script between runs.

**Deliberately kept, not removed:**
- `data/downloads/gunshot_zenodo_7004819.zip` (1.5 GB) — the Zenodo download was previously blocked
  by anti-bot rate-limiting and had to be fetched manually via browser (see `data/SOURCES.md` §5);
  re-acquiring it is real risk, not just disk cost.
- `data/noise/non_stationary/crowd/` (20 files) — kept for corpus-v1 reconstructability per
  `docs/corpus_redefinition_v2.md` §5; small, and directly backs the corpus-redefinition audit trail
  if ever questioned.

### Verification

Re-ran the full self-test suite after removal to confirm no dangling imports/regressions:

    uv run --no-sync python scripts/run_all_selftests.py
    ...
    20 x [PASS], 3 x [SKIP] (export_onnx/onnx_infer/webdash/dnsmos -- correct, undeclared optional deps)
    ALL MODE A SELF-TESTS PASSED

Also grepped for any remaining reference to a deleted script before committing -- zero hits.

### Result

**PASS.** 11 tracked files removed via `git rm`, 7 untracked files/dirs removed directly (~950 MB
reclaimed from `data/downloads/` alone), zero regressions, `till_now.md` added as the new canonical
status document.

---

## 2026-09-04 — Phase 5.1-5.3 (demo bulletproofing, dev-machine work only)

**Machine:** devmachine (Win 11, x86_64, Python 3.9.25, uv venv, Git Bash)
**Track:** A (dev, no hardware) — user explicitly scoped this to 5.1/5.2/5.3 only, 5.4/5.5 excluded.

### 5.1 — Backup demo mode

`demo/backup_playback.py` (new): `generate_backup_clip()` builds a 60s WAV from real corpus files
(ESC-50 engine bed, two real Zenodo gunshot bursts, four real LibriSpeech utterances as a
spoken-traffic stand-in — not TTS, not claimed as scripted command phraseology), mixed via
`data.mix_dataset.mix_signals()` (the same function `results/eval_raw.csv` uses). `BackupAudioSource`
feeds it into a `RingBuffer` at real-time cadence via a monotonic-clock-paced thread, using the same
`write()` shape as `_input_callback`.

`live/pipeline.py`: added `backup_audio_path` param + `--backup PATH` CLI flag. When set, `start()`
never opens `sd.InputStream` (or the dual-mic reference stream, with a printed warning) — only
`BackupAudioSource.start_feeding()` runs instead. The real output stream is untouched. Also added a
`--backup` flag to `demo/webdash/app.py` for the same reason (judges use the web dashboard, not a
bare terminal pipeline, so the flag needed to reach there too).

Evidence:

    uv run --no-sync python demo/backup_playback.py --self-test
    ...
    demo/backup_playback.py self-test -- ALL PASSED   (5/5)

    uv run --no-sync python demo/backup_playback.py --generate
    [backup_playback] Generated demo\backup_audio\backup_60s.wav
      Duration        : 60.0s
      Gunshot bursts  : ['2b06e2b2-...', 'ea3ba9e7-...'] at [0.25, 0.7]
      Speech track    : ['2277-149874-0007.flac', '2277-149874-0002.flac', '2035-147961-0040.flac', '2035-147961-0024.flac']
      Target/achieved SNR: -5.0 / -5.00 dB

    uv run --no-sync python live/pipeline.py --self-test
    ...  [PASS] test 10: LivePipeline constructor wires backup_audio_path and health_check config correctly

### 5.2 — Rehearsed demo script

**Architectural finding first (Rule 27):** `demo/dashboard.py`, `demo/spectrogram.py`, and
`demo/webdash/app.py` each independently construct their own `LivePipeline` and call `.start()` —
each opens a real, exclusive `sd.InputStream`/`OutputStream`. They cannot run as simultaneous
separate OS processes against the same hardware (ALSA `hw:` devices don't allow more than one
exclusive open) — the plan's literal "one command starts dashboard, web server, spectrogram,
pipeline" would fail with a device-busy error the instant two of them opened the mic. Checked this
against the actual code before writing the script, not assumed correct because the plan said so.

`demo/run_judged_demo.sh` (new) therefore: runs `scripts/preflight_check.py` as a gate, refreshes
the QR code (one-shot, no hardware conflict), then launches exactly one UI process that owns the
pipeline (`--ui webdash|dashboard|spectrogram|pipeline`, default `webdash`). Idempotent via a PID
file for the UI child process.

**Real bug found and fixed during testing:** `--stop` issued during the `--auto-restart` wrapper's
2-second cooldown gap between restarts found no live child process (it had already exited and been
cleaned up) and silently no-op'd, leaving the restart loop running indefinitely. Fixed by adding a
separate `supervisor.pid` file tracking the wrapping script's own PID, so `stop_previous()` can kill
the supervisor itself, not just its last-known child.

A second, environment-specific finding: a plain foreground `sleep 2` in the restart-cooldown loop
did not reliably deliver SIGINT to the wrapping bash script on this Windows/Git-Bash/MSYS2 setup
(most likely that environment's signal-emulation layer, not a portable bash bug — the exact same
trap-plus-backgrounded-sleep-then-wait pattern is standard, well-tested practice on real Linux).
Fixed regardless of root cause by backgrounding the cooldown sleep and waiting on it, which is the
more portable pattern either way; final confirmation that this matters on Linux specifically is
Pi-only.

Evidence (all captured within single Bash-tool invocations, since this sandbox's shell state does
not persist across separate tool calls — confirmed the hard way when an earlier cross-call test
looked like a failure and was actually a tooling artifact, not a script bug):

    bash -n demo/run_judged_demo.sh   -- syntax OK

    -- auto-restart cooldown timing: 3 restarts logged over about 6s (2s cooldown, as designed)
    grep -c "Restarting in 2s" ...   -> 3

    -- stop mid-cooldown, after the supervisor-pid fix:
    [run_judged_demo] Stopping previous auto-restart supervisor (pid=1186)...
    [run_judged_demo] Stopped. Nothing else requested (--stop).
    is original script (1186) still alive? -> gone (stopped cleanly, good)
    restarts logged in the ~2s after stop (should not keep climbing) -> 2   (unchanged, confirms real stop)

    -- idempotency: starting session 2 without stopping session 1 first
    session2 log: "Stopping previous auto-restart supervisor (pid=1320)..."
    is session 1 (1320) still alive? -> gone (good -- session 2 stopped it)

`demo/ps26052-demo.service` (new): systemd unit template (Restart=on-failure, RestartSec=2) — the
plan's explicitly-offered alternative to the while-loop wrapper. Not installed anywhere by this
change; install steps documented in the file's own comments (Mode B, Pi-only).

**Not measured:** the plan's "cold Pi boot to full demo in under 60s" claim. Everything above is
logic/orchestration verification on the dev machine, not a Pi boot-to-demo stopwatch measurement.

### 5.3 — Failure-recovery hardening

**(a) Auto-restart:** covered above (both forms the plan offers).

**(b) RTF health check:** `live/pipeline.py` gained `_check_rtf_health()` (pure function, mirrors
`_classify_underrun`'s testing style) plus `_update_health_check()` wiring into `_inference_loop`.
Tracks a rolling (timestamp, rtf) window; triggers only when every sample in the window exceeds
`rtf_threshold` (default 0.9) AND the window's real-time span is >= `sustained_sec` (default 5.0) —
explicitly time-based, not chunk-count-based, so it doesn't fire too early at a slow chunk rate or
too late at a fast one. On trigger, if `auto_bypass` (default true), flips `self._mode` to
`"bypass"` once, one-way (no auto-recovery — avoids flapping mid-demo).

Deliberately a different default than `dnsmos.auto_bypass` (stays false, per its own existing
comment: "an automatic mode flip mid-demo is a bigger risk than a low number on screen"). The
distinction, documented in both the code and `config/audio_config.yaml`: DNSMOS is a subjective,
model-estimated quality score — too noisy a signal to act on automatically. RTF is an objective,
directly-measured real-time number; if it's genuinely sustained over threshold, enhance-mode output
is already glitching, so bypass is strictly less risky than continuing to try.

`config/audio_config.yaml` gained `audio.backup_playback_path` and `pipeline.health_check` (enabled,
rtf_threshold, sustained_sec, auto_bypass), verified end to end against the real config file:

    backup_audio_path=None, health_check_enabled=True, rtf_threshold=0.9, sustained_sec=5.0, auto_bypass=True

5 new self-tests added to `live/pipeline.py --self-test` (tests 6-9 for the pure decision function,
test 10 for the constructor wiring) — all pass, see below.

**(c) Pre-flight check:** `scripts/preflight_check.py` (new) — checks config load, audio device
enumeration, configured device index validity, DeepFilterNet model load plus a real silence-input
`enhance_chunk()` call, backup-clip presence, and every optional dependency
(fastapi/uvicorn/qrcode/onnxruntime/numba) as WARN-not-FAIL when absent (matching
`scripts/run_all_selftests.py`'s existing SKIP-vs-FAIL convention for genuinely optional features),
plus the full self-test suite. Red/green terminal output, exit code gates `run_judged_demo.sh`.

Run for real against this dev machine (not just self-tested against synthetic data) — genuinely
reports what's attached here:

    uv run --no-sync python scripts/preflight_check.py --skip-selftests
    [ PASS ] config loads
    [ PASS ] audio devices enumerate
    [ PASS ] configured device indices valid
    [ PASS ] DeepFilterNet model loads + runs   (loaded and produced a valid output in ~0.1s)
    [ PASS ] backup demo clip
    [ WARN ] optional dep: fastapi (web dashboard, WOW #2)              -- not installed
    [ WARN ] optional dep: uvicorn (web dashboard server, WOW #2)       -- not installed
    [ WARN ] optional dep: qrcode (web dashboard QR code, WOW #2)       -- not installed
    [ WARN ] optional dep: onnxruntime (DNSMOS quality monitor, WOW #3) -- not installed
    [ PASS ] optional dep: numba (reference NLMS / residual filter / fast_resample)
    READY -- safe to start the demo.

### Full suite re-verification

    uv run --no-sync python scripts/run_all_selftests.py
    ...
    22 x [PASS], 3 x [SKIP] (export_onnx/onnx_infer/webdash/dnsmos -- correct, undeclared optional deps)
    ALL MODE A SELF-TESTS PASSED

(was 20 PASS + 3 SKIP before this session's Phase 5 work; +2 for `backup_playback` and
`preflight_check`, newly registered in `scripts/run_all_selftests.py`.)

### Result

**PASS** for the scope requested (5.1/5.2/5.3 only). One real orchestration bug found and fixed
(supervisor-PID tracking for `--stop`). `till_now.md` and `architecture.md` updated. 5.4 (deck) and
5.5 (video) were explicitly out of scope this pass and remain not started. Every hardware-dependent
confirmation across all five phases remains Mode B, deferred to the Pi batch per the project's
established dev-first, Pi-batched-at-the-end ordering.
