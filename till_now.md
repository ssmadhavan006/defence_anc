# PS26052 — Where Things Stand (2026-09-04)

Smart India Hackathon 2026 · DRDO Problem Statement 26052 · AI/ML-Enabled Adaptive Noise
Cancellation for Defence Communications.

This document tracks progress against `prototype.md`'s five-phase plan. It reports what is
**verified** (a real command was run and its output is quoted somewhere in `progress.md`) versus
what is **built but not yet hardware-validated**, per Rule 29 (no Mode B test is marked passed
from code review alone). Every number below traces to `progress.md`, `results/`, or a file that
still exists in the repo — nothing here is asserted from memory.

**One-line status:** all four dev-machine (Mode A) phases are built, self-tested, and produce a
compliance verdict of **8 of 9 metric cells PASS**. Every hardware-dependent (Mode B) item across
all four phases, plus the entirety of Phase 5, remains outstanding.

---

## Phase 1 — Dual-Channel Hardware & Software Foundation

**Plan's objective:** bring the system from single-mic to primary + reference mic — *"the one
PS-explicit requirement not currently met."*

### Done (dev machine, Mode A)
- `config/audio_config.yaml` extended with `audio.dual_mic` (reference device, delay compensation,
  topology) and `pipeline.reference_nlms` sections.
- `live/pipeline.py` runs a second `sd.InputStream` + second ring buffer (`_ref_buf`), with
  delay-line compensation and ERLE telemetry.
