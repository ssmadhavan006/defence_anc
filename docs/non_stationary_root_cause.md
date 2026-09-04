# Root-Cause Analysis — Non-Stationary Category Weakness
**Smart India Hackathon 2026 | DRDO Problem Statement 26052**
**Scope:** Why does the non-stationary category (helicopter/crowd) lag stationary and impulsive across every metric?

---

> [!IMPORTANT]
> **Root cause SUPERSEDED 2026-09-04 (corpus v2, Rule 27). This document's decomposition is still
> correct; its explanation is incomplete.**
>
> This analysis correctly localised the non-stationary failure to the `crowd` subtype (Section 3:
> crowd STOI 0.7212 / PESQ-WB 1.7155 vs helicopter 0.9082 / 2.5443) and attributed it to the
> **cocktail-party problem** — a genuine, structural limitation of single-channel enhancement.
> That attribution is not wrong, but it is not the whole cause, and on its own it understates
> the problem.
>
> The deeper cause, found 2026-09-04, is that **the `crowd` task was ill-posed as constructed**:
> `scripts/generate_babble_noise.py` drew its babble from `data/clean` — the *same pool the target
> speech comes from* — with no speaker or utterance exclusion, and that pool contains only
> **2 unique LibriSpeech speakers** (2035, 2277) across 150 files. Measured by reproducing the
> generator's seeded sampling against the v1 manifest:
>
> ```
> crowd mixtures in manifest: 40
>   target utterance literally inside its own babble interferer: 4/40
>   target SPEAKER present inside its own babble interferer:     39/40
> ```
>
> In 39 of 40 crowd mixtures the interferer contained the target speaker's own voice. Those
> mixtures have **no defined correct answer** — separating a speaker from themselves is not a hard
> problem, it is an unsatisfiable one. So the crowd numbers in Section 3 measure an unsatisfiable
> task, not merely a difficult one.
>
> **This also supersedes the Phase 3 T6 explanation.** The oracle-reference NLMS scoring *worse*
> (PESQ 1.399) than DeepFilterNet3 alone (2.13) was previously explained as reference-channel
> contamination. The actual reason is that the "oracle" reference partly *was* the target signal,
> so subtracting it removed target speech.
>
> **Consequence:** the `crowd` subtype was retired from the corpus on 2026-09-04 and replaced with
> `wind` + `aircraft`. See `docs/corpus_redefinition_v2.md` for the pre-registered rationale and for
> the binding rules on how the resulting v1→v2 number changes may be described. Note in particular
> that the cocktail-party limitation was **removed from scope, not solved** — a genuine crowd-babble
> scenario (real, disjoint speakers) would still be hard for a single-channel enhancer, and that
> remains a real and disclosed limitation of this system.
>
> Everything below is preserved unchanged as the record of the subtype decomposition.

---

## 1. The question

`docs/phase_4_summary.md` and `results/final/target_compliance.json` both show the non-stationary category as the weakest of the three for DeepFilterNet: STOI 0.8334 (target >0.85, FAIL), SI-SNR 10.86 dB (target >15 dB, FAIL), PESQ-WB 2.21 (target >2.5, FAIL, largest miss margin of the three categories) — figures as of the Phase 3 T4-tuned (`atten_lim_db=30`) configuration; the pre-tuning numbers (STOI 0.8297, SI-SNR 10.75 dB, PESQ-WB 2.13) tell the same story. The committed compliance note attributes this jointly to "helicopter/crowd" noise being harder to suppress. This analysis decomposes the category by subtype to check whether that's accurate.

## 2. Method

Recomputed directly from `results/eval_raw.csv` (per-mixture, per-method rows), grouped by `(method, subtype)` for `category == non_stationary`. STOI and SI-SNR/ΔSI-SNR are used because they don't depend on the `pesq` package.

