# PS26052 — Phase 2 Implementation Plan
## Latency Engineering & Real-Time Grade

**Source plan:** `prototype.md` § "Phase 2 — Latency Engineering & Real-Time Grade"
**Target end-state:** `idea.md` § 3.3 (sub-150 ms interactive-voice latency)
**Status:** DRAFT — awaiting sign-off. No code has been modified.
**Written against the repo after the Phase 1 software commit (branch `main`).**
**Governing rules:** `rules.md` — Rules 1, 3, 4, 5, 8, 10, 29, 30, 33 are load-bearing here.

---

## 0. How to read this document

Sections 1–4 define **what must be true when Phase 2 is done**. Section 5 is **the work**, split into
**Track A (dev machine, buildable now)** and **Track B (Pi, deferred batch)** to match the agreed
working order. Section 6 is the **logging contract** — exact `progress.md` templates, because Rule 3
forbids marking anything done without pasted evidence. Sections 7–11 are verification, risk, rollback,
and the acceptance gate.

Section 4 lists **five decisions that need your answer before implementation starts.** Each has a
recommendation; reply "proceed" and I implement the recommended option.

---

## 1. A correction to `prototype.md` before we start

Three claims in `prototype.md` § Phase 2 do not survive contact with the code. Flagging them now
because they change how the phase must be planned, not merely how it is described.

### 1.1 "No hardware dependency" is false

`prototype.md` labels Phase 2 *"1.5 days · No hardware dependency."* Every acceptance criterion in
its own checklist requires the Pi:

| Checklist item | Why it needs hardware |
|---|---|
| Latency < 150 ms confirmed | Device round-trip is a driver/ALSA measurement |
| Physical acoustic round-trip | Requires physical mic + speaker |
| Thread pinned to dedicated core | `os.sched_setaffinity` is Linux-only; absent on Windows |
| Chunk sweep rerun | Dropout counts are real-time behaviour |
| 10-min stress PASS | Definitionally hardware |

Only the **code** is dev-machine work. Given the agreed order (all dev work first, all Pi work in one
final batch), this plan is split into Track A and Track B throughout. **Track A alone cannot close
Phase 2** — no latency claim is real until Track B runs.

### 1.2 The "~172 ms current latency" is an analytical estimate, not a measurement

From `progress.md` (2026-08-24) and the arithmetic in `live/e2e_latency_test.py:215`:

```
full_estimate = device_roundtrip_ms + inference_ms + priming_ms
              = 42.67              + ~29.5        + 100.0        ≈ 172 ms
```

The module docstring calls this out itself: *"an engineering estimate combining two real measurements,
not one unified physical measurement."* Two consequences:

- Driving this number below 150 by arithmetic alone would produce **a smaller estimate, not a faster
  system.** Phase 2 is only credible if it also produces the first true physical measurement (§ 5.A5 / 5.B5).
- The 42.67 ms was measured on **`snd-aloop`**, a digital loopback — median = p95 = min = max across
  20 reps, which is the signature of a purely digital path. Real USB hardware will not behave this way.

### 1.3 The dominant latency term is our own code, not physics

| Component | Value | Share | Nature |
|---|---|---|---|
| **Priming** | **100.0 ms** | **58 %** | **Self-inflicted; pure standing latency** |
| Device round-trip | 42.67 ms | 25 % | Driver/ALSA, partly irreducible |
| Inference | ~29.5 ms | 17 % | Model compute |

`config/audio_config.yaml` already documents priming as *"PERMANENT STANDING LATENCY, not one-time
warmup cost — it never drains (FIFO)."* At `priming_chunks: 1` and a 100 ms chunk, that is 100 ms
added to every end-to-end path.

**This reorders `prototype.md`'s task list by measured leverage.** Its § 2.3 (numba-JIT the audio
callbacks) targets `_resample`, which is microseconds of `np.interp` — noise against a 100 ms term.
Priming reduction is worth roughly **50–100 ms**; everything else in `prototype.md` § 2 combined is
worth substantially less. The work breakdown in § 5 is ordered accordingly, not in `prototype.md`'s order.

