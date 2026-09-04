# PS26052 — Phase 3 Implementation Plan
## Quality Validation: Activate What's Built

**Source plan:** `prototype.md` § "Phase 3 — Quality Validation: Activate What's Built"
**Target end-state:** `idea.md` § evaluation/compliance story
**Status:** DRAFT — awaiting sign-off. No code has been modified.
**Written against the repo after the Phase 2 Track A commit (branch `main`).**
**Governing rules:** `rules.md` — Rules 1–10, 19, 20, 22–28, 31 are load-bearing here.

---

## 0. How to read this document

Section 1 is **three corrections to `prototype.md`** that change what this phase can achieve — read it
first, because one of them makes `prototype.md`'s headline target arithmetically unreachable. Sections
2–3 define the objective and the code-verified ground truth. Section 4 lists **five decisions needing
your sign-off**. Section 5 is the work. Section 6 is the `progress.md` logging contract. Sections 7–13
are verification, risk, rollback, and the acceptance gate.

**Good news up front:** unlike Phases 1 and 2, this phase genuinely has **no hardware dependency**.
`prototype.md`'s "no hardware" label is correct here. Phase 3 is ~100 % dev-machine work and does not
add to the deferred Pi batch, apart from one optional live spot-check (§ 5.7).

---

## 1. Three corrections to `prototype.md` before we start

### 1.1 The "8 of 9 metric cells green" target is arithmetically unreachable by the means proposed

`prototype.md` § 3.4 sets: *"2 of 3 categories fully PASS, third category passes SI-SNR and STOI with
disclosed PESQ gap → 8/9 metric cells green vs. current 5/9."*

That requires the **non-stationary** category to pass SI-SNR and STOI. Using the committed per-subtype
numbers from `docs/non_stationary_root_cause.md` (helicopter n=60, crowd n=40), I reproduced the
committed category means exactly — confirming the subtype table is consistent with
`results/final/target_compliance.json`:

```
STOI   mean = (60×0.9108 + 40×0.7080)/100 = 0.8297   ← matches committed 0.8297
SI-SNR mean = (60×14.570 + 40×5.017)/100 = 10.7488   ← matches committed 10.75
```

Now solve for what would have to happen to pass:

| To pass | Crowd must reach | Crowd's realistic ceiling | Verdict |
|---|---|---|---|
| STOI ≥ 0.85 | **≥ 0.7588** | 0.7196 *(unprocessed noisy)* | **Impossible** — target is above the un-degraded input |
| SI-SNR ≥ 15 dB | **≥ 15.645 dB** | 3.986 dB *(unprocessed)* | **Impossible** — needs +10.6 dB on babble |

The alternative route — leave crowd alone and improve helicopter — is no better:

| To pass via helicopter | Helicopter must reach | Context | Verdict |
|---|---|---|---|
| STOI ≥ 0.85 | ≥ 0.9447 | best cell in the *entire* evaluation is 0.9319 | Implausible |
| SI-SNR ≥ 15 dB | ≥ 21.655 dB | currently 14.570 dB | Implausible |

**The decisive case:** even if we bypassed DFN3 entirely on crowd — doing zero damage, accepting the
raw noisy signal — the category STOI mean would be **0.8343, still below 0.85**.

**Why this is structural, not a tuning problem.** `docs/non_stationary_root_cause.md` § 4 already
established it: crowd babble is *other human speech*, so a single-channel enhancer has no cue to
separate target from interferer. It is the cocktail-party problem. `atten_lim_db` sweeps, spectral
tilt, and pre-emphasis are **spectral shaping** operations — none of them create the missing spatial
or speaker cue. They cannot move a 4.25 dB SI-SNR gap on babble.

**Consequence for this plan:** the realistic single-channel ceiling is **6 of 9** (the current 5 plus
stationary PESQ, which misses by only −0.018). This plan targets 6/9 honestly and states why 8/9 was
not attempted, rather than spending two days chasing it and reporting a miss. Per Rule 33, a target is
either met with evidence or disclosed as missed with the number and reason — and per Rule 1, we do not
write a target into a plan that the committed data already shows to be unreachable.