- `live/reference_nlms.py` — streaming reference-based NLMS filter, numba-JIT. Verified
  **bit-identical** to the offline batch reference (`baselines/nlms/nlms.py`) in self-test.
  (This is the plan's `live/reference_ale.py` — implemented under a different name; same function.)
- `live/calibrate_mic_pair.py` — log-chirp cross-correlation calibration, writes
  `config/mic_calibration.yaml`. (Plan called this `scripts/calibrate_mic_pair.py`; same script,
  lives under `live/` instead per this repo's Pi/non-Pi code separation, Rule 9.)
- **Topology decision, made explicitly with you before implementation:** no 2-in USB interface was
  purchased. Dual-mic uses two independent USB devices (Topology B) — primary via a 3.5mm-to-USB
  headset dongle, reference as a separate USB mic. Clock drift (~2.4 samples/sec at 50ppm/48kHz) is
  accepted as a permanent constraint, mitigated by calibration + NLMS's 64-tap span.
- 8 self-tests pass, including a convergence test (correlation 0.763→0.992) and ERLE-positive check.

### Not done — requires real hardware (Mode B, deferred to your Pi batch)
- **No dual-mic hardware has been physically connected or tested.** This is the plan's headline
  deliverable and it has not happened.
- `results/stress_dualmic.json` (10-min dual-mic stress test) — does not exist.
- Live calibration on Pi (`python live/main.py calibrate`) — not run.
- Live A/B demo with reference NLMS toggled — not run.
- The spectrogram crowd-babble-suppression comparison the plan's checklist asks for is now moot in
  its original form — see Phase 3 below, the `crowd` subtype itself was retired as ill-posed.
- README still describes the system as single-channel "AI/ML-enabled adaptive noise suppression,"
  **not** "true dual-channel adaptive noise cancellation" (Rule 32 — that language is earned only
  once secondary-path/reference hardware is actually running, not before).

---

## Phase 2 — Latency Engineering & Real-Time Grade

**Plan's objective:** get end-to-end latency under 150ms, "from a hedged claim to a defensible
number against any evaluator's stopwatch."

### Done (dev machine, Mode A)
- **Bug found and fixed first:** `config/audio_config.yaml` had duplicate top-level `audio:` and
  `pipeline:` blocks. YAML silently collapsed them to the last one seen, so `input_device`,
  `output_device`, `chunk_duration_sec`, and `priming_chunks` were being silently discarded on
  every run to date — auto-detection happened to compensate, which is why it went unnoticed.
- `live/latency_budget.py` — dataclass that tags each latency component with its actual source
  (`"measured"` / `"estimated"` / `"configured"`), so no number can be misrepresented as measured
  when it wasn't.
- Fractional `priming_chunks` (float, `1.0` = byte-identical to the old behavior) — the mechanism
  for eventually reducing priming toward the plan's "0 priming" goal.
- `live/cpu_affinity.py` — inference-thread core pinning; confirmed graceful no-op on this Windows
  dev machine (real effect only testable on Pi/Linux).
- `live/fast_resample.py` — numba-JIT resampler, confirmed bit-equivalent to the numpy version
  (max diff 0.00e+00), ~2.8x faster **on this dev machine only** (Rule 5 — not claimed for Pi).
- `live/acoustic_latency_test.py` — physical click/cross-correlation round-trip method, logic
  verified with synthetic clicks; also measures DFN3's algorithmic lookahead empirically (Rule 30).
- `scripts/sweep_chunk_size.py` extended for dual-mic-aware sweeps.

### Not done — requires real hardware (Mode B)
- **The <150ms claim has never been measured.** The current ~172ms figure is an *analytical
  estimate* (device round-trip 42.67ms from `snd-aloop` loopback, not real USB + inference ~29.5ms
  + priming 100ms), not a physical stopwatch measurement.
- The physical mic-to-headset acoustic round-trip — *"the first-ever true mouth-to-ear number in
  this project"* per the plan — has not been run.
- Re-baseline on real dual-USB hardware, priming minimization validation, chunk-size re-sweep with
  dual-mic active, core-pinning A/B, fast_resample A/B on Pi, and the final 600s gate at the chosen
  configuration — all outstanding (tracked as B0–B8 in `progress.md`).

---

## Phase 3 — Quality Validation

**Plan's objective:** turn dormant code (augmentation, residual filter) into cited PESQ/STOI
results, and close the offline dual-mic eval loop. Target stated in the plan: **8/9 metric cells.**

### Done — and this is where the project's real work happened
- Found and fixed a **second, independent** reproducibility bug: `data/mix_dataset.py` used
  unsorted `glob.glob()`, so the "seeded" dataset generation wasn't actually deterministic. The
  manifest had drifted from the mixtures on disk. Regenerated end to end; this revealed a
  previously-reported impulsive PESQ-WB of 2.5841 (PASS) was an unreproducible favorable draw — the
  honest baseline was 2.4916 (FAIL).
- Data-augmentation robustness analysis (`docs/augmentation_robustness.md`): NLMS collapses under
  reverb/clipping; DeepFilterNet degrades far more gracefully.
- Attenuation sweep (`scripts/sweep_atten_lim.py`) — **the plan predicted per-category tuning would
  be needed; the actual finding was that all three categories share the identical optimum**
  (`atten_lim_db=30`, post_filter off). This single global change closed both the stationary and
  impulsive PESQ-WB gaps. `config/audio_config.yaml` default changed 100→30.
- Spectral-tilt post-processing experiment — tried, negative result, dropped honestly (no
  cherry-picking, per the plan's own instruction).
- Offline dual-mic A/B with a *realistically degraded* (not oracle) reference
  (`scripts/simulate_reference_channel.py`) — **the plan expected this to rescue crowd babble; it
  did the opposite.** The oracle-reference advantage inverted to strongly negative SI-SNR once the
  reference was realistic. This result was later root-caused further (see below).
- **Corpus v2 redefinition (2026-09-04, beyond the original plan's scope):** audited the
  `non_stationary/crowd` subtype and found it **ill-posed, not merely hard** — the babble generator
  drew interferer speech from the same 2-speaker pool as the target speech with no exclusion, so
  39/40 crowd mixtures contained the target speaker's own voice inside the interferer (4/40 the
  literal same utterance). This also explains the dual-mic A/B inversion above: the "oracle"
  reference was partly the target signal. `crowd` was retired and replaced with `wind` + `aircraft`
  (ESC-50, already on disk, no new download), pre-registered on threat-model grounds *before* any
  metric was computed. `stationary`/`impulsive` verified byte-identical as a control.
  Full rationale: `docs/corpus_redefinition_v2.md`.
- **Compliance result: 8 of 9 metric cells PASS** (exceeding the plan's own 8/9 target), computed by
  `eval/make_compliance_report.py` directly from `results/eval_raw.csv` — not hand-assembled, unlike
  the report this replaced.

| Category | SI-SNR >15dB | STOI >0.85 | PESQ-WB >2.5 |
|---|---|---|---|
| Stationary | 16.11 ✅ | 0.913 ✅ | 2.539 ✅ |
| Non-stationary | 14.18 ❌ | 0.903 ✅ | 2.545 ✅ |
| Impulsive | 15.24 ✅ | 0.919 ✅ | 2.543 ✅ |

The one remaining failure — non-stationary SI-SNR, 14.18 vs >15 dB, a 0.82dB miss — is now
**uniform across all three subtypes** (aircraft 14.4, helicopter 14.3, wind 13.7 dB), confirming
it's a genuine category-level characteristic, not one subtype dragging the mean down the way
`crowd` alone did in v1 (where the gap was 4.14 dB).

### What was NOT solved, stated plainly
Retiring `crowd` removed the cocktail-party scenario **from the evaluation scope; it did not solve
it.** A real crowd-babble case with disjoint speakers would still be hard for a single-channel
enhancer — the dual-mic A/B already showed a reference-assisted mitigation doesn't rescue it either
under realistic conditions. See `docs/non_stationary_root_cause.md`.

### Known open defect, deliberately deferred
The clean speech pool uses only **2 of the 40 speakers** available in LibriSpeech `dev-clean`. This
limits speaker-generalization claims across *every* category (not just non-stationary). Left
untouched on purpose — fixing it would move stationary/impulsive's already-thin PASS margins
(+0.0385, +0.0428 PESQ headroom) simultaneously, which would make this change uninterpretable.
Scoped as its own future single-variable change.

### Also not done — Mode B
- T9 (optional): live dual-mic crowd-babble spot-check on real hardware, to check whether live
  behavior falls between the T6 offline predictions. Not a gate, but still open.

---

## Phase 4 — WOW Factors

**Plan's objective:** three differentiators — adaptive noise classifier + routing, phone-accessible
web dashboard, on-device DNSMOS quality self-monitoring.

### Done (dev machine, Mode A)
- **WOW #1 — Noise classifier, reframed.** `models/noise_classifier/` — CNN trained with a
  **grouped split by `noise_id`** (added as a self-test assertion) to prevent the same physical
  noise clip leaking across train/test at different SNRs — the corpus has only 155 unique noise
  files across 300 mixtures, so a naive random split would have leaked. `models/noise_classifier/classify_chunk.py`
  has an UNCERTAIN state for low-confidence predictions. `models/noise_classifier/impulsive_log.py`
  logs impulsive events to JSONL.
  **Two things dropped from the original plan, deliberately:**
  - The **routing mechanism** (dynamically adjusting `atten_lim_db` per detected category) is dead.
    Phase 4 T1 measured the NLMS realistic-reference penalty across categories and found it
    uniformly negative (crowd −0.49, helicopter −1.36 PESQ mean) — no evidence-backed routing
    policy exists, because Phase 3 T4 had already shown every category wants the same `atten_lim_db=30`.
    The classifier is **display-only**.
  - The **"doubles as acoustic shot-detection"** claim was removed (Rule 32, by analogy to the
    project's existing "no true ANC" rule). A 3-class stationary/non-stationary/impulsive
    classifier trained on synthetic mixtures cannot distinguish a gunshot from a door slam. It's
    named an "impulsive-event log," not a shot detector.
- **WOW #2 — Web dashboard.** `demo/webdash/app.py` — FastAPI + WebSocket, 4Hz telemetry push,
  `/mode/{enhance|bypass}` endpoint reusing the existing terminal dashboard's mode-assignment
  pattern. `demo/webdash/generate_qr.py` for LAN QR codes.
- **WOW #3 — DNSMOS quality monitor.** `models/dnsmos/dnsmos_infer.py` — numpy-only mel spectrogram,
  0.5Hz background thread, `auto_bypass` off by default, correctly SKIPs its self-test when
  `onnxruntime` is absent rather than failing. `models/dnsmos/SOURCES.md` records model provenance +
  MIT license (Rule 12). The documented ONNX blocker (`ml_dtypes`→numpy≥2.1 conflict) was found to
  apply only to the `onnx` package (model *export*), not `onnxruntime` (model *inference*) — verified
  against PyPI metadata, so DNSMOS is very likely viable on the Pi's Python 3.13 despite the dev
  machine being stuck on Python 3.9.
- All three features are **default-off**. Full self-test suite: 20 PASS + 3 correct SKIP
  (undeclared optional deps: `onnxscript`, `fastapi`, `onnxruntime`), zero regressions.

### Not done — requires real hardware (Mode B)
- `onnxruntime` install check on the Pi's Python 3.13 (this is the gate for WOW #3 actually running
  there — likely to work per the PyPI audit above, but "likely" is not "verified").
- DNSMOS per-inference timing measurement on Pi.
- Noise classifier real-mic accuracy (gates whether it's demoed at all — the corpus has ~50 source
  files per class, thin for live-mic generalization).
- Web dashboard LAN + QR code test from an actual phone browser (Android + iOS per the plan).
- 600s stress test with all three features active simultaneously.
- MOS<2.5 warning-path test with intentional garbage input, on the Pi.

---

## Phase 5 — Demo Bulletproofing & Pitch Integration

**Plan's objective:** make demo-day failures (WiFi flooding, USB re-enumeration, someone unplugging
something) into non-events.

### Status: not started

Checked directly against the file system — none of these exist:
- `demo/backup_playback.py` (pre-recorded audio fallback if live mic fails)
- `demo/run_judged_demo.sh` (one-command cold-boot-to-demo script)
- `scripts/preflight_check.py` (pre-demo device/model/self-test verification)
- Auto-restart wrapper for pipeline crashes
- RTF>0.9-for-5s auto-bypass health check
- Presentation deck (10–12 slides)
- Backup demo video
- Before/after audio A/B pair for judges to listen to
- Dress rehearsal

This phase needs the least new *engineering* (most of it is scripting + rehearsal, not research)
but has zero coverage right now, and is explicitly "waiting on user" per `progress.md` since Phase
4 closeout — nothing here is hardware-blocked in the way Phases 1/2/4's Track B items are; most of
it is buildable on the dev machine today.

---

## Master checklist vs. `prototype.md`'s "Final Readiness Gate"

| Item | Status |
|---|---|
| Dual-mic hardware live, PS-explicit requirement met | ❌ Not done |
| End-to-end latency <150ms, measured | ❌ Not measured (estimate only) |
| Physical acoustic mouth-to-ear latency measured | ❌ Not done |
| Data augmentation eval complete | ✅ Done |
| Dual-mic crowd-babble improvement quantified | ✅ Done (offline) — found negative, not positive |
| `atten_lim_db` tuned, PESQ improvements captured | ✅ Done — global, not per-category (better finding) |
| Target compliance ≥8/9 cells green | ✅ **Done — 8/9**, exceeds the plan's own target |
| Full pipeline 10min zero-dropout on real dual-mic hardware | ❌ Not done |
| All self-tests green on dev machine | ✅ 20 PASS + 3 correct SKIP (plan asked for "9... 7+ on Pi") |
| Noise classifier operational, displayed live | ✅ Built, display-only (router killed) |
| Impulsive event log | ✅ Built, reframed away from "shot detection" |
| Web dashboard via QR | ✅ Built, not LAN/phone-tested |
| Judge phone toggle | ✅ Built, not tested |
| DNSMOS live quality score | ✅ Built, Pi timing unverified |
| Auto-degraded-quality warning path | ⚠️ Built (`auto_bypass` flag exists), untested |
| Backup playback mode | ❌ Not started |
| Backup demo video | ❌ Not started |
| Pre-flight check script | ❌ Not started |
| Cold-boot-to-demo <60s | ❌ Not started |
| Full dress rehearsal | ❌ Not started |
| README/architecture.md updated | ✅ Current through this document |
| Presentation deck | ❌ Not started |

---

## What "more needs to be done," in priority order

1. **Pi hardware batch** (per your own stated ordering — batch everything hardware-dependent to the
   end). Covers: Phase 1 dual-mic physical setup + validation, Phase 2 real latency measurement,
   Phase 4 Pi-side WOW validation. This is the largest remaining block of *validation* work (not new
   engineering — the code already exists and is self-tested).
2. **Phase 5**, which needs no hardware for most of its scope and could be built now: backup
   playback script, `run_judged_demo.sh`, preflight check script, auto-restart wrapper. The deck and
   video are the only genuinely time-consuming items and don't block anything else.
3. **Optional, not gating:** closing the remaining 0.82dB non-stationary SI-SNR gap (not yet
   attempted — Phase 3's atten sweep optimized for PESQ, not SI-SNR specifically, so there may be
   room here) and the open clean-speech-pool speaker-diversity defect (2 of 40 speakers).
