# Corpus Redefinition v2 — `non_stationary` Category

**Status:** PRE-REGISTERED 2026-09-04, before any metric was computed on the new corpus.
**Author:** Phase 4.5 (between Phase 4 Track A close and Phase 5).

> **Read this first.** This document changes the *evaluation*, not the *system*. Any number
> that moves as a result of this change moves because the benchmark was redefined, not
> because the enhancement pipeline improved. Section 6 states exactly how the before/after
> comparison may and may not be described. The v1 (crowd) results are preserved, not deleted.

---

## 1. Summary of the change

| | v1 (before) | v2 (after) |
|---|---|---|
| `non_stationary` subtypes | `helicopter`, `crowd` | `helicopter`, `wind`, `aircraft` |
| `crowd` source | Synthetic LibriSpeech babble | **Removed** |
| `stationary` subtypes | `engine`, `vehicle` | *unchanged* |
| `impulsive` subtypes | `gunshot`, `explosion`, `artillery` | *unchanged* |
| Clean speech pool | 150 files / 2 speakers | *unchanged* (see §7 — separate open defect) |
| SNR grid, seeds, mixture count | -5…+15 dB, seed 42, 300 | *unchanged* |

Exactly one thing changed: **the `crowd` subtype was removed from `non_stationary` and
replaced with two non-speech battlefield noise subtypes.** Everything else is held constant
so the before/after comparison stays interpretable.

---

## 2. Why `crowd` was removed — two independent reasons

### 2.1 Reason A: it is the wrong problem class for the stated threat model

PS26052 targets a **battlefield / defence communication** device. "Non-stationary noise" in
that operational context means noise whose spectral and temporal statistics vary because of
*physical events in the environment*: wind gusts, aircraft flyover, vehicle manoeuvres,
machinery throttle changes.

Multi-talker crowd babble is a **different problem class**. Separating a target talker from
competing talkers is *speaker separation* (the cocktail-party problem), which requires
speaker identity cues, spatial cues, or a per-speaker enrolment — none of which a
single-channel speech *enhancement* model is designed to provide. Benchmarking a speech
enhancer on a speaker-separation task measures the wrong capability.

### 2.2 Reason B: as constructed here, the `crowd` task is mathematically ill-posed

This is the stronger reason, and it is a defect in the v1 dataset construction, not a
judgement call.

`scripts/generate_babble_noise.py` builds each babble clip by sampling 6 utterances from
`data/clean` — **the same pool the target speech is drawn from** — with no speaker or
utterance exclusion (`generate_babble_noise.py:67,76` vs `data/mix_dataset.py:143,197`).
The clean pool contains only **2 unique LibriSpeech speakers** (2035, 2277) across 150 files.

Measured consequence, computed by reproducing the generator's seeded sampling and
cross-referencing `data/manifest.csv`:

```
clean pool: 150 files, 2 unique LibriSpeech speakers
crowd mixtures in manifest: 40
  target utterance literally inside its own babble interferer: 4/40
  target SPEAKER present inside its own babble interferer:     39/40
```

In 39 of 40 crowd mixtures the interferer contains the target speaker's own voice. In 4 it
contains the target's own utterance. For those mixtures the separation task has no defined
correct answer: no spectral, temporal, or spatial cue distinguishes a speaker from
themselves. This is not a hard benchmark — it is an unsatisfiable one.

**This independently explains the anomalous Phase 3 T6 result** (`results/results_dualmic_nonstationary_full.csv`):
a dual-mic NLMS given an *oracle* reference scored PESQ 1.399, **worse** than DeepFilterNet3
alone at 2.13. That inversion was previously attributed to reference-channel contamination.
The root cause is now identified as the target speaker being present in the interferer
itself, so the "oracle" reference was partly the target signal, and subtracting it removed
target speech. Per Rule 27, this supersedes the earlier explanation.

---

## 3. Replacement subtypes — selection rationale (PRE-REGISTERED)

The replacement classes were chosen on **threat-model relevance alone**, committed to in
this document **before any PESQ/STOI/SI-SNR number was computed on the new corpus**. No
candidate screening by score was performed. Whatever the new numbers are, they stand.

Source: ESC-50 (`data/downloads/esc50-master.zip`, already on disk — no new download,
Rule 15). Same corpus, same licence (CC BY-NC 3.0), same 40-clips-per-class structure as
the existing `helicopter`, `engine`, and `fireworks` subtypes, so provenance and licensing
are unchanged.