### 1.2 § 3.2's premise inverts the reason NLMS wins on crowd — a Rule 27 trap

`prototype.md` § 3.2: *"does DFN3 + reference-ALE beat DFN3-alone on crowd babble? **Expected yes based
on the offline NLMS numbers.**"*

The offline NLMS numbers do not support that inference. `docs/non_stationary_root_cause.md` § 5 states
exactly why NLMS wins on crowd:

> NLMS in this evaluation is reference-assisted — it has direct access to the true noise-only reference
> channel (traced via `noise_id`, per Rule 18) … an **oracle-like advantage**.

The offline reference is the **true pre-mix noise clip**: perfectly sample-aligned, noise-only, with
**zero speech leakage**. A real reference microphone has none of those three properties — it sees a
different acoustic path, it is misaligned (and drifting, per the Topology B constraint), and it
picks up the target speaker too.

Using the oracle result to predict live dual-mic performance is precisely the failure mode **Rule 27**
exists to prevent: a plausible-sounding narrative that does not match the actual architecture. It
would also produce a number real hardware can never reproduce — setting up a credibility failure at
demo time, not just a documentation error.

**Consequence:** § 5.4 evaluates a **realistically-degraded simulated reference** as the headline
figure, and reports the oracle number alongside it *explicitly labelled as an unreachable upper bound*.

### 1.3 A stale caveat now blocks nothing — and unlocks the analysis that was missing

`docs/non_stationary_root_cause.md` § 2 and § 7 both record that PESQ-WB could not be broken out by
subtype because *"the local `pesq` C-extension build is currently unavailable in this dev environment."*

**Verified today — that is no longer true.** Both metric libraries import and execute:

```
$ uv run --no-sync python -c "...compute_si_snr/compute_stoi/compute_pesq_wb on a synthetic signal..."
SI-SNR: 16.9764
STOI  : 0.0227
PESQ  : 1.0131
```

(The low STOI/PESQ values are expected — the probe used a pure tone, not speech. The point is that the
C extension **executes without raising**, which is what was previously impossible.)

This unblocks the **per-subtype PESQ breakdown** that § 7 listed as an open caveat, and it is a
prerequisite for tuning `atten_lim_db` against PESQ at all. Per Rule 27, the stale caveat gets
corrected in the source document rather than left standing.

---

## 2. Objective and Definition of Done

### 2.1 Objective

Convert already-written but unmeasured code (data augmentation, the reference-adaptive stage) into
**cited, reproducible quality results**, and extract the genuinely available PESQ headroom via
post-processing tuning — without overstating what single-channel enhancement can do on babble.

### 2.2 Definition of Done

| # | Condition | Verified by |
|---|---|---|
| DoD-1 | Augmented dataset generated, all 5 methods run, evaluated; robustness deltas quantified | `results/results_augmented.csv` + `docs/augmentation_robustness.md` |
| DoD-2 | Row-count integrity proven programmatically for **both** datasets (Rule 26) | Pasted count check; exclusions stated explicitly (Rule 24) |
| DoD-3 | `atten_lim_db` (and `--post-filter`) swept per category; optima selected on evidence | `results/atten_sweep.csv` + committed per-category config |
| DoD-4 | Spectral-tilt / pre-emphasis experiments run and **kept or dropped honestly** | `docs/postproc_experiments.md`, including negative results |
| DoD-5 | Reference-adaptive stage A/B'd offline with a **realistic** simulated reference; oracle reported separately as an upper bound | `results/results_dualmic_crowd.csv`, Rule 31 separate track |
| DoD-6 | Fresh compliance report regenerated with all improvements | `results/final/target_compliance.md` / `.json` |
| DoD-7 | Final cell count stated honestly, with the non-stationary gap explained by root cause, not hand-waved | `progress.md` + compliance report |
| DoD-8 | Stale PESQ-availability caveat corrected in `docs/non_stationary_root_cause.md` (Rule 27) | Diff + `progress.md` note |

### 2.3 Success criterion, stated honestly up front

**Target: 6 of 9 cells green** (up from 5), by closing stationary PESQ (−0.018 gap).