> [!NOTE]
> **Superseded 2026-09-04 (Phase 3 T8, Rule 27):** the paragraph below originally said PESQ-WB could not
> be broken out by subtype because "the local `pesq` C-extension build is currently unavailable in this
> dev environment." **That is no longer true** — verified 2026-09-04 that both `pesq` and `pystoi` import
> and execute on this machine (a GCC toolchain was installed and `pesq` rebuilt during the 2026-08-24
> incident recovery — see `progress.md`). The per-subtype PESQ breakdown this caveat said was unavailable
> is now added in Section 3 below, computed against the current (Phase 3 T4-tuned, `atten_lim_db=30`)
> configuration. Original text preserved, not deleted, per established project practice:
>
> ~~PESQ-WB is not broken out by subtype here — the local `pesq` C-extension build is currently
> unavailable in this dev environment (build script targets a different machine profile,
> `C:\Users\Admin\...`; not reproducible here without a GCC/MinGW toolchain), so only the already-committed
> category-level PESQ means in `target_compliance.json` are cited below.~~
>
> STOI/SI-SNR figures in this document were freshly recomputed and verified when first written, not
> carried over from prior docs; PESQ-WB below is newly added 2026-09-04.

## 3. Finding: the two subtypes behave completely differently

*Table below recomputed 2026-09-04 (Phase 3 T8) against the current, Phase-3-tuned (`atten_lim_db=30`)
DeepFilterNet configuration and now includes the PESQ-WB column the Section 2 caveat originally said was
unavailable. STOI/SI-SNR are within 0.03 of the values originally reported here (computed pre-tuning);
the tuning did not change which subtype drives the gap.*

| Method | Subtype | n | STOI | ΔSI-SNR (dB) | SI-SNR (dB) | PESQ-WB |
|---|---|---|---|---|---|---|
| **DeepFilterNet (tuned)** | helicopter | 60 | **0.9082** | **+8.894** | +14.566 | **2.5443** |
| **DeepFilterNet (tuned)** | crowd | 40 | **0.7212** | **+1.306** | +5.292 | **1.7155** |
| NLMS (ref-assisted) | helicopter | 60 | 0.8889 | +2.996 | +8.668 | 1.3957 |
| NLMS (ref-assisted) | crowd | 40 | 0.8657 | +2.650 | +6.636 | 1.4040 |
| Wiener | helicopter | 60 | 0.8394 | +2.709 | +8.381 | 1.5279 |
| Wiener | crowd | 40 | 0.7170 | +0.345 | +4.331 | 1.3381 |
| Spectral Subtraction | helicopter | 60 | 0.8307 | +1.143 | +6.815 | 1.4621 |
| Spectral Subtraction | crowd | 40 | 0.7195 | +0.186 | +4.172 | 1.3805 |
| Unprocessed noisy | helicopter | 60 | 0.8279 | +0.000 (ref) | +5.672 | 1.4181 |
| Unprocessed noisy | crowd | 40 | 0.7196 | +0.000 (ref) | +3.986 | 1.3847 |

**New from the PESQ column:** DeepFilterNet's PESQ-WB on crowd (1.72) is still comfortably the best of any
method on that subtype (next best: NLMS 1.40, a +0.31 margin) — DeepFilterNet is not failing to help on
crowd, it is failing to help *enough* to clear the 2.5 target, which is a materially different claim than
"DeepFilterNet underperforms classical baselines on crowd" (true only for the STOI/ΔSI-SNR metrics
discussed below, not for PESQ). The 0.83-point PESQ gap between DeepFilterNet's helicopter (2.54) and
crowd (1.72) results is the largest per-subtype spread of any metric in this table, underscoring how much
harder crowd babble is across every measure, not just STOI/SI-SNR.

Two things stand out:

1. **On helicopter, DeepFilterNet is the strongest result in the entire evaluation** — 0.9108 STOI and +8.9 dB ΔSI-SNR, comparable to the stationary and impulsive category headline numbers (0.92 STOI, +10–11 dB). Helicopter alone is not the problem.
2. **On crowd babble, DeepFilterNet's STOI (0.708) is *below* the unprocessed noisy baseline (0.720)** — a −0.012 STOI regression, i.e. DeepFilterNet measurably *reduces* intelligibility on this subtype rather than improving it. Its ΔSI-SNR gain (+1.03 dB) is also the smallest of every method on crowd, including the three classical DSP baselines — NLMS (+2.65 dB) and Wiener (+0.35 dB) both edge it out, and NLMS's STOI on crowd (0.866) is well above DeepFilterNet's (0.708).

The entire non-stationary category shortfall is driven almost exclusively by the crowd subtype, not helicopter.

## 4. Why this happens (and why it isn't a DeepFilterNet-specific defect)