---

## 2. Objective and Definition of Done

### 2.1 Objective

Reduce measured end-to-end latency below the ITU-T G.114 interactive threshold (150 ms) on the real
dual-USB Phase 1 hardware, **and** replace the standing analytical estimate with a genuine
single-path physical measurement.

### 2.2 Definition of Done

| # | Condition | Verified by |
|---|---|---|
| DoD-1 | A **re-baselined** latency budget exists on real dual-USB hardware (not `snd-aloop`) | `results/latency_baseline_dualmic.json` pasted in `progress.md` |
| DoD-2 | Priming is configurable below one whole chunk and the chosen value holds **0 dropouts over 600 s** | `results/stress_priming.json` verdict PASS |
| DoD-3 | A **true physical acoustic round-trip** number exists, with a running pipeline in the loop — first in project history | `results/acoustic_latency.json`, median + p95 over ≥20 reps |
| DoD-4 | DFN3 algorithmic lookahead is **measured empirically**, not read from config (Rule 30) | `results/lookahead_measured.json` |
| DoD-5 | Final chosen configuration passes the full 10-minute dual-mic stress gate | `results/stress_dualmic_final.json` verdict PASS |
| DoD-6 | Every latency figure in `README.md` / `architecture.md` traces to a pasted measurement, **with the machine named** (Rule 5) | `progress.md` entry |
| DoD-7 | If < 150 ms is **not** reached, the gap is disclosed with the real number and the reason (Rule 33) | `progress.md` entry |

**DoD-7 is not a fallback clause — it is a first-class outcome.** A Phase 2 that lands at 158 ms and
says so honestly satisfies this plan. A Phase 2 that reaches "under 150" by shrinking an estimate,
re-parameterising, or quietly excluding a component does not.

### 2.3 Explicitly NOT the goal

- **Not** a quality change. Every latency change must leave PESQ/STOI untouched; any that alters audio
  content (§ 5.A4) requires a bit-equivalence self-test.
- **Not** model optimisation. ONNX/quantisation stays out (blocked on Pi Python 3.13 — see
  `config/audio_config.yaml`).
- **Not** a re-litigation of chunk size on `snd-aloop`. The 50 ms candidate is already documented as
  blocked by a driver-level input overflow; that verdict is re-tested on **real hardware**, where it
  may differ, and nowhere else.

---

## 3. Ground truth — code-verified, not assumed

| Fact | Anchor |
|---|---|
| Priming writes N **whole** chunks of silence; count is an `int` | `live/pipeline.py` `start()`, `silence = np.zeros((chunk_samples, channels))` loop |
| Priming is permanent standing latency, already documented as such | `config/audio_config.yaml` `priming_chunks` comment block |
| Output underruns are already split into real (`_dropped_chunks`) vs teardown (`_teardown_underruns`) | `live/pipeline.py` `_output_callback` |
| Stress verdict gates on `overflows + underruns > 0` | `live/stress_test.py` (`total_dropouts` check) |
| `RingBuffer` uses `threading.Lock` + `threading.Condition` | `live/ring_buffer.py:62-63` |
| The blocking `wait_for` in the output callback is a deliberate, previously-falsified-and-reverted design | `live/pipeline.py` `_output_callback` comment (2026-08-24 experiment) |
| `_resample` is pure `np.interp`, runs **only** when device rate ≠ 48 kHz | `live/pipeline.py` `_resample` |
| Real Pi hardware **does** hit that path (headset ~44.1 kHz, Jabra ~16 kHz) | `config/audio_config.yaml` device comments |
| Full-estimate arithmetic lives in the e2e test, clearly labelled an estimate | `live/e2e_latency_test.py:215` |
| Sweep script writes scratch configs, never mutates the real one | `scripts/sweep_chunk_size.py` `_make_scratch_config` |
| Sweep selection rule is p95 RTF ≤ 0.6 **and** 0 dropouts | `scripts/sweep_chunk_size.py` closing print |
| `df_lookahead` defaults to 0 in installed DFN config; `conv_lookahead` is separate | `.venv/.../df/config.py:35`, `df/deepfilternet.py:16` |
| Phase 1 added a **third** concurrent USB stream + an NLMS stage — both change the RTF budget | `live/pipeline.py` `_ref_callback`, `_inference_loop` |

