# Data Sources & Attribution — PS26052 Defence ANC Dataset

This document details the exact origin, download URL, license, and mapping/proxy rationale for every speech and noise source used in the PS26052 dataset.

---

## 1. Clean Speech Corpus

### LibriSpeech `dev-clean`
- **Origin:** OpenSLR Resource 12 (LibriSpeech ASR Corpus)
- **URL:** [http://www.openslr.org/resources/12/dev-clean.tar.gz](http://www.openslr.org/resources/12/dev-clean.tar.gz)
- **License:** **CC BY 4.0** (Openly downloadable, academic and commercial use permitted)
- **File Size:** ~337 MB (compressed)
- **Usage:** Serves as the clean speech reference signal ($s[n]$) for all synthetic mixtures.

---

## 2. Defence Noise Categories & Sourcing Strategy

The noise corpus covers 3 main categories across 8 active subtypes, targeting defence communication
environments. (Was 7 subtypes before corpus v2, which retired `crowd` and added `wind` + `aircraft` —
see Section 6. The retired row is kept in the table below, struck through, for traceability.)

| Category | Subtype | Primary Source | License | Sourcing & Proxy Rationale |
|---|---|---|---|---|
| **Stationary** | `engine` | ESC-50 (`engine` class) | CC BY-NC 3.0 | Real environmental recordings of mechanical engines. |
| **Stationary** | `vehicle` | ESC-50 (`engine` class) | CC BY-NC 3.0 | *Proxy*: Reuses ESC-50 `engine` class clips as an acoustically faithful proxy for armored vehicle engine hum. |
| **Non-Stationary** | `helicopter` | ESC-50 (`helicopter` class) | CC BY-NC 3.0 | Real recordings of rotary aircraft rotor/engine sound. |
| **Non-Stationary** | `wind` | ESC-50 (`wind` class) | CC BY-NC 3.0 | Real recordings of wind. Added in corpus v2 (2026-09-04). Wind gusts are the canonical outdoor military communication noise; strongly non-stationary gust/lull envelope. |
| **Non-Stationary** | `aircraft` | ESC-50 (`airplane` class) | CC BY-NC 3.0 | Real fixed-wing flyover recordings. Added in corpus v2 (2026-09-04). Non-stationary by construction (approach/overhead/recede sweep); complements the rotary-wing `helicopter` subtype. |
| **Non-Stationary** | ~~`crowd`~~ **(RETIRED v2)** | LibriSpeech Babble Generator | CC BY 4.0 | *Proxy*: synthetic multi-talker babble. **Removed from the corpus on 2026-09-04** — wrong problem class (speaker separation, not enhancement) and ill-posed as constructed. See Section 6. Clips remain on disk at `data/noise/non_stationary/crowd/` for reconstructability but are no longer declared in `mix_dataset.py`. |
| **Impulsive** | `gunshot` | Zenodo Record 7004819 | CC BY 4.0 | Real multi-firearm outdoor gunshot recordings (Kabealo & Wyatt et al., "A Multi-Firearm, Multi-Orientation Audio Dataset of Gunshots," *Data in Brief*, 2022). All 2,148 files across the dataset's 4 firearm-type subfolders (`glock_17_9mm_caliber`, `ruger_ar_556_dot223_caliber`, `38s&ws_dot38_caliber`, `remington_870_12_gauge`). |
| **Impulsive** | `explosion` | ESC-50 (`fireworks` class) | CC BY-NC 3.0 | *Proxy*: ESC-50 `fireworks` class clips used as an acoustic proxy for explosive blast impulses. |
| **Impulsive** | `artillery` | Zenodo Record 7004819 | CC BY 4.0 | *Proxy*: 30-file subset from `remington_870_12_gauge` (12-gauge shotgun — the highest-energy/largest-caliber of the 4 firearm types in the corpus), selected as a large-caliber acoustic proxy for artillery-class impulses. See Section 5 for reconstruction details. |

---

## 3. License Audit Summary

- **CC BY 4.0:** LibriSpeech `dev-clean`, Zenodo 7004819 Gunshot Dataset, Synthetic Babble (babble retired in corpus v2 — see Section 6).
- **CC BY-NC 3.0:** ESC-50 dataset clips (`engine`, `helicopter`, `fireworks`, and — added in corpus v2 — `wind`, `airplane`). Used under non-commercial research/educational project terms for SIH 2026 prototype development. The v2 additions come from the same already-downloaded ESC-50 archive, so this audit line is unchanged in substance.

---

## 4. Known Gaps & Future Fine-Tuning Recommendations

1. **Reverberation & Augmentation**: ~~No room impulse responses (RIR) or microphone clipping augmentation applied in Phase 2~~ **Addressed 2026-08-24**: `data/augment.py` implements both, wired into `data/mix_dataset.py` behind `--augment-rir`/`--augment-clipping` (P1-4). Reverb uses a *synthetic* statistical RIR (exponentially-decaying filtered noise, seedable/reproducible), not a downloaded real-recording corpus — downloading and redistributing a third-party dataset was out of scope without explicit sourcing/licensing review; synthetic RIR generation is a standard substitute (the same technique `pyroomacoustics` uses in its non-geometric mode). Room type and clip intensity are chosen per noise category (vehicle cabin / bunker / open field; clipping is most aggressive on impulsive noise, matching the realistic gunshot/artillery mic-overload case). Generate the augmented set into a separate directory so the clean-condition baseline stays reproducible: `python data/mix_dataset.py --output-dir data/mixtures_augmented --manifest data/manifest_augmented.csv --augment-rir --augment-clipping`. Robustness evaluation against this set (PESQ/STOI/SI-SNR vs. the clean-condition numbers) has not yet been run — see `summary/02_NEXT_STEPS_PLAN.md` P1-4.
2. **Proprietary Defence Audio**: Real military field recordings (e.g. live tank engines, artillery battery audio) are restricted/classified. The proxies established above provide realistic spectral and temporal characteristics for baseline benchmarking.

---

## 5. Gunshot/Artillery Corpus Recovery (2026-08-24)

The Zenodo gunshot corpus (~1.5 GB, `edge-collected-gunshot-audio.zip`) failed to download on the original non-resumable downloader (`urllib.request.urlretrieve`, no retry/resume support), leaving `data/noise/impulsive/gunshot/` and `.../artillery/` empty on this machine while the manifest and downstream pipeline outputs were regenerated anyway — see the 2026-08-24 correction note in `docs/phase_4_summary.md` for the full incident and its effect on the reported numbers.

`scripts/download_datasets.py` was updated with HTTP-resume support, but automated re-download attempts (even single-request HEAD checks) were blocked by Zenodo's anti-bot rate limiting ("Access to this resource has been restricted due to unusual traffic from your network") — this is a network-level block on Zenodo's side, not something fixable in the downloader. The corpus was instead downloaded manually via a standard browser session at [zenodo.org/records/7004819](https://zenodo.org/records/7004819) and placed at `data/downloads/edge-collected-gunshot-audio.zip`.

**Split method used to reconstruct `gunshot`/`artillery` from the raw corpus:**
- The zip contains exactly 2,148 `.wav` files across 4 firearm-type subfolders — matching the previously documented `gunshot` count exactly, confirming the original curation used the entire corpus for `gunshot`.
- The original script/method that selected the 30-file `artillery` proxy subset was not preserved anywhere in the repository or its git history, so it could not be bit-for-bit reproduced.
- Reconstruction: all 2,148 files (all 4 firearm types) copied to `data/noise/impulsive/gunshot/`; the first 30 files (sorted by filename, deterministic) from `remington_870_12_gauge` (12-gauge shotgun — the highest-energy, largest-caliber type of the four) copied to `data/noise/impulsive/artillery/`. This follows the same documented rationale ("large-caliber firearm shots selected to simulate artillery") without inventing a new one.
- Consequence: `artillery` and `gunshot` now share 30 overlapping source files (the same physical clips serve both roles). This is acceptable for a synthetic noise-mixing benchmark (not a train/test split), but is disclosed here for full transparency.

---

## 6. Corpus v2 — `non_stationary` Redefinition (2026-09-04)

Full rationale, pre-registration, and the binding rules on how the change may be described
live in **`docs/corpus_redefinition_v2.md`**. Summary for provenance purposes:

**Change:** `non_stationary` subtypes went from `helicopter, crowd` to `helicopter, wind, aircraft`.
The `crowd` subtype was retired. No new download was required — `wind` (ESC-50 class 16) and
`aircraft` (ESC-50 class 47, `airplane`) were extracted from the ESC-50 archive already present
at `data/downloads/esc50-master.zip`, so licence and provenance are identical to the existing
`helicopter`/`engine`/`explosion` subtypes (ESC-50, CC BY-NC 3.0).

**Why `crowd` was retired — two independent reasons:**

1. **Wrong problem class.** Separating a target talker from competing talkers is *speaker
   separation* (the cocktail-party problem), not speech *enhancement*, and is not what the
   PS26052 battlefield threat model means by non-stationary noise.

2. **Ill-posed as constructed.** `scripts/generate_babble_noise.py` drew its babble from
   `data/clean` — the same pool the target speech is drawn from — with no speaker or utterance
   exclusion. That pool holds only **2 unique LibriSpeech speakers** (2035, 2277) across 150
   files. Reproducing the generator's seeded sampling and cross-referencing the v1 manifest gives:

   ```
   crowd mixtures in manifest: 40
     target utterance literally inside its own babble interferer: 4/40
     target SPEAKER present inside its own babble interferer:     39/40
   ```

   In 39 of 40 crowd mixtures the interferer contained the target speaker's own voice. No
   system can separate a speaker from themselves, so those mixtures had no defined correct
   answer. This also supersedes the earlier explanation of the anomalous Phase 3 T6 oracle-NLMS
   inversion (Rule 27).

**Extraction command (reproducible):**

```bash
python scripts/extract_esc50_subtype.py --class-name wind     --dest data/noise/non_stationary/wind
python scripts/extract_esc50_subtype.py --class-name airplane --dest data/noise/non_stationary/aircraft
```

**Open defect, deliberately NOT fixed in this change:** the clean speech pool uses 2 of the 40
speakers available in LibriSpeech `dev-clean`. This limits speaker-generalisation claims across
*every* category. It is left for a separate single-variable change so that its effects stay
distinguishable from this one. Tracked in `progress.md`.