Anything beyond that is upside, not plan. Non-stationary is expected to remain 0/3 on the
single-channel track for the reasons proven in § 1.1, and that is reported as a **scoped, root-caused
limitation** — which `docs/non_stationary_root_cause.md` § 6 already argues is a *stronger* pitch
position than an unexplained weak cell.

### 2.4 Explicitly NOT the goal

- **Not** fine-tuning or retraining (out of scope by design — needs the Rust `libdfdata`/HDF5 pipeline).
- **Not** solving crowd babble. Proven structural in § 1.1.
- **Not** blending reference-assisted results into the single-channel compliance matrix (**Rule 31**).
- **Not** cherry-picking. Experiments that fail get logged as failures (`prototype.md` § 3.3 already
  commits to this: *"dropped honestly if not — no cherry-picking"*).

---

## 3. Ground truth — code-verified

| Fact | Anchor |
|---|---|
| `--augment-rir` and `--augment-clipping` flags exist as `prototype.md` assumes | `data/mix_dataset.py:300,302` |
| Augmentation primitives exist and self-test green | `data/augment.py` (`generate_synthetic_rir`, `apply_reverb`, `apply_clipping`) |
| Eval methods are a **hardcoded list** — new conditions require editing it | `eval/run_eval.py:15` `METHODS = [...]` |
| Method audio resolved as `results/baselines/{method}/{mix_file}` | `eval/run_eval.py` `resolve_method_audio_path` |
| `run_eval.py` accepts `--manifest`, `--results`, `--baselines-dir`, `--eval-raw`, `--limit` | `eval/run_eval.py:270-275` |
| Exclusions already collected with `mixture_id` + `method` + error (Rule 24 satisfied) | `eval/run_eval.py` `exclusions` list |
| ΔSI-SNR computed per-mixture via `noisy_si_snr_map` (Rule 25 satisfied) | `eval/run_eval.py` `noisy_si_snr_map` |
| PESQ resamples 48 k→16 k **in memory only**; disk untouched (Rule 23 satisfied) | `eval/metrics.py` `compute_pesq_wb` docstring |
| STOI accepts 48 kHz directly, resamples internally to 10 kHz | `eval/metrics.py` `compute_stoi` docstring |
| `run_inference.py` exposes `--atten-lim` — no code change needed to sweep | `models/deepfilternet/run_inference.py:168` |
| **`--post-filter` also exists and has never been swept** | `models/deepfilternet/run_inference.py:169` |
| Manifest is 300 rows; 300 × 5 methods = 1,500 eval pairs | `data/manifest.csv` (301 lines incl. header) |
| Manifest carries `category`, `subtype`, `snr_db`, `clean_ref_path`, `noise_id` | `data/manifest.csv` header |
| `pesq` + `pystoi` both import **and execute** on this dev machine | Verified § 1.3 |
| Offline NLMS reference is the oracle pre-mix clip (Rule 18) | `baselines/nlms/nlms.py` `process_batch` |

### 3.1 Two code changes that are unavoidable

**(a) `METHODS` is hardcoded.** Adding a tuned DFN3 variant or a dual-mic condition means editing
`eval/run_eval.py:15` and adding the corresponding output directory. Not a refactor — but it must be
done deliberately, and the tuned variant needs its **own** directory (e.g.
`results/baselines/deepfilternet_tuned/`) so the untuned baseline stays intact for comparison and is
never silently overwritten.

**(b) There is no per-category attenuation mechanism.** `--atten-lim` is a single global value.
Producing per-category outputs requires either three separate runs filtered by category, or a small
driver script that reads the manifest and dispatches per row. The latter is cleaner and is what § 5.3
specifies.

---

## 4. Decisions requiring sign-off

### D1 — Target 6/9 honestly, rather than pursuing 8/9 *(recommended)*

Per § 1.1, 8/9 is unreachable by post-processing. **Recommendation:** plan for 6/9, state the
non-stationary limitation as root-caused and scoped, and present it using the framing
`docs/non_stationary_root_cause.md` § 6 already recommends — *"suppresses every sourced defence noise
type at 0.83–0.92 STOI; the one gap is background human speech, a known limitation of single-channel
enhancement."*