### 3.1 Two constraints that kill parts of `prototype.md` § 2.3 outright

**(a) The audio callbacks cannot be `njit`-compiled.** `_input_callback` → `RingBuffer.write` →
`threading.Lock`/`Condition`. Numba `nopython` mode cannot compile Python threading primitives. The
*only* njit-able part of the callback path is the pure-numpy `_resample` inner math. Scoped
accordingly in § 5.A4.

**(b) Only the inference thread can be pinned.** `os.sched_setaffinity` affects the calling thread.
The inference thread can pin itself. The audio callbacks run on **PortAudio's internal C threads**,
which Python cannot address this way — so `prototype.md`'s *"use 2 cores for audio callbacks, 2 for
inference"* is not implementable as written. What **is** implementable: pin the inference thread away
from core 0 and measure whether jitter improves. Treated as a hypothesis to test, not a fix to apply.

### 3.2 A naming collision worth stating once

`rules.md` numbers the **historical project phases** (its "Phase 2" = dataset generation, Rules 12–16;
"Phase 4" = PESQ/STOI, Rules 22–26). `prototype.md` numbers a **new sprint** on top of finished work.
They are different axes. This document is `prototype.md` Phase 2 (latency); the `rules.md` rules that
actually bind it are the **global** ones (1–10) plus the **Phase 5 addendum** (29, 30, 33), because
this is live-hardware work. Rules 12–28 concern dataset and offline-eval work and do not apply.

Rule 11 ("do not start Phase 2+ until Phase 1 DoD is met") refers to the historical phases, all long
complete. It is *not* a blocker here — but its spirit is: Phase 1's **Track B** is still outstanding,
so § 5.B0 re-baselines on real hardware before any Phase 2 tuning, and Phase 2's Track B runs *after*
Phase 1's Track B in the single Pi batch.

---

## 4. Decisions requiring sign-off

### D1 — Fractional priming instead of integer chunks *(recommended: yes)*

Today `priming_chunks` is an `int`, so the only options are 100 ms (1 chunk) or 0 ms — a binary choice
between "58 % of the latency budget" and "no jitter absorption at all."

**Recommendation:** make it a **float**, and prime `round(priming_chunks * chunk_samples)` samples.
`1.0` reproduces today's behaviour exactly (backward compatible); `0.5` gives 50 ms — halving the
dominant latency term while retaining half a chunk of jitter absorption. This converts an all-or-nothing
gamble into a tunable knob, and is ~4 lines.

| Option | Standing latency | Jitter absorption | Verdict |
|---|---|---|---|
| `1.0` (today) | 100 ms | 1 full chunk | Safe, misses target |
| **`0.5`** | **50 ms** | **half chunk** | **Recommended starting point** |
| `0.25` | 25 ms | quarter chunk | Try if 0.5 passes cleanly |
| `0.0` | 0 ms | none — buffer runs at zero occupancy | Highest risk; test last |

**Why `0.0` is genuinely risky, not merely aggressive:** with zero priming the output buffer's
steady-state occupancy is ~0, so *every* scheduling hiccup must be absorbed by the output callback's
blocking `wait_for`. That blocking wait is itself the thing the 2026-08-24 experiment showed must not
be removed. Measured p95 RTF 0.40 says there is ~60 ms of compute slack per chunk, but slack only
helps if something is buffered. Empirical question — settled in § 5.B2, not by argument.

### D2 — Cold-start underrun tolerance *(recommended: yes, with a hard cap)*

At reduced priming the first few output callbacks fire before inference has produced anything. Those
are startup transients, not real-time failures — the same category distinction the codebase already
makes for teardown underruns.