| New subtype | ESC-50 class | Threat-model justification |
|---|---|---|
| `wind` | 16 (`wind`) | Wind gusts are the canonical outdoor military communication noise: a soldier-worn or vehicle-mounted mic outdoors is wind-exposed by default. Strongly non-stationary amplitude envelope (gust/lull structure). |
| `aircraft` | 47 (`airplane`) | Fixed-wing flyover. Non-stationary by construction — approach/overhead/recede produces a sweeping amplitude and Doppler-shifted spectral envelope. Complements the existing rotary-wing `helicopter` subtype. |

`helicopter` (ESC-50 class 40) is **retained unchanged**. It was never part of the defect;
`target_compliance.json` already records it performing on par with the strongest categories
(STOI 0.91, ΔSI-SNR +8.9 dB), which is itself evidence that the category's v1 failure was
localised to `crowd`.

### Why two replacements rather than one

Splitting `crowd`'s 40 mixtures across two new subtypes avoids resting the entire category
verdict on a single 40-clip ESC-50 class, and brings `non_stationary` to 3 subtypes,
matching `impulsive`'s existing structure. The change is still a single conceptual
edit — "the babble subtype is replaced by non-speech battlefield noise."

---

## 4. What was NOT changed, and why that matters

Deliberately held constant so that any metric movement is attributable to the subtype swap
alone:

- Clean speech pool (same 150 files, same 2 speakers) — see §7
- SNR grid (-5, 0, +5, +10, +15 dB) and per-mixture seeding (seed 42)
- Total mixture count (300) and per-category count (100 each)
- `stationary` and `impulsive` categories — **byte-for-byte identical inputs**, so their
  numbers act as a control. If they move, something unintended broke and the run is invalid.
- Model, weights, and `atten_lim_db=30` (the Phase 3 T4 committed optimum)
- All evaluation code, metric implementations, and reference-signal handling (Rules 22–26)

---

## 5. Preservation of v1 results (nothing is deleted)

| v1 artefact | Archived to |
|---|---|
| `data/manifest.csv` | `data/manifest_v1_crowd.csv` |
| `results/eval_raw.csv` | `results/v1_crowd/eval_raw.csv` |
| `results/results.csv` | `results/v1_crowd/results.csv` |
| `results/final/target_compliance.{json,md}` | `results/v1_crowd/target_compliance.{json,md}` |

The v1 crowd numbers remain quotable and remain in git history. The 6/9 v1 verdict is not
retracted — it was a correct measurement of a benchmark that has since been shown to contain
an ill-posed subtype.

---

## 6. How this change may and may not be described (binding)

**Permitted:**
- "The `non_stationary` evaluation corpus was redefined to match the operational threat
  model; the previous `crowd` subtype was found to be ill-posed (target speaker present in
  its own interferer in 39/40 mixtures) and was replaced with non-speech battlefield noise."
- Reporting v1 and v2 numbers side by side, each labelled with its corpus version.

**Forbidden:**
- Describing any v1→v2 metric change as a system, model, or algorithm improvement. The
  pipeline is bit-identical across this change.
- Reporting a v2 number against the v1 corpus label, or vice versa.
- Quoting a v2 `non_stationary` figure without stating that the corpus definition changed.
- Any claim that the cocktail-party limitation was "solved." It was **removed from scope**,
  not solved. A crowd-babble scenario would still fail, and that remains a genuine and
  disclosed limitation of single-channel enhancement.

---

## 7. Open defect NOT addressed by this change

**The clean speech pool uses 2 of the 40 speakers available in LibriSpeech `dev-clean`**
(2035, 2277; verified against `data/downloads/dev-clean.tar.gz`, which contains 40). Every
category in the benchmark is therefore evaluated on 2 talkers, which materially limits any
speaker-generalisation claim.

This is left unfixed **in this change** on purpose: expanding the speaker pool would move
every category's numbers simultaneously, including `stationary` (+0.0385 PESQ headroom) and
`impulsive` (+0.0428 PESQ headroom), whose current PASS margins are thin enough that they
could flip. Mixing it with the subtype swap would make neither change interpretable.

Recommended as the next separate, single-variable change. Tracked in `progress.md`.

---

## 8. Reproduction

```bash
python scripts/extract_esc50_subtype.py --self-test
python scripts/extract_esc50_subtype.py --class-name wind     --dest data/noise/non_stationary/wind
python scripts/extract_esc50_subtype.py --class-name airplane --dest data/noise/non_stationary/aircraft
python data/mix_dataset.py
python scripts/run_all_baselines.py
python models/deepfilternet/run_inference.py
python eval/run_eval.py
python eval/make_compliance_report.py
```