That is a defensible engineering position. "8/9" reached by loosening a threshold or averaging across
categories would not be — and the compliance report already carries an explicit warning against
cross-category averaging for exactly this reason.

### D2 — Sweep on a stratified subset, confirm on the full set *(recommended)*

A naive sweep of 8 attenuation values × 300 files = 2,400 DFN3 inferences, before the eval cost.

**Recommendation:** two-stage. Stage 1 sweeps on a **stratified subset** (20 mixtures per category = 60
files, covering all 5 SNR levels) to locate each category's optimum. Stage 2 runs **only the chosen
per-category values** across the full 300 and regenerates compliance. Cuts compute ~5× while keeping
the final number a full-dataset result.

Rule 19 applies regardless: pilot-time on 5–10 files and extrapolate **before** launching either stage.

### D3 — Simulated realistic reference for the offline dual-mic A/B *(recommended)*

Per § 1.2, the oracle reference cannot predict live dual-mic behaviour. **Recommendation:** synthesise
a reference channel that degrades the oracle in the three ways real hardware does:

| Degradation | Models | Implementation |
|---|---|---|
| Different acoustic path | Reference mic is elsewhere in the room | Second synthetic RIR via `generate_synthetic_rir` (different seed) |
| Time misalignment | Two USB clocks, mic spacing | Fixed sample offset + optional slow drift |
| Speech leakage | Reference mic also hears the talker | Mix in the clean signal at a low, stated ratio (e.g. −15 dB) |

Report **three** conditions: DFN3-alone · DFN3 + NLMS(oracle) *labelled upper bound* · DFN3 +
NLMS(realistic). The spread between the last two is the honest estimate of what the live system loses
versus the offline baseline — genuinely useful information the project does not currently have.

All of it on a **separate reference-assisted track** per Rule 31.

### D4 — Sweep `--post-filter` alongside `--atten-lim` *(recommended)*

`prototype.md` doesn't mention it, but `run_inference.py:169` exposes DeepFilterNet's own post-filter,
and it has never been evaluated. It is a single boolean, costs one extra sweep arm, and is a more
principled lever than the hand-rolled spectral tilt in `prototype.md` § 3.3 because it ships with the
model. **Recommendation:** include it in the Stage-1 sweep grid.

### D5 — Pre-emphasis/de-emphasis: implement, measure, expect to drop *(recommended)*

`prototype.md` § 3.3 claims pre-emphasis *"often lifts PESQ 0.05–0.15."* That heuristic comes from
codec and ASR front-end practice; DFN3 already operates on an ERB-scale representation with its own
learned spectral weighting, so an external tilt may fight the model rather than complement it.

**Recommendation:** implement it (it is genuinely ~3 lines), measure it, and **expect a null or
negative result**. Budget it as a 2-hour experiment, not a planned win. If it does not help, it gets
logged as a negative result and deleted — per DoD-4 and `prototype.md`'s own no-cherry-picking clause.

---

## 5. Work breakdown

> **All of § 5.1–5.6 is dev-machine work.** Only § 5.7 touches hardware, and it is optional and
> appended to the existing deferred Pi batch.

---

**T0 — Pilot timing gate** *(Rule 19 — blocking; do this before any batch run)*

Time 5–10 files through each stage (mixture generation, each baseline, DFN3, eval) and extrapolate
total runtime for: the augmented set (300 × 5), the Stage-1 sweep, and the Stage-2 confirmation.
Log the pilot timing and the decision it drove (run directly vs. background vs. checkpoint) in
`progress.md`. If any stage extrapolates beyond ~2 h, run it backgrounded with resumable checkpoints.

**T1 — Augmented dataset generation** *(`prototype.md` § 3.1)*

```bash
python data/mix_dataset.py --output-dir data/mixtures_augmented \
    --manifest data/manifest_augmented.csv --augment-rir --augment-clipping
```

- Verify achieved-vs-requested SNR deviation is logged (Rule 13 discipline carries over — augmentation
  changes signal levels, so this is not a formality).