**Recommendation:** add a third counter, `_startup_underruns`, active only for a bounded
`startup_grace_sec` (default **0.5 s**), excluded from the stress verdict. Cap it hard: if underruns
continue past the grace window they count as real failures.

**The trap to avoid:** an unbounded grace period would let a genuinely broken configuration report
PASS. The grace window must be a fixed wall-clock bound, and the count must be **printed and stored
in the JSON** even though it is excluded from the verdict, so it can never hide a regression silently.
This mirrors how `_teardown_underruns` is already reported-but-excluded.

### D3 — Where the physical acoustic measurement gets its second channel *(recommended: reference mic)*

`progress.md` records why this measurement never happened: *"the click-based `e2e_latency_test.py`
method can't run against physically separate mic/headset hardware."* True — `sd.playrec` needs a wired
path, and it does not have a running pipeline in the loop.

Phase 1 changes this. There are now **two microphones**.

**Recommendation — method:**
1. Run the full `LivePipeline` in enhance mode on real hardware.
2. Emit a click from an external source into the **primary** mic.
3. Place the **reference** mic at the output speaker.
4. Record both mics; cross-correlate click-at-primary against click-at-reference-output.

The delta is a genuine mouth-to-ear number **with inference in the loop** — exactly what the project
has never had. Requires the mic-pair calibration offset from Phase 1 to be subtracted (already
measured by `live/calibrate_mic_pair.py`).

**Two hazards to design around, not discover during the run:** (a) acoustic feedback — output into
primary mic can howl; keep `output_gain` low and separate the mics physically. (b) The reference mic
is simultaneously feeding the NLMS stage; the measurement run should set
`reference_nlms.enabled: false` so the filter does not adapt away the very click being measured.

### D4 — numba on `_resample`: measure-first, keep-only-if-it-helps *(recommended)*

`prototype.md` § 2.3 asks for njit on the callbacks. Per § 3.1(a) only `_resample` qualifies, and
`np.interp` is already compiled C. The honest expectation is a **negligible** gain.

**Recommendation:** implement it behind a config flag, benchmark before/after **on the Pi**, and
**delete it if it does not measurably help.** Carrying a numba dependency deeper into the hot path for
an unmeasured gain is a net loss. `prototype.md` § 3.3 already sets this precedent
("dropped honestly if not — no cherry-picking"); the same standard applies here.

### D5 — Core pinning as a tested hypothesis, not an applied fix *(recommended)*

Per § 3.1(b), only the inference thread is pinnable from Python.

**Recommendation:** implement `pipeline.cpu_affinity` (default `null` = no pinning, i.e. today's
behaviour). Guard on `hasattr(os, "sched_setaffinity")` so it is a clean no-op on Windows. Run an
A/B on the Pi comparing RTF p95 and dropout counts pinned vs unpinned. **Keep it only if the A/B
shows a real improvement.** Pinning can degrade performance by removing the scheduler's freedom to
migrate work; asserting it as a win without the A/B would violate Rule 1.

---

## 5. Work breakdown

### TRACK A — Dev machine (buildable now, no hardware)

---

**A0 — Latency budget accounting module** · `live/latency_budget.py` *(new)*

Single source of truth for the budget so the arithmetic stops living inside a print statement in
`e2e_latency_test.py`.

- `LatencyBudget` dataclass: `device_roundtrip_ms`, `inference_ms`, `priming_ms`, `resample_ms`,
  `lookahead_ms`, plus `total_estimate_ms` and a `measured_physical_ms` field that stays `None` until
  a real § A5 measurement fills it.
- `to_json()` / `from_json()`, and a `render_table()` that prints each component with its **share of
  total** and, critically, a `source` field per component: `"measured"` vs `"estimated"` vs `"configured"`.
- **Rule 5 compliance is structural, not editorial:** every record carries a mandatory `machine` field
  (`"pi5"` / `"devmachine"`). A budget that mixes sources must render them distinctly, so a
  dev-machine number can never be silently presented as a Pi result.
