# PS26052 — Phase 4 Implementation Plan
## WOW Factors: Three Differentiators

**Source plan:** `prototype.md` § "Phase 4 — WOW FACTORS: Three Differentiators"
**Status:** DRAFT — awaiting sign-off. No code has been modified.
**Written against the repo after Phase 3 completion (6/9 compliance, 17 PASS + 2 SKIP self-tests).**
**Governing rules:** `rules.md` — Rules 1–10, 12 (by analogy), 19, 20, 27, 29, 31, 32, 33 are load-bearing.

---

## 0. How to read this document

Section 1 contains **five corrections to `prototype.md`**, one of which invalidates a WOW factor's core
premise using Phase 3's own measured data, and one of which *unblocks* a WOW factor everyone assumed
was dead. Read it first — it changes what this phase should build. Sections 2–3 are objective and
code-verified ground truth. Section 4 lists **six decisions needing sign-off**. Section 5 is the work,
split Track A / Track B. Section 6 is the `progress.md` logging contract. Sections 7–13 are
verification, risk, rollback, gate, and scope.

**Hardware reality:** unlike Phase 3, Phase 4 is **heavily Pi-dependent** — every WOW factor's *value*
is in the live demo. Track A builds and unit-tests everything; Track B validates on hardware and joins
your deferred Pi batch. One item (§ 4 D2) is worth pulling forward as a deliberate 5-minute exception,
and I explain why.

---

## 1. Five corrections to `prototype.md`

### 1.1 WOW #1's "Adaptive Attenuation Router" has nothing left to route — Phase 3 measured it away

`prototype.md` § WOW #1 specifies a classifier that *"feeds decision to `LivePipeline._policy_router`
which sets `atten_lim_db` and toggles reference ALE."* The entire premise is that different noise
categories want different attenuation.

**Phase 3 T4 measured that they don't.** From `results/atten_sweep.csv`:

| Category | Best `atten_lim_db` | Best `post_filter` | PESQ at optimum |
|---|---|---|---|
| stationary | **30** | **off** | 2.5023 |
| non_stationary | **30** | **off** | 2.1371 |
| impulsive | **30** | **off** | 2.6299 |

All three categories share the **identical** optimum, and the response is monotonic in every category
(PESQ falls as attenuation rises: stationary 2.5023 → 2.4217 from 30 → 100 dB). This is why Phase 3
correctly committed a **single global** `atten_lim_db: 30` rather than the
`model.atten_lim_db_by_category` map `prototype.md` § 3.3 anticipated.

**Consequence:** a router that selects attenuation per category would select 30 dB every time. It is a
no-op with extra moving parts and extra failure modes in front of judges.

The second routing lever — *"toggles reference ALE"* — is also weakened by Phase 3: the realistic
(non-oracle) reference made NLMS **strongly negative** on crowd babble. That *might* support a genuine
policy ("disable the reference stage when crowd babble is detected"), but only if Phase 3's data shows
the effect is category-*dependent* rather than uniformly negative. That must be checked against the
committed data **before** building a router on it (§ 5 T1), not assumed.

Per Rule 27, a narrative that contradicts the measured implementation must be corrected, not repeated.

### 1.2 DNSMOS is **not** blocked on the Pi — the documented ONNX blocker doesn't apply to it

Everyone reading this repo would reasonably conclude WOW #3 is dead. `requirements-optional.txt` says:

> ⚠️ KNOWN INCOMPATIBLE ON PYTHON 3.13 (the Pi's version) … `onnx` requires `ml_dtypes`, and EVERY
> published ml_dtypes release declares `numpy>=2.1.0; python_version >= "3.13"`. deepfilternet
> requires numpy<2.0 … a hard upstream constraint.

That is accurate — **for the `onnx` package**, which the P1-3 *export* path needs. DNSMOS needs only
**`onnxruntime`** for *inference*. Verified against PyPI metadata for onnxruntime 1.29.0:

| Property | Value | Implication |
|---|---|---|
| numpy bound | `numpy>=1.21.6` — **no upper bound** | Compatible with the `numpy==1.26.4` pin |
| `ml_dtypes` | **optional extra** (`quantization`), not required | The ml_dtypes→numpy≥2.1 conflict never triggers |
| `onnx` | **not** a dependency | The documented blocker is bypassed entirely |
| requires_python | `>=3.11` (supports 3.11–3.14) | Pi's 3.13 ✓ |
| Wheels | publishes `manylinux_2_17_aarch64` | Pi's ARM64 ✓ |

**WOW #3 is very likely viable on the Pi.** This must still be confirmed on the actual device (§ 4 D2)
— PyPI metadata is not an install — but the a-priori blocker dissolves. This is a meaningful unblock:
roughly a third of the phase was presumed impossible.

### 1.3 …but the dev machine can't run the same onnxruntime the Pi will

**Dev machine is Python 3.9.25.** `onnxruntime` requires `>=3.11`. So DNSMOS **cannot be developed
against the same runtime version the Pi will run**, and `uv run python -c "import onnxruntime"` fails
on dev today. Confirmed missing alongside every other WOW dependency:

```
fastapi: MISSING   uvicorn: MISSING   onnxruntime: MISSING   qrcode: MISSING   sklearn: MISSING
torch: OK
```

This needs an explicit decision (§ 4 D3), not discovery mid-implementation.

### 1.4 "FastAPI already in Python-optional" is false

`prototype.md` § WOW #2: *"FastAPI already in Python-optional; add to requirements-optional.txt."*
Self-contradictory, and the first half is wrong — `requirements-optional.txt` contains only `numba`,
`scipy`, and the ONNX block. `fastapi`, `uvicorn`, and `qrcode` are absent and not installed. Minor,
but it means WOW #2 starts with dependency work that the plan budgets at zero.

`sklearn` is also missing — relevant because it is the obvious choice for classifier metrics/splitting.
`torch` **is** available, so a small PyTorch classifier needs no new heavy dependency.

### 1.5 "Acoustic shot-detection" is an overclaim the project's own Rule 32 forbids

`prototype.md` § WOW #1: *"log every impulsive event with timestamp → doubles as acoustic
shot-detection, an actual defence capability worth naming."*

A 3-class classifier trained to separate stationary / non-stationary / impulsive **cannot** distinguish
a gunshot from a door slam, a dropped object, a hand clap, or a balloon pop — all impulsive. It has
never been evaluated as a *detector* (no precision/recall on an event-detection task), only as a
classifier over synthetic mixtures.

Rule 32 sets the precedent exactly: do not describe the system as "true ANC" without the hardware that
would justify it. The same discipline applies here. In front of DRDO evaluators — who will know what
real acoustic gunshot localisation involves (multi-sensor arrays, triangulation, extensive field
validation) — "shot detection" is a claim that invites a question the system cannot answer.

---

## 2. Objective and Definition of Done

### 2.1 Objective

Add demo-facing differentiators that are **honest under questioning**: a situational-awareness display,
a judge-operable live dashboard, and continuous self-quality monitoring — each with its capability and
its limits measured and stated.

### 2.2 Definition of Done

| # | Condition | Verified by |
|---|---|---|
| DoD-1 | Noise classifier trained with a **leakage-free grouped split**, accuracy reported on held-out *source files* | `results/classifier_eval.json` + confusion matrix |
| DoD-2 | Classifier accuracy measured on **real recorded audio**, not just synthetic mixtures | `results/classifier_realmic_eval.json` |
| DoD-3 | Classifier exposes calibrated confidence and an explicit `UNCERTAIN` state below threshold | Self-test + demo behaviour |
| DoD-4 | Web dashboard serves live telemetry over LAN; judge can toggle enhance/bypass from a phone | Pasted Pi session + phone screenshot |
| DoD-5 | QR code resolves to the dashboard on a phone browser | Track B evidence |
| DoD-6 | DNSMOS runs on-device; per-inference time **measured on Pi**, not asserted | `results/dnsmos_timing_pi.json` |
| DoD-7 | DNSMOS model origin, version, and licence recorded (Rule 12 discipline) | `models/dnsmos/SOURCES.md` |
| DoD-8 | **RTF impact of all background threads measured**, not assumed | 600 s stress with every feature on |
| DoD-9 | No capability is described beyond what was measured (Rules 32/33) | README / `architecture.md` review |

### 2.3 Explicitly NOT the goal

- **Not** shot detection (§ 1.5).
- **Not** an adaptive attenuation router, unless § 5 T1 finds an evidence-backed policy dimension (§ 1.1).
- **Not** retraining DFN3.
- **Not** a production web service — no auth, LAN-only, demo-scoped, and stated as such.

---

## 3. Ground truth — code-verified

| Fact | Anchor |
|---|---|
| Manifest: 300 mixtures, exactly 100 per category | `data/manifest.csv` |
| **Only 155 unique `noise_id` values** across 300 mixtures | verified via manifest count |
| 123 unique `clean_id` values | verified via manifest count |
| Subtypes: engine 50, vehicle 50, helicopter 60, crowd 40, explosion 40, artillery 34, gunshot 26 | manifest |
| Crowd babble is **synthetic** (6 overlapped utterances), logged as a proxy subtype | `scripts/generate_babble_noise.py`, `data/SOURCES.md` |
| All three categories share optimum atten 30 / post_filter off | `results/atten_sweep.csv` |
| Committed config is a single global value, not per-category | `config/audio_config.yaml:117` |
| `demo/dashboard.py` **already** mutates `pipeline._mode` from a key-listener thread | `demo/dashboard.py:114-116` |
| `last_in_chunk` / `last_out_chunk` display hooks exist, explicitly display-only | `live/pipeline.py` |
| `fastapi`/`uvicorn`/`qrcode`/`onnxruntime`/`sklearn` absent; `torch` present | verified § 1.3 |
| Pi is Python 3.13; dev is Python 3.9.25 | `requirements-optional.txt` notes; verified |

### 3.1 The cross-thread mutation question is already settled

`demo/dashboard.py:114-116` does `pipeline._mode = new_mode` from a separate listener thread today, and
that has been running on the Pi through the 10-minute stress gates. So WOW #2's `/mode/{...}` endpoint
is **not** a new hazard class — it is the same pattern from a different trigger. It should reuse
whatever the dashboard does, so any needed engine/filter reset is handled in exactly one place rather
than diverging between the two entry points.

### 3.2 The classifier's data problem, quantified

300 mixtures drawn from **155 unique noise files** ≈ 2 mixtures per noise clip, ~50 unique source files
per class. Two consequences that must shape the work:

1. **A random split by mixture leaks.** The same noise clip appears in train and test at different
   SNRs and with different clean speech. Reported accuracy would be inflated by memorising noise
   instances. The split must be **grouped by `noise_id`** (ideally by source file).
2. **~50 unique sources per class is a small dataset** for a classifier expected to generalise to a
   room, a phone speaker, and a USB mic at demo time. High synthetic validation accuracy will **not**
   imply live reliability. DoD-2 exists for this reason.

---

## 4. Decisions requiring sign-off

### D1 — Reframe WOW #1 as situational-awareness display, not a router *(recommended)*

Given § 1.1, three options:

| Option | What it is | Verdict |
|---|---|---|
| **A. Display-only + honest confidence** | Classifier shows detected category with confidence and an `UNCERTAIN` state; drives nothing | **Recommended** |
| B. Router on an evidence-backed lever | Keep routing, but only for a policy T1 proves is category-dependent (candidate: disable reference stage on crowd) | Only if T1 finds it |
| C. Drop WOW #1 | Skip entirely | Reserve for time pressure |

**Why A:** the demo value was always the *visible* moment — "STATIONARY (engine)" flipping to
"IMPULSIVE" while a judge plays sounds. That works without touching the audio path, and keeps a
fragile ML component out of the signal chain entirely. A wrong classification then costs a label, not
the audio. **B stays open** — T1 is a cheap check against data we already have.

### D2 — Pull the onnxruntime Pi check forward as a deliberate exception *(recommended)*

This conflicts with your batch-all-Pi-work rule, so it is your call. The argument for an exception:

- It is **one SSH command**, ~5 minutes: `pip install onnxruntime` then `import onnxruntime`.
- It gates **all of WOW #3** — roughly a third of the phase.
- Without it, Track A builds a full DNSMOS integration that might be unusable, and you'd discover that
  only in the final Pi batch, with no time to re-plan.
- § 1.2 says the blocker probably dissolves, but "probably" is doing real work in that sentence, and
  Rule 2 says verify rather than assume.

**Recommendation:** make this single check the one exception. If you'd rather keep the batch intact,
say so and I'll sequence WOW #3 **last** in Track A so a failed gate wastes the least work.

### D3 — How to develop DNSMOS given dev 3.9 vs Pi 3.13 *(recommended: pinned older runtime on dev)*

| Option | Trade-off |
|---|---|
| **A. Older `onnxruntime` on dev (last cp39 build), current on Pi** | **Recommended** — ONNX models are portable and the basic `InferenceSession` API is stable across these versions; note the version difference in the log |
| B. Upgrade the dev venv to Python 3.11+ | Cleanest parity, but revalidates the entire dev toolchain mid-project — high blast radius for one feature |
| C. Mock DNSMOS on dev; real only on Pi | Zero dev dependency, but the integration is then untested until the Pi batch |

**Recommendation:** A, with the dev/Pi version difference explicitly recorded per Rule 5 (any timing
number from dev is a dev number and never a Pi claim).

### D4 — Grouped split + a real-mic validation set *(recommended)*

Two requirements, both from § 3.2:

1. **Split grouped by `noise_id`** — never a random per-mixture split. Report accuracy on held-out
   source files, and state the split method in the results file so the number is interpretable.
2. **Record a small real-audio validation set** (~20–30 clips: the actual sounds you plan to demo,
   through the actual mic, in a room). This converts "will it generalise?" from an unknown into a
   measured number, and it is the single highest-value item in WOW #1.

If a USB mic can be plugged into the dev machine, (2) is Track A. Otherwise it joins Track B — but
**it should gate whether the classifier is demoed at all** (§ 8 R1).

### D5 — Rename the impulsive log; drop the "shot detection" claim *(recommended)*

Per § 1.5 and Rule 32's precedent. Keep the feature — a timestamped log of detected impulsive events
is genuinely useful and demoable. Call it **"impulsive-event log"**. In the pitch, describe it as
*"timestamped logging of impulsive acoustic events"* and, if asked about gunshot detection, answer
honestly: the classifier separates broad noise categories and has not been evaluated as a firearm
detector. That answer is stronger than a claim that collapses under one follow-up question.

### D6 — Build order if time runs short *(recommended: #2 → #3 → #1)*

`prototype.md` budgets 3 days for all three. Ranked by (demo value ÷ risk):

1. **WOW #2 (web dashboard)** — highest value, lowest risk. No ML generalisation problem, no dependency
   blocker, and judges *touching* it is the memorable part. Build first.
2. **WOW #3 (DNSMOS)** — genuinely differentiating, now likely unblocked; gated on D2.
3. **WOW #1 (classifier)** — highest risk of visible failure, and its headline feature was just
   invalidated (§ 1.1). Build last, demo only if DoD-2 supports it.

---

## 5. Work breakdown

### TRACK A — Dev machine

**T0 — Dependency gate** *(blocking)*
Add `fastapi`, `uvicorn`, `qrcode` to `requirements-optional.txt` with pin rationale in the established
house style (why this version, what it conflicts with). Verify each installs on dev via `uv`. Record
the dev `onnxruntime` version chosen under D3. **Nothing in `requirements.txt`** — the core demo path
must stay installable (the 2026-08-24 scipy incident is the precedent).

**T1 — Re-ground the routing premise** *(cheap; decides D1-B)*
Query the committed Phase 3 dual-mic results: is the realistic-reference NLMS penalty **category-
dependent** (bad on crowd, fine elsewhere) or **uniformly negative**? If category-dependent, there is
one evidence-backed policy worth routing and D1-B opens. If uniform, the router is dead and WOW #1 is
display-only. Log the finding either way — a negative result here saves a day of work.

**T2 — Noise classifier** *(WOW #1, per D1/D4)*
- `models/noise_classifier/` — small PyTorch model on log-mel features (no new heavy dep; `torch` present).
- **Grouped split by `noise_id`** (D4). Report per-class precision/recall + confusion matrix, not just
  accuracy — with 3 classes and ~50 sources each, aggregate accuracy hides per-class failure.
- Confidence calibration + `UNCERTAIN` below threshold (DoD-3).
- `classify_chunk.py` with a self-test asserting output shape, class range, and that the grouped split
  contains **zero** `noise_id` overlap between train and test (an assertion, so leakage cannot
  silently return).
- Background thread at 500 ms cadence; display-only under D1-A.

**T3 — Impulsive-event log** *(per D5)*
Timestamped JSONL of detected impulsive events with confidence. Named and documented as
impulsive-event logging, **not** shot detection.

**T4 — Web dashboard** *(WOW #2 — build first per D6)*
- `demo/webdash/` — FastAPI + WebSocket + single static page, canvas waveform.
- Telemetry at 4 Hz from the existing `last_in_chunk` / `last_out_chunk` display hooks — **zero
  hot-path change** (they are already documented as display-only with a benign race).
- `/mode/{enhance|bypass}` reusing `demo/dashboard.py`'s existing mode-switch path (§ 3.1) so both
  entry points share one implementation.
- QR generation script encoding `http://<pi-lan-ip>:8080`.
- Bind explicitly to the LAN interface; document that it is unauthenticated and demo-scoped.
- Self-test: start the app with a mock pipeline object, assert the WS emits well-formed telemetry and
  the toggle endpoint flips mode — no audio hardware required.

**T5 — DNSMOS integration** *(WOW #3 — gated on D2)*
- `models/dnsmos/` + **`models/dnsmos/SOURCES.md`** recording model URL, version/commit, licence, and
  citation (Rule 12 discipline applied to a downloaded model).
- Background thread, 0.5 Hz, 9 s window.
- **Window-fill state**: the first score is only valid after 9 s of audio; the UI must show
  "measuring…" rather than a misleading number (§ 1.x UX note below).
- Threshold warning at MOS < 2.5; **auto-bypass off by default** — an automatic mode flip mid-demo is
  a bigger risk than a low number on screen.
- Self-test with a synthetic signal asserting the score is finite and in range.

**T6 — UI surfacing**
Category + confidence + MOS on terminal dashboard, spectrogram, and web dashboard. One telemetry
struct feeding all three, so the surfaces cannot drift apart.

**T7 — Self-tests + docs**
Register every new self-test in `scripts/run_all_selftests.py` (currently 17 PASS + 2 SKIP; must stay
green with zero regressions). Update `architecture.md` **before** the new directories land (Rule 7).

---

### TRACK B — Raspberry Pi *(joins the deferred batch)*

| ID | Task | Gate |
|---|---|---|
| B1 | `pip install onnxruntime` + import check | **Pull forward per D2** |
| B2 | DNSMOS per-inference timing **measured on Pi** | DoD-6; replaces the uncited "~5 ms" |
| B3 | Classifier accuracy on real mic audio | DoD-2; gates whether it is demoed |
| B4 | Web dashboard reachable from a phone over LAN; QR scan; toggle | DoD-4/5 |
| B5 | **600 s stress with classifier + DNSMOS + dual-mic all active** | DoD-8 — the RTF-impact measurement |
| B6 | MOS < 2.5 warning path (feed deliberate garbage) | Verify it fires |

**B5 is the one that matters most.** `prototype.md` asserts "no RTF impact" twice. On a 4-core Pi 5
already running DFN3 at RTF 0.29–0.40 plus Phase 1's dual-mic NLMS, adding two background inference
threads **will** contend for CPU. It also interacts directly with Phase 2's core-pinning work (B3
there), which was planned before these threads existed. Measured, not assumed — Rule 1.

---

## 6. Logging contract — `progress.md`

> Rule 3: nothing is done until evidence is pasted. Rule 10: log per increment.

### 6.1 Entry skeleton

```markdown
## <YYYY-MM-DD> — Phase 4: <task ID> <short title>

**Machine:** <devmachine (Win 11, x86_64, Python 3.9.25, uv venv) | Pi 5 (Debian 13, Python 3.13)>
**Track:** <A (dev) | B (Pi hardware, Mode B)>
**WOW factor:** <#1 classifier | #2 webdash | #3 DNSMOS | cross-cutting>

### What changed
<files touched, one line each, with the reason>

### Evidence
<exact command>
<verbatim pasted output>

### Result
<PASS / FAIL / PARTIAL — for FAIL, the real error text per Rule 4>
```

### 6.2 Mandatory rules for every Phase 4 entry

1. **Name the machine on every timing or accuracy number** (Rule 5). A dev-machine DNSMOS timing is
   never presented as a Pi figure — and under D3 the *runtime versions differ*, so the distinction is
   substantive, not cosmetic.
2. **State the classifier's split method next to any accuracy number.** An accuracy without "grouped
   by `noise_id`" is uninterpretable and probably leaked (§ 3.2).
3. **Report per-class precision/recall, never accuracy alone** (Rule 28's spirit: no silently omitted
   cells).
4. **Never write "shot detection"** (D5, Rule 32). Impulsive-event logging.
5. **Never write "no RTF impact" until B5 measures it** (Rule 1). Until then it is an open question.
6. **Record the DNSMOS model's origin and licence before using it** (Rule 12 discipline).
7. **Log negative results** — T1 finding no routable policy is a finding worth a day saved.
8. **Root-cause surprises against the code before narrating them** (Rule 27).

### 6.3 Required evidence per task

| Task | Command to paste | Must show |
|---|---|---|
| T0 | dependency install | Each package resolving; core `requirements.txt` untouched |
| T1 | query over Phase 3 results | Category-dependent or uniform, with the numbers |
| T2 | training + eval | Grouped split proof (zero `noise_id` overlap), confusion matrix, per-class P/R |
| T4 | webdash self-test | WS telemetry well-formed; toggle flips mode |
| T5 | DNSMOS self-test | Finite in-range score; `SOURCES.md` present |
| T7 | `run_all_selftests.py` | Full summary, new tests PASS, **zero regressions** |
| B1 | `pip install onnxruntime` on Pi | Install output + successful import |
| B2 | timing harness on Pi | Median + p95 per-inference ms |
| B3 | real-mic eval | Accuracy + confusion matrix on recorded audio |
| B5 | 600 s stress, all features on | Verdict, dropouts, RTF p95 **vs the Phase 2 baseline** |

### 6.4 Closing entry

Per WOW factor: what it does, what was measured, what it explicitly does **not** do. The last column
is what keeps the demo honest under questioning — and it is where "not a firearm detector" and the
measured RTF cost get recorded.

---

## 7. Test plan

**Mode A:** every new module carries a self-test (Rule 8) registered in the runner. Suite must stay
green — 17 PASS + 2 SKIP today, zero regressions. The webdash self-test uses a mock pipeline so it
needs no audio hardware. The grouped-split assertion is part of the classifier self-test, so leakage
cannot silently reappear.

**Mode B (Rule 29):** hand off exact commands, wait for pasted output. Order: B1 → B2 → B3 → B4 → B5 → B6.

**Regression guard:** every Phase 4 feature is default-off. With `noise_classifier.enabled: false`,
`dnsmos.enabled: false`, and the webdash not started, the pipeline must be byte-for-byte the Phase 3
demo path.

---

## 8. Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Classifier misfires live in front of judges | **High** | **High** | D1-A (display-only), `UNCERTAIN` state, DoD-2 gates whether it's demoed at all |
| R2 | onnxruntime fails on Pi despite § 1.2 | Low-Med | High | D2 pulls the check forward; WOW #3 sequenced last otherwise |
| R3 | Background threads push RTF over budget | **Med-High** | **High** | B5 measures it; features are independently switchable so the demo can shed load |
| R4 | Synthetic-trained classifier collapses on real mic | **High** | Med | Expected — that's what DoD-2 measures; honest fallback is display-with-confidence or drop |
| R5 | Dev/Pi onnxruntime version skew causes behaviour difference | Med | Med | D3-A + explicit version logging; B2 is the authoritative timing |
| R6 | Web dashboard exposed unauthenticated on a shared network | Med | Low-Med | LAN-only bind, demo-scoped, documented; no secrets served |
| R7 | 3-day estimate overruns | **High** | Med | D6 build order means the highest-value item ships first |
| R8 | Auto-bypass on low MOS fires mid-demo | Med | High | Default **off**; warning is visual only |
| R9 | "Shot detection" reaches a slide and gets challenged | Med | **High** | D5; § 6.2 rule 4 makes it a logging violation |

---

## 9. Backward compatibility and rollback

All additive and default-off:

| Setting | Default | Effect at default |
|---|---|---|
| `noise_classifier.enabled` | `false` | No thread, no model load |
| `dnsmos.enabled` | `false` | No thread, no onnxruntime import |
| webdash | not started | No server, no port bound |

New dependencies go to `requirements-optional.txt` only. **`requirements.txt` is untouched** — the core
demo path stays installable on the Pi regardless of any Phase 4 resolver failure.

**Rollback:** flip the three defaults; new directories are inert. `git revert` of Phase 4 leaves
Phases 1–3 intact — nothing here modifies the signal path under D1-A.

---

## 10. Acceptance gate

**Gate A — dev**
- [ ] T0 deps added to *optional* only; core untouched
- [ ] T1 routing question answered with data; D1 resolved
- [ ] Classifier: grouped split proven (zero `noise_id` overlap), per-class P/R + confusion matrix
- [ ] `UNCERTAIN` state implemented
- [ ] Webdash self-test green with mock pipeline
- [ ] DNSMOS `SOURCES.md` with origin + licence
- [ ] `architecture.md` updated **first** (Rule 7)
- [ ] Suite green, zero regressions
- [ ] Default-off regression check passes

**Gate B — Pi**
- [ ] onnxruntime installs and imports
- [ ] DNSMOS per-inference time measured
- [ ] Classifier accuracy on real mic measured → demo/no-demo decision recorded
- [ ] Dashboard reachable by phone; QR scans; toggle works
- [ ] 600 s stress with everything on: verdict + RTF delta vs Phase 2 baseline
- [ ] MOS warning path fires

**Gate C — honesty**
- [ ] No "shot detection" anywhere (Rule 32)
- [ ] No "no RTF impact" claim unless B5 supports it
- [ ] Every accuracy carries its split method; every timing carries its machine
- [ ] Each WOW factor documents what it does **not** do

---

## 11. Out of scope

Firearm detection/localisation · retraining DFN3 · authenticated/production web service · cloud
telemetry · training on new corpora (Rule 15) · ONNX *export* path (still blocked — § 1.2 unblocks
inference only) · Jetson port.

---

## 12. Effort estimate

| Item | Estimate |
|---|---|
| T0 deps + T1 routing check | 0.5 day |
| T4 webdash *(first per D6)* | ~1 day |
| T5 DNSMOS | ~0.75 day |
| T2/T3 classifier + real-mic set | ~1 day |
| T6/T7 UI surfacing, self-tests, docs | ~0.5 day |
| **Track A total** | **~3.5 days** |
| Track B (Pi validation) | ~0.5 day |

`prototype.md` says 3 days. That covers the code but not honest evaluation (grouped splits, real-mic
validation, RTF measurement) or the dependency work § 1.4 shows was assumed done. 3.5 + 0.5 is realistic;
D6's ordering means a time-box still ships the highest-value item.

---

## 13. Open question for you

**Do you want the classifier in the demo at all?**

§ 1.1 removed its headline feature, and § 3.2 says ~50 unique noise sources per class is thin for
live-mic generalisation. It remains a genuinely striking demo moment *if it works* — and a
credibility problem the instant it mislabels while a judge watches.

Three positions:

1. **Build it, gate it on DoD-2** *(recommended)* — measure real-mic accuracy first, demo only if it
   holds. Costs a day, decided on evidence.
2. **Build it display-only, never claim more** — show category + confidence, accept occasional errors
   as visibly uncertain rather than wrong.
3. **Drop it, reallocate to #2 and #3** — a polished dashboard plus live self-quality monitoring is
   already a strong differentiator set, with far less that can go wrong on stage.

I recommend (1). But if the schedule tightens, (3) is a more defensible cut than shipping a classifier
that has never seen a real microphone — and D6 orders the work so that cut stays available late.