- Verify all output is 48 kHz (Rule 14).
- Verify `manifest_augmented.csv` row count equals files on disk **programmatically** (Rule 16/26).

**T2 — Run all methods over the augmented set**

All four baselines + DFN3 → `results/baselines_augmented/{method}/`. Reuse the existing resumable /
idempotent batch behaviour (Rule 20) — `baselines/nlms/nlms.py` already skips existing outputs; verify
the same holds for the others before relying on it.

```bash
python eval/run_eval.py --manifest data/manifest_augmented.csv \
    --baselines-dir results/baselines_augmented \
    --eval-raw results/eval_raw_augmented.csv \
    --results results/results_augmented.csv
```

**T3 — `docs/augmentation_robustness.md`**

Per-category, per-method deltas: clean condition vs augmented. The interesting question is not "did
scores drop" (they will) but **which methods degrade most gracefully** — that is the robustness story.
Report exclusions explicitly (Rule 24) and confirm row counts (Rule 26).

**T4 — Attenuation + post-filter sweep** *(§ 3.3, per D2 and D4)*

- New driver `scripts/sweep_atten_lim.py` — reads the manifest, dispatches per-category runs at each
  grid point, writes `results/atten_sweep.csv` (columns: category, atten_lim_db, post_filter, PESQ,
  STOI, SI-SNR).
- Grid: `atten_lim_db ∈ {30, 50, 70, 85, 100}` × `post_filter ∈ {off, on}`, Stage-1 stratified subset.
- Must be resumable (Rule 20) and must **not** overwrite `results/baselines/deepfilternet/`.
- Select per-category optima → `model.atten_lim_db_by_category` in config.
- **Selection rule stated in advance** (so it cannot be retrofitted to whatever looks best): maximise
  PESQ subject to STOI and SI-SNR not regressing more than 0.005 / 0.1 dB against the current
  committed values.

**T5 — Spectral tilt / pre-emphasis experiments** *(§ 3.3, per D5)*

Implement as post-DFN numpy ops behind flags; measure on the stratified subset; keep only on a
demonstrated win under the T4 selection rule. Log outcomes — **including negatives** — in
`docs/postproc_experiments.md`.

**T6 — Offline reference-adaptive A/B** *(§ 3.2, per D3 — Rule 31 separate track)*

- `scripts/simulate_reference_channel.py` (new): produces a realistic reference per mixture (second
  RIR + offset + stated speech leakage). Self-test: assert the simulated reference correlates with the
  true noise but is *not* identical, and that leakage is at the configured ratio.
- Score three conditions on the **crowd subset first** (where the effect should be largest), then the
  full non-stationary category.
- Output `results/results_dualmic_crowd.csv`.
- **Reported on a separate reference-assisted track. Never merged into the 9-cell matrix** (Rule 31).
- Oracle condition carried through explicitly labelled `nlms_oracle_upper_bound`.

**T7 — Consolidated compliance rerun** *(§ 3.4)*

Regenerate `results/final/target_compliance.md` / `.json` with T4/T5 winners applied. Preserve the
existing structural warnings (no cross-category averaging; NLMS separate-track note; ANC terminology
note per Rule 32). Add the § 1.1 arithmetic as a short subsection so the non-stationary verdict is
shown to be structural rather than asserted.

**T8 — Correct the stale PESQ caveat** *(DoD-8, Rule 27)*

Update `docs/non_stationary_root_cause.md` § 2 and § 7 to record that PESQ is now available, and add
the per-subtype PESQ breakdown that was previously impossible. Mark the old caveat superseded rather
than deleting it — matching established project practice.

**T9 — Optional live spot-check** *(Track B — joins the deferred Pi batch, does not block Phase 3)*

Once the Pi batch runs, spot-check whether live dual-mic behaviour on crowd babble falls between the
simulated and oracle predictions from T6. This is the validation that closes the § 1.2 loop — but it
is **not** a Phase 3 gate.

---

## 6. Logging contract — `progress.md`

> Rule 3: nothing is "done" until its evidence is pasted. Rule 10: log per increment, not in one batch.