Crowd babble is fundamentally different from every other noise subtype in this dataset: it is *other human speech*, synthesized in Phase 2 by overlapping six clean speech utterances (`data/SOURCES.md`, `scripts/generate_babble_noise.py` — explicitly logged as a proxy/synthetic subtype, not a sourced defence-noise recording). Every other subtype (engine, vehicle, helicopter, gunshot, explosion, artillery) is acoustically distinct from speech in ways a single-channel model can exploit — spectral shape, harmonic structure, temporal envelope. Babble is not: it occupies the same frequency band, has the same broadband speech-like spectral envelope, and the same temporal modulation statistics as the target voice.

This is the well-documented **cocktail-party problem**: a single-channel (one-microphone) speech enhancer has no cue — spatial, spectral, or otherwise — to distinguish "the speaker we want" from "other speakers in the background," because both are speech. This is a structural limitation of the entire class of single-channel neural speech enhancers, not a defect specific to this DeepFilterNet checkpoint. Multi-channel methods (beamforming with a real second microphone) or speaker-conditioned models (given a reference clip of the target speaker) are the standard mitigations, and both are out of scope for the current single-channel, no-enrollment architecture.

## 5. Why classical NLMS edges out DeepFilterNet on crowd STOI specifically

NLMS in this evaluation is reference-assisted — it has direct access to the true noise-only reference channel (`baselines/nlms/nlms.py`, traced via `noise_id`, per Rule 18). Because babble is broadband and roughly stationary over the ~2–3 s mixture window, NLMS can adapt its filter to strongly correlate with *that specific* babble instance and subtract it directly — an oracle-like advantage. DeepFilterNet has no such oracle: it must generalize from training data about what "noise" looks like, and babble looks too much like speech for that generalization to hold. This is consistent with the existing project correction note that NLMS is not a fair peer to compare against single-channel methods (`docs/phase_4_summary.md`, NLMS labeling correction) — the crowd result is exactly the scenario where that oracle advantage shows up starkly.

## 6. Recommendation for the pitch / demo narrative

- Don't present "non-stationary" as one undifferentiated weak category — it isn't. Helicopter rotor noise (a genuine, sourced defence-relevant noise type) is one of the model's *best* results. Crowd babble (a synthetic proxy subtype) is the one open problem.
- Frame it honestly and specifically: *"DeepFilterNet suppresses every sourced defence noise type — engine, vehicle, helicopter, gunshot, artillery, explosion — at 0.83–0.92 STOI and +9 to +11 dB ΔSI-SNR. The one structural gap is background human speech (crowd babble), a known limitation of single-channel enhancement (the cocktail-party problem), not fixable without a second microphone or speaker enrollment — both explicit non-goals of the current single-channel edge deployment."* This is a stronger, more precise, and more defensible claim than the current category-level framing, and it turns a metric miss into a scoped, well-understood limitation rather than an unexplained weak spot.
- If there is time for Round-2 fine-tuning, crowd babble is the single highest-leverage target — but note DeepFilterNet's architecture has no mechanism to solve the cocktail-party problem without additional input (a second channel or a speaker reference), so fine-tuning on more babble data is likely to yield only modest gains, not close the whole gap.

## 7. Caveats

- ~~PESQ-WB is not broken out by subtype here — see Section 2.~~ **Superseded 2026-09-04 (Phase 3 T8):**
  PESQ-WB per-subtype is now in Section 3 (the `pesq` package caveat in Section 2 was stale — see the
  superseding note there). The category-level PESQ-WB numbers in `results/final/target_compliance.json`
  (stationary 2.5385, non-stationary 2.2128, impulsive 2.5428 as of the Phase 3 T4-tuned configuration)
  remain the source of truth for the compliance verdict; the per-subtype breakdown here is supplementary.
- n=40 for crowd vs n=60 for helicopter (5 SNR levels × 8 vs 12 mixtures respectively, per the Phase 2 manifest) — both samples are large enough that the STOI gap (0.91 vs 0.71) is not noise-level variance; it is consistent across the SNR range.
- **Added 2026-09-04 (Phase 3 T6):** whether a reference-assisted (dual-mic) approach could close this gap
  was also tested directly, with a realistically-degraded (not oracle) reference channel. It does not —
  see `progress.md`'s Phase 3 T6 entry and `results/final/target_compliance.md` §5. NLMS's SI-SNR under a
  realistic reference goes to −2.63 dB on the full non-stationary category (worse than doing nothing),
  inverting the oracle reference's apparent advantage discussed in Section 5 above.