- Self-test: construct a known budget, assert the total, assert mixed-source rendering flags itself,
  assert round-trip JSON fidelity.

**A1 — Fractional priming** · `live/pipeline.py`, `config/audio_config.yaml` *(per D1)*

- Change `priming_chunks` parse from `int(...)` to `float(...)`.
- Replace the whole-chunk write loop with a single `round(priming_chunks * chunk_samples)`-sample write.
- Guard: negative → `ValueError`; `0.0` → skip the write entirely.
- Config: document the new float semantics and that `1.0` is the previous default, with the measured
  100 ms figure cited.
- Self-test (extend the pipeline's existing coverage or add `--self-test`): assert the primed sample
  count for `1.0` / `0.5` / `0.0`, and assert `1.0` is byte-identical to the pre-change behaviour.

**A2 — Cold-start underrun tolerance** · `live/pipeline.py`, `live/stress_test.py` *(per D2)*

- Add `_startup_underruns` + `pipeline.startup_grace_sec` (default `0.5`).
- In `_output_callback`, classify an underrun as startup if `time.monotonic() - _stream_start_t <
  startup_grace_sec`, else as a real `_dropped_chunks`.
- `_print_stats` and the stress JSON both report all three buckets explicitly.
- `stress_test.py`: exclude startup underruns from the verdict; **print them regardless**; add
  `startup_underruns` to the summary dict.
- Self-test: simulate underruns inside and outside the window, assert correct bucketing and that the
  verdict is unaffected by in-window ones but fails on out-of-window ones.

**A3 — CPU affinity control** · `live/cpu_affinity.py` *(new)* + `live/pipeline.py` *(per D5)*

- `set_thread_affinity(cores: list[int] | None) -> bool` — returns `False` and warns (never raises)
  when unsupported. Guard on `hasattr(os, "sched_setaffinity")`.
- Called from inside `_inference_loop` at thread start, so it applies to the correct thread.
- Config `pipeline.cpu_affinity: null` (default = today's behaviour).
- Self-test: on Windows assert the graceful `False`; on Linux assert a round-trip via
  `os.sched_getaffinity`. **Must pass on both platforms** — dev machine is Windows.

**A4 — Optional numba `_resample`** · `live/pipeline.py` or `live/fast_resample.py` *(per D4)*

- njit variant of the linear-interpolation resampler, behind `pipeline.fast_resample` (default `false`).
- Lazy import — the established pattern (a disabled feature must never break the core path).
- Self-test: **bit-equivalence against the existing `_resample`** across several rate pairs
  (44100→48000, 16000→48000, 48000→48000), plus a dev-machine microbenchmark printing both timings.
- Explicitly reversible: if § 5.B4 shows no Pi gain, this file is deleted and the config key removed.

**A5 — Physical acoustic latency test** · `live/acoustic_latency_test.py` *(new)* *(per D3)*

- Dual-mic click capture against a **running pipeline**; cross-correlation between primary-click and
  reference-output-click; subtracts the Phase 1 calibration offset.
- ≥20 reps; reports median / p95 / min / max; writes `results/acoustic_latency.json`.
- Refuses to emit a number when the click is not cleanly detected — reuse the `min_peak_ratio` +
  `RuntimeError` discipline from `find_click_lag` rather than returning a silently-bogus lag.
- Registered as `python live/main.py acoustic-latency`.
- Mode A self-test: synthetic two-channel arrays with a known injected delay; assert recovery within
  ±1 sample; assert `RuntimeError` on a click-free recording.

**A6 — Empirical lookahead measurement** · extend `live/acoustic_latency_test.py` *(Rule 30)*

Rule 30 requires lookahead to be *measured*, never asserted from config. Implement
`measure_model_lookahead()`: push an impulse through `InferenceEngine.enhance_chunk` and locate the
output response offset relative to `bypass_chunk`. Writes `results/lookahead_measured.json`.

- Mode A self-test on the logic; the DFN3-loaded run is Mode B.

**A7 — Dual-mic-aware sweep** · `scripts/sweep_chunk_size.py`

- Propagate `dual_mic` / `reference_nlms` settings into the scratch configs (currently only
  `chunk_duration_sec` is overridden — a dual-mic sweep would otherwise silently test the single-mic path).
- Add `priming_chunks` as a sweepable axis alongside chunk size.
- Add the measured `startup_underruns` column to the summary table.
- Keep the existing scratch-config discipline: never mutate the real config.

**A8 — Docs** · `architecture.md`

Per Rule 7, `architecture.md` is updated **before** the new modules land: add `live/latency_budget.py`,
`live/cpu_affinity.py`, `live/acoustic_latency_test.py` (+ `live/fast_resample.py` if D4 is taken) to
the component matrix with one-line rationales.

---

### TRACK B — Raspberry Pi (deferred to the single hardware batch)

> Runs **after** Phase 1's outstanding Track B (numba install, calibration, dual-mic stress).
> Both tracks are collected in the cumulative pending table in `progress.md`.

**B0 — Re-baseline on real dual-USB hardware** ← *do this first; nothing else is meaningful without it*

Every latency number on record is `snd-aloop`. Real USB adds transfer latency, and Phase 1 added a
third concurrent stream plus an NLMS stage. **Optimising against the loopback baseline would be
optimising the wrong target.**

```bash
python live/latency_test.py --mode enhance --n-reps 20 --output-json results/latency_inference_dualmic.json
python live/e2e_latency_test.py --n-reps 20 --inference-ms <median from above> --output-json results/latency_baseline_dualmic.json
```

Record the new budget via § A0. Expect it to differ materially from 42.67 ms / 172 ms.

**B1 — Priming validation** *(the dominant lever)*

Stress-test `priming_chunks` at `1.0` → `0.5` → `0.25` → `0.0`, 600 s each, dual-mic active. Select
the **lowest value holding 0 real dropouts** (startup-window underruns excluded per D2, but reported).
Write `results/stress_priming.json`.

**B2 — Chunk-size sweep, dual-mic** — `scripts/sweep_chunk_size.py` with the chosen priming.
Re-test the 50 ms candidate on **real hardware**: its previous rejection was a documented `snd-aloop`
driver artifact and may not reproduce. Selection rule unchanged: smallest chunk with p95 RTF ≤ 0.6 and
0 dropouts.

**B3 — Core-pinning A/B** — 300 s runs, pinned vs unpinned, comparing RTF p95 and dropouts. Keep only
on a demonstrated win (D5). Verify placement with `taskset -pc <pid>`.

**B4 — `fast_resample` A/B** — before/after microbenchmark on Pi. Delete the feature if the gain is not
measurable (D4).

**B5 — Physical acoustic round-trip** — the headline measurement. ≥20 reps, `reference_nlms` disabled
for the run (D3), `output_gain` low to avoid feedback. **First true mouth-to-ear number in the project.**

**B6 — Empirical lookahead** (Rule 30) — run § A6 against the loaded DFN3 model.

**B7 — Final gate** — full 600 s dual-mic stress at the final chosen configuration →
`results/stress_dualmic_final.json`. Must be PASS with 0 real dropouts.

**B8 — Claim reconciliation** — update every latency figure in `README.md`, `architecture.md`, and
`config/audio_config.yaml` comments to the measured values, each labelled with its machine (Rule 5).
Where a target is missed, state the number and the reason (Rule 33).

---

## 6. Logging contract — `progress.md`

> Per Rule 3, nothing below is "done" until its evidence block is pasted into `progress.md`.
> Per Rule 10, log each increment as it completes rather than batching at the end.

### 6.1 Entry skeleton

Append one dated section per work session, newest at the end of the file:

```markdown
## <YYYY-MM-DD> — Phase 2: <task ID> <short title>

**Machine:** <devmachine (Windows 11, x86_64, uv venv) | Pi 5 (Debian 13 trixie, Python 3.13)>
**Track:** <A (dev) | B (Pi hardware, Mode B)>

### What changed
<files touched, one line each, with the reason>

### Evidence
<exact command>
<verbatim pasted output — not paraphrased, not trimmed to the good parts>

### Result
<PASS / FAIL / PARTIAL — and for FAIL, the real error text per Rule 4>
```

### 6.2 Mandatory rules for every Phase 2 entry

1. **Name the machine on every number (Rule 5).** No latency figure appears without it. A dev-machine
   benchmark is never presented as a Pi result under any framing.
2. **Distinguish measured from estimated.** Any composite figure states its components and which were
   measured vs configured. The word "estimate" is not optional decoration on an estimate.
3. **Log failures verbatim (Rule 4).** A regression that raises dropouts gets pasted with its real
   output. No silent retry-and-hide, no paraphrasing an error into something friendlier.
4. **Report missed targets as missed (Rule 33).** If the final number is above 150 ms, write the
   number and the reason. Never re-parameterise to manufacture a pass. The 2026-08-24 entry
   ("~172 ms — close but not met… Reporting this honestly rather than rounding up") is the standard.
5. **Never delete a superseded measurement.** Mark it superseded and keep it, matching how the
   2026-08-26 real-mic stress result supersedes but preserves the 2026-08-24 loopback result.
6. **Keep the cumulative pending-Mode-B table current.** Phase 2's Track B items are appended to the
   table Phase 1 started, so the deferred hardware batch stays a single executable checklist.

### 6.3 Required evidence per task

| Task | Command to paste | Must show |
|---|---|---|
| A0–A8 | `uv run --no-sync python scripts/run_all_selftests.py --skip-dfn` | Full summary; new tests PASS; **zero regressions** |
| A1 | priming self-test | Sample counts for 1.0 / 0.5 / 0.0; `1.0` identical to old behaviour |
| A3 | `live/cpu_affinity.py --self-test` | Graceful no-op on Windows |
| A4 | `live/fast_resample.py --self-test` | Bit-equivalence + both timings |
| A5/A6 | `live/acoustic_latency_test.py --self-test` | Known synthetic lag recovered; raises on no-click |
| B0 | both baseline commands | New dual-USB budget, all components |
| B1 | stress per priming value | Verdict, real dropouts, startup underruns separately |
| B2 | sweep | Full table incl. the re-tested 50 ms row |
| B3/B4 | A/B pairs | Both arms; explicit keep/drop decision |
| B5 | acoustic test | median + p95 over ≥20 reps |
| B6 | lookahead | Measured samples + ms (Rule 30) |
| B7 | `python live/main.py stress --duration 600` | PASS, 0 real dropouts |

### 6.4 Closing entry

Phase 2 ends with a summary table: each budget component, its value, its **source**, and its machine;
the final end-to-end figure; and an explicit `< 150 ms: MET / NOT MET` line. If NOT MET, the gap and
cause are stated in the same table — not in a footnote.

---

## 7. Test plan

**Mode A (dev machine, every commit):** full `run_all_selftests.py` must stay green, with the new
entries registered. The Windows path matters — A3 must no-op cleanly, not raise.

**Mode B (Pi, Rule 29):** hand off the exact command, wait for pasted output, never mark passed from
code review. Order: B0 → B1 → B2 → B3 → B4 → B5 → B6 → B7 → B8.

**Regression guard throughout:** with `dual_mic.enabled: false`, `priming_chunks: 1.0`,
`cpu_affinity: null`, `fast_resample: false`, behaviour must be **identical to today**. Every Phase 2
feature is default-off; the demo path is untouched until a measurement justifies changing it.

---

## 8. Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Zero priming causes dropouts on real hardware | High | Med | Fractional priming (D1) gives a middle ground; select empirically in B1 |
| R2 | Real USB baseline is **worse** than 42.67 ms `snd-aloop`, widening the gap | Med-High | High | B0 first, before any tuning; if the target becomes unreachable, DoD-7 applies |
| R3 | Acoustic feedback howl during B5 | Med | Low | Low `output_gain`, physical mic separation, NLMS disabled |
| R4 | Core pinning degrades rather than improves | Med | Low | A/B gated; default off; discard on no win |
| R5 | numba `_resample` gain is unmeasurable | High | Low | Expected; delete-if-not-helpful is pre-agreed (D4) |
| R6 | Clock drift (Topology B) corrupts the B5 measurement | Med | Med | Calibrate immediately before; keep runs short; report drift if seen |
| R7 | 50 ms chunk still blocked on real hardware | Med | Med | Not load-bearing — priming alone can close most of the gap |
| R8 | Startup-grace window masks a real regression | Low | High | Hard 0.5 s cap; always printed and stored even when excluded |
| R9 | Optimising the estimate rather than the system | Med | **High** | DoD-3 requires a physical measurement; § 1.2 states the failure mode explicitly |

---

## 9. Backward compatibility and rollback

Every change is additive and default-off:

| Setting | Default | Effect at default |
|---|---|---|
| `priming_chunks` | `1.0` | Identical to current `int` 1 |
| `startup_grace_sec` | `0.5` | Only reclassifies underruns in the first 0.5 s |
| `cpu_affinity` | `null` | No pinning |
| `fast_resample` | `false` | Original `_resample` path |

**Rollback:** revert the config defaults; the new modules are inert. `git revert` of the Phase 2
commits leaves Phase 1 intact — no Phase 2 change modifies the dual-mic signal path.

---

## 10. Acceptance gate

**Gate A — dev machine**
- [ ] A0–A8 implemented; `architecture.md` updated **first** (Rule 7)
- [ ] Full self-test suite green, new tests registered, zero regressions
- [ ] A3 verified no-op on Windows
- [ ] A4 bit-equivalence proven
- [ ] Default-off regression check confirms today's behaviour preserved
- [ ] `progress.md` Track A entry with pasted output

**Gate B — Pi hardware**
- [ ] Phase 1 Track B complete first
- [ ] B0 re-baseline recorded on real dual-USB hardware
- [ ] B1 priming selected on evidence; 600 s PASS
- [ ] B2 sweep run, 50 ms re-tested on real hardware
- [ ] B3/B4 A/Bs run; keep-or-drop decisions logged
- [ ] B5 physical acoustic round-trip measured (≥20 reps)
- [ ] B6 lookahead measured empirically (Rule 30)
- [ ] B7 final 600 s dual-mic stress PASS
- [ ] B8 all claims reconciled to measured values with machines named

**Gate C — honesty**
- [ ] Every number traces to a pasted command
- [ ] Estimates labelled as estimates
- [ ] Target met → stated with evidence. Target missed → stated with the real number and reason (Rule 33)
- [ ] No superseded measurement deleted

---

## 11. Out of scope

ONNX/quantisation (blocked on Pi Python 3.13) · model fine-tuning · quality/PESQ changes ·
`RingBuffer` lock-free rewrite (its `Condition` is deliberate and previously validated) · real-time
kernel / `PREEMPT_RT` · Phase 3 quality work · pinning PortAudio's internal threads (not reachable
from Python).

---

## 12. Effort estimate

| Track | Work | Estimate |
|---|---|---|
| A | A0–A8, self-tests, docs | ~1 day |
| B | B0–B8, hardware runs | ~0.75 day (mostly 600 s stress runs) |
| — | Contingency (R2: worse USB baseline) | ~0.25 day |
| | **Total** | **~2 days** |

`prototype.md` estimates 1.5 days. That assumed no hardware dependency; § 1.1 shows Track B is
unavoidable, and B1/B7 alone are ~1 hour of wall-clock stress runs.

---

## 13. Open question for you

**Is the 150 ms target load-bearing for the submission, or is a well-evidenced honest number
acceptable?**

It changes how aggressively to push priming toward 0. If 150 ms must be met, D1 goes to `0.0` and
accepts dropout risk. If an honest number is acceptable, `0.5` is the safer selection and likely lands
around 120 ms once B0 re-baselines. My recommendation is the latter — a defensible measured number
beats a fragile one — but that is your call to make, not mine.