### 6.1 Entry skeleton

```markdown
## <YYYY-MM-DD> — Phase 3: <task ID> <short title>

**Machine:** devmachine (Windows 11, x86_64, uv venv)   [Phase 3 is dev-only]
**Dataset:** <clean 300 | augmented 300>

### What changed
<files touched, one line each, with the reason>

### Evidence
<exact command>
<verbatim pasted output>

### Row-count / exclusion integrity   [required for any eval run — Rules 24/26]
Expected rows: <n>   Actual: <n>   Exclusions: <n> (<reason breakdown>)

### Result
<PASS / FAIL / PARTIAL — for FAIL, the real error text per Rule 4>
```

### 6.2 Mandatory rules for every Phase 3 entry

1. **State expected vs actual row counts on every eval run** (Rule 26). No silent gaps.
2. **Report exclusions with `mixture_id`, method, and the real error** (Rule 24). Never backfill a
   placeholder or estimated value.
3. **Keep reference-assisted results on their own track** (Rule 31). No table may rank NLMS or dual-mic
   conditions alongside single-channel methods as if the input assumptions matched.
4. **Log negative results** (DoD-4). An experiment that did not help is a finding, not a non-event.
   Deleting it and keeping only winners is cherry-picking.
5. **Root-cause anomalies against the code before narrating them** (Rule 27). If a number moves
   unexpectedly, verify against the implementation before writing an explanation.
6. **Never delete a superseded measurement** — mark it superseded, matching existing project practice.
7. **State the final cell count honestly** (Rule 33). If it is 6/9, write 6/9.

### 6.3 Required evidence per task

| Task | Command to paste | Must show |
|---|---|---|
| T0 | pilot timing runs | Per-stage timing + extrapolation + the decision it drove |
| T1 | `mix_dataset.py ...` | SNR deviation stats, 48 kHz confirmation, row-count check |
| T2 | `run_eval.py ...` | Completion + exclusion count |
| T3 | — | Delta table clean vs augmented, per method/category |
| T4 | `sweep_atten_lim.py` | Full grid; selected optima; selection rule applied |
| T5 | experiment runs | Both arms; explicit keep/drop with numbers |
| T6 | dual-mic A/B | All three conditions, oracle clearly labelled upper bound |
| T7 | compliance regen | Final matrix + cell count |
| T8 | diff | Corrected caveat + new per-subtype PESQ table |

### 6.4 Closing entry

A summary table: each of the 9 cells, before → after, with the delta and what caused it; the final
cell count; and an explicit statement of which cells remain failing and why (citing § 1.1 for
non-stationary). Plus the reference-assisted track reported separately.

---

## 7. Test plan

**Mode A only** — Phase 3 adds no hardware tests.

- New scripts (`sweep_atten_lim.py`, `simulate_reference_channel.py`) each carry a self-test (Rule 8)
  and are registered in `scripts/run_all_selftests.py`.
- Full suite must stay green with zero regressions — currently 14 PASS + 2 SKIP after Phase 2.
- **Integrity checks are part of the test plan, not an afterthought:** row counts (Rule 26), exclusion
  accounting (Rule 24), and 48 kHz verification (Rule 14) are asserted programmatically, not eyeballed.

---

## 8. Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Sweep compute exceeds budget | Med | Med | D2 two-stage design; T0 pilot gate (Rule 19); resumable (Rule 20) |
| R2 | Stationary PESQ gap doesn't close even at optimum | Med | High | It's only −0.018, but if it holds, report 5/9 honestly (Rule 33) |
| R3 | Tuning improves PESQ while regressing STOI/SI-SNR | **High** | Med | Pre-committed selection rule in T4 forbids trading them away |
| R4 | Augmented run overwrites clean-condition results | Low | **High** | Separate `--baselines-dir` / manifest / results paths throughout |
| R5 | Simulated reference is unrealistic in an unfalsifiable way | Med | Med | Report oracle *and* simulated; T9 live spot-check closes the loop |
| R6 | Dual-mic gains leak into the single-channel headline | Med | **High** | Rule 31 enforced structurally — separate file, separate table |
| R7 | Pre-emphasis fights DFN3's learned weighting | High | Low | Expected (D5); budgeted as a short experiment, dropped on null |
| R8 | PESQ C-extension breaks again mid-phase | Low | High | T0 verifies it before batch launch; treat as a hard gate |

---

## 9. Backward compatibility and rollback

Every artifact is written to a **new path**; nothing existing is mutated:

| Existing (untouched) | New |
|---|---|
| `data/manifest.csv`, `data/mixtures/` | `data/manifest_augmented.csv`, `data/mixtures_augmented/` |
| `results/baselines/` | `results/baselines_augmented/`, `results/baselines/deepfilternet_tuned/` |
| `results/results.csv`, `eval_raw.csv` | `results/results_augmented.csv`, `eval_raw_augmented.csv` |

`results/final/target_compliance.*` is the one file regenerated in place — the previous version is
preserved in git history and the superseding note kept in-document, matching how the 2026-08-24
dataset-correction supersede was handled.

**Rollback:** revert the compliance file and the `METHODS` edit; every other Phase 3 artifact is
additive and inert.

---

## 10. Acceptance gate

**Gate A — integrity** *(nothing else counts until these pass)*
- [ ] T0 pilot timing logged with the decision it drove (Rule 19)
- [ ] PESQ/STOI verified executable before batch launch
- [ ] Row counts verified programmatically, both datasets (Rule 26)
- [ ] Exclusions reported with IDs and real errors (Rule 24)
- [ ] All audio confirmed 48 kHz (Rule 14)

**Gate B — results**
- [ ] `results/results_augmented.csv` complete; robustness deltas documented
- [ ] Sweep run; per-category optima selected under the pre-committed rule
- [ ] Post-processing experiments logged, **including negatives**
- [ ] Dual-mic A/B on a separate reference-assisted track (Rule 31), oracle labelled as upper bound
- [ ] Compliance report regenerated

**Gate C — honesty**
- [ ] Final cell count stated as measured (Rule 33)
- [ ] Non-stationary verdict explained via § 1.1 arithmetic + root cause, not hand-waved
- [ ] No cross-category averaging introduced
- [ ] Reference-assisted results never blended into single-channel rankings
- [ ] Stale PESQ caveat corrected (Rule 27); superseded content marked, not deleted

---

## 11. Out of scope

Fine-tuning / retraining · solving crowd babble · beamforming or speaker enrollment · new noise corpora
(Rule 15: keep dataset size proportionate) · live hardware validation beyond the optional T9 spot-check
· ONNX/quantisation (still blocked on Pi Python 3.13).

---

## 12. Effort estimate

| Task | Estimate |
|---|---|
| T0 pilot gate | 1 h |
| T1–T3 augmented eval + robustness doc | ~0.75 day |
| T4 sweep (two-stage) | ~0.5 day (mostly unattended compute) |
| T5 post-processing experiments | ~2 h |
| T6 dual-mic simulation + A/B | ~0.5 day |
| T7–T8 compliance + doc corrections | ~0.25 day |
| **Total** | **~2 to 2.5 days** |

Matches `prototype.md`'s 2-day estimate, plus contingency for the two-stage sweep. No hardware wait
states — this phase can run start to finish on the dev machine.

---

## 13. Open question for you

**How should the non-stationary category be presented in the final pitch?**

§ 1.1 proves it cannot pass on the single-channel track. Two framings:

1. **Scoped-limitation framing** *(recommended, and what `non_stationary_root_cause.md` § 6 already
   argues for)* — "every *sourced defence* noise type passes; the one gap is background human speech,
   a structural single-channel limitation with a named cause and a known fix." Turns a red cell into
   evidence of engineering maturity.
2. **Dual-mic-as-the-answer framing** — present the reference-assisted track as the mitigation. Honest
   **only** if T6's realistic-reference number supports it, and it must stay on its own track (Rule 31).

I recommend leading with (1) and using (2) as supporting evidence **if and only if** T6's realistic
condition shows a genuine gain. Which one you want changes how much weight T6 carries — it is worth
deciding before the work starts rather than after the numbers land.
