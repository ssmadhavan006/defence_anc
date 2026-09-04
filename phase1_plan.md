# PS26052 — Phase 1 Implementation Plan
## Dual-Channel (Primary + Reference) Hardware & Software Foundation

**Source plan:** `prototype.md` § "Phase 1 — Dual-Channel Hardware & Software Foundation"
**Target end-state:** `idea.md` § 2.2 (reference-aware architecture), § 2.2.4 (residual stage), § 3.3 (100% hardware target)
**Status:** DRAFT — awaiting sign-off. No code has been modified.
**Written against the repo at commit `baf2b74` (branch `main`, clean tree).**

---

## 0. How to read this document

Sections 1–4 are **what must be true when Phase 1 is done**. Section 5 is **the work**, written
against real file/line anchors in this repo so no step needs re-derivation. Sections 6–8 are the
**verification, risk and rollback** contracts. Section 9 is the **acceptance gate** — Phase 1 is not
done until every box there is ticked with pasted evidence, per `rules.md` Rule 3.

Section 3 lists **six decisions that need your answer before implementation starts.** Each has a
recommendation; if you reply "proceed" without comment, I will implement the recommended option.

---

## 1. Objective and Definition of Done

### 1.1 Objective

Move the live pipeline from **single-microphone speech enhancement** to a **primary + reference
two-channel capture path** with a genuine reference-based adaptive filter (Widrow NLMS) in the
signal chain — the one PS26052-explicit requirement (*"integrated with microphones (primary +
reference)"*) that the current system does not meet.

### 1.2 Definition of Done (the gate — all must hold simultaneously)

| # | Condition | Verified by |
|---|---|---|
| DoD-1 | Two microphone channels are captured on the Pi, time- and level-aligned, with a written calibration record | `live/calibrate_mic_pair.py` output pasted into `progress.md` |
| DoD-2 | A streaming reference-NLMS stage exists, is numerically equivalent to the offline `baselines/nlms/nlms.py` implementation, and runs chunk-continuous | Mode-A self-test PASS |
| DoD-3 | The dual-mic path runs 10 minutes continuous on the Pi with **0 dropouts, 0 inference errors** | `results/stress_dualmic.json` verdict PASS |
| DoD-4 | The single-mic path is **behaviourally identical** to today when dual-mic is disabled | Regression test + a stress run with `dual_mic.enabled: false` |
| DoD-5 | A live A/B (reference stage ON vs OFF) is demonstrable from a single keystroke during a demo | Pasted Pi session + spectrogram observation |
| DoD-6 | Every claim written into `README.md` / `architecture.md` is traceable to a pasted measurement | `progress.md` entry |

### 1.3 Explicitly NOT the goal of Phase 1

Phase 1 delivers **capability + stability**, not **proven quality improvement**. Whether
DFN3 + reference-NLMS beats DFN3 alone on PESQ/STOI is measured in **Phase 3 § 3.2**, on the offline
eval harness. Phase 1 must not assert a quality win. This mirrors how `live/residual_filter.py` was
correctly shipped off-by-default pending A/B evidence.

---

## 2. Ground truth — what exists today (code-verified, not assumed)

| Fact | Anchor |
|---|---|
| One `sd.InputStream`, one `sd.OutputStream`, both opened with the **same** `self._channels` | `live/pipeline.py:308`, `:584`, `:594` |
| Both ring buffers created with that same channel count | `live/pipeline.py:337-338` |
| `RingBuffer` is **already multi-channel capable** — `channels` is a constructor arg, storage is `(capacity, channels)` | `live/ring_buffer.py:45`, `:56` |
| Input callback already writes **all channels** of `indata` into the buffer unchanged | `live/pipeline.py:381-389` |
| The inference loop **discards** every channel but 0 | `live/pipeline.py:464-466` (`mono = chunk[:, 0]`) |
| Per-stream sample-rate resolution + resampling already exists and is independent per direction | `live/pipeline.py:186-253`, `:560-570` |
| The residual stage hook point (post-DFN, enhance-mode-only) already exists | `live/pipeline.py:497-500` |
| Optional-dependency lazy-import pattern (a disabled feature must never break the core path) | `live/pipeline.py:539-556` |
| Offline NLMS reference: numba-JIT, sample-serial, `L-1` zero-prepad, returns the **error** signal as the speech estimate | `baselines/nlms/nlms.py:19-67` |
| Reference-free ALE is the deliberate *stand-in* for this work, and its docstring already names the swap-in path | `live/residual_filter.py` module docstring, "Swap-in path for P1-2" |
| Stress test already accepts `--output-json`; verdict gates on `overflows + underruns` | `live/stress_test.py:182-190`, `:135-142` |
| Self-test runner registers each module with an optional-dependency SKIP rule | `scripts/run_all_selftests.py` `TESTS` |
| Deploy bundle includes `live/`, `config/`, `demo/`, `models/deepfilternet/` — **`scripts/` is NOT included** | `scripts/deploy_to_pi.py:35-36` |
| `numba==0.67.0` is verified to have a cp313/aarch64 wheel and to coexist with the `numpy==1.26.4` pin | `requirements-optional.txt` |
| `requirements-optional.txt` **cannot be installed as a whole on the Pi** — the ONNX entries are hard-incompatible with Python 3.13 | `requirements-optional.txt`, `config/audio_config.yaml` comments |

**Consequence of the last two rows:** Phase 1 promotes a numba-dependent stage from "optional
experiment" to "headline demo feature." The dependency question must be settled **before** any code
is written — see Task T0.

---

## 3. Decisions requiring sign-off

### D1 — Hardware topology (blocking; drives the purchase)

| Option | What it is | Verdict |
|---|---|---|
| **A. Single 2-in interface, stereo capture** | One USB device presenting `max_input_channels >= 2`; primary = ch0, reference = ch1 | **RECOMMENDED** |
| B. Two separate USB mics | Two devices, two `InputStream`s, two ring buffers (as literally written in `prototype.md` § 1.2) | Fallback only |

**Why A, strongly:** two USB audio devices have **two independent crystal clocks**. They drift
relative to each other (typically tens to hundreds of ppm). NLMS cancellation depends on the
reference staying sample-aligned with the noise in the primary; 50 ppm is ~2.4 samples/second at
48 kHz, i.e. the alignment calibration is invalid within seconds and cancellation collapses. A single
stereo device samples both mics off **one** clock — alignment is fixed for the session and is exactly
what the calibration script measures once.

**BOM trap to check before buying:** electret/lavalier mics need *plug-in power*; XLR interfaces
(Behringer UMC202HD) supply *phantom power* and expect XLR/TRS mics, not 3.5 mm electrets.
Three concrete buy paths:

| Path | Parts | Approx | Note |
|---|---|---|---|
| A1 | UMC202HD + 2× dynamic/condenser XLR mics | ₹8,000 + ₹3,000+ | Best audio, highest cost, bulky for a headset story |
| A2 (recommended) | Generic USB **stereo line-in** card + 2× electret + 2× plug-in-power preamp module (MAX9814 class) | ₹2,000 + ₹1,600 | Cheapest true-stereo path; matches the ₹15,000 BOM story in `idea.md` § 4.2 |
| A3 | USB interface with 2× 3.5 mm mic jacks that natively supply plug-in power | ₹2,500–4,000 | Simplest **if** a specific model is confirmed to enumerate as 2-in |

**Action needed from you:** confirm which is being bought. The code will be written
topology-agnostic either way, but the *validated* path is whichever hardware actually arrives.

### D2 — Module name: `reference_ale.py` vs `reference_nlms.py`

`prototype.md` says `live/reference_ale.py`. **"ALE" (Adaptive Line Enhancer) specifically means the
reference-FREE configuration** — `live/residual_filter.py`'s docstring goes out of its way to draw
that distinction, including the opposite output convention (ALE returns the *prediction*; NLMS
returns the *error*). Naming the reference-based filter "ALE" would contradict our own documentation
and is exactly the kind of silent convention inversion that module warns about.

**Recommendation:** `live/reference_nlms.py`, class `ReferenceNLMSFilter`, config key
`pipeline.reference_nlms`. The rename will be logged against `prototype.md` in `architecture.md`'s
decisions log so the two documents don't diverge silently.

### D3 — Where calibration output is written

`prototype.md` says the calibration script writes into the config. **`config/audio_config.yaml` is
heavily annotated** — every value carries the reasoning that produced it. `yaml.safe_dump()`
round-trips destroy **all** comments. A script that rewrites that file would delete the project's
most valuable config documentation on its first run.

**Recommendation:** calibration writes a separate machine-owned file **`config/mic_calibration.yaml`**
(small, no hand-written comments), which `_load_config()` merges into `audio.dual_mic.calibration`
when present. `audio_config.yaml` stays hand-owned and gains a comment pointing at it. `--dry-run`
prints the block instead of writing.

### D4 — Calibration script location

`prototype.md` says `scripts/calibrate_mic_pair.py`. **`scripts/` is not in the Pi deploy bundle**
(`scripts/deploy_to_pi.py:35`), and this script *only* runs on the Pi with hardware attached.

**Recommendation:** `live/calibrate_mic_pair.py` — satisfies Rule 9 (Pi-bound code under `live/`),
ships in the bundle automatically, and gets a `live/main.py calibrate` subcommand.

### D5 — Where the reference stage sits in the chain

`prototype.md` § 1.2 routes it **after** DFN3. That is defensible (residual cleanup) but has a real
theoretical weakness worth stating up front: DFN3 applies a **non-linear, time-varying** mask, so the
noise remaining in its output is no longer a *linear* function of what the reference mic hears. A
linear NLMS can only cancel the linearly-related part, so post-DFN cancellation will be weaker than
textbook ANC on the same signals. Pre-DFN placement (classical ANC first, neural second) keeps the
linear relationship intact but risks feeding DFN3 an input distribution it was not trained on.

**Recommendation:** implement **both**, config-switched (`reference_nlms_stage: post_dfn | pre_dfn`),
default `post_dfn` per `prototype.md`. The cost is ~6 lines; the payoff is that Phase 3 § 3.2 can
measure the question instead of arguing it. The expected post-DFN weakness is disclosed in the module
docstring from day one rather than discovered later.

### D6 — README wording (direct conflict with `rules.md` Rule 32)

`prototype.md` Phase 1 deliverable: *"README updated: system now described as **true dual-channel
adaptive noise cancellation**."*

**`rules.md` Rule 32:** *"The system is described … as AI/ML-enabled adaptive noise suppression /
speech enhancement, **not** as true active noise cancellation (ANC in the acoustic anti-noise sense),
unless secondary-path cancellation hardware is actually implemented."*

Phase 1 adds a reference **microphone**, not a secondary-path anti-noise **speaker**. Writing the
prototype's sentence into the README would violate our own rule and hand any experienced evaluator a
credibility hit.

**Recommended wording (accurate and still strong):**

> "Dual-channel (primary + reference) AI/ML noise suppression, combining DeepFilterNet3 with a
> Widrow reference-based adaptive noise-cancelling filter (NLMS) on the reference channel."

This keeps the technically-correct term "adaptive noise cancelling" attached to the *filter* (which
is precisely Widrow's 1975 name for it) without claiming acoustic ANC for the *system*. Rule 31 also
applies: dual-mic results are reported on a **separate reference-assisted track**, never blended into
one ranking with the single-channel methods.

---

## 4. Requirements

### 4.1 Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | The pipeline shall capture a primary and a reference microphone channel, selectable by config. |
| FR-2 | Topology A (one device, ≥2 input channels) shall be supported, with configurable primary/reference channel indices. |
| FR-3 | Topology B (two devices, two `InputStream`s, a second ring buffer) shall be supported and documented as drift-limited (see R1). |
| FR-4 | A streaming, chunk-continuous, stateful NLMS filter shall accept `(primary_chunk, reference_chunk)` and return an enhanced chunk of identical length. |
| FR-5 | The filter shall be numerically equivalent to `baselines/nlms/nlms.py:19` given the same input and no chunk boundaries. |
| FR-6 | Chunked processing shall be bit-identical to one-shot processing of the same signal. |
| FR-7 | Reference alignment (integer sample delay) and level match (linear gain) shall be applied from a calibration record before the filter runs. |
| FR-8 | A calibration routine shall measure that delay and gain on real hardware and persist them. |
| FR-9 | The reference stage shall be switchable at runtime (single keystroke) for live A/B demonstration. |
| FR-10 | Device detection shall identify and report devices with ≥2 input channels and emit a ready-to-paste dual-mic config block. |
| FR-11 | The stress test shall report dual-mic-specific counters and write to `results/stress_dualmic.json`. |
| FR-12 | Both demo UIs shall display reference-stage state (ON/OFF) and reference-channel health. |

### 4.2 Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | **Zero regression:** with `dual_mic.enabled: false`, behaviour is identical to today — same streams, same buffers, same channel count, same code path. |
| NFR-2 | **No hot-path blocking:** audio callbacks gain no locks, no allocation growth, and no reference-dependent branching that can block. |
| NFR-3 | **Graceful degradation:** if the reference channel starves or errors, the pipeline continues DFN-only, increments a counter, and never drops audio. |
| NFR-4 | **Optional-dependency safety:** a missing `numba` fails loudly *only* when the feature is enabled, never at import time (existing lazy-import pattern preserved). |
| NFR-5 | **RTF budget:** the added stage must keep p95 RTF < 0.7 at the current 100 ms chunk (headroom for Phase 2's sweep). Measured, not assumed. |
| NFR-6 | Every new script is independently runnable and carries a Mode-A self-test (Rule 8). |

### 4.3 Compliance requirements (mapped to `rules.md`)

| ID | Rule | Obligation in Phase 1 |
|---|---|---|
| CR-1 | R29 | Every hardware test is Mode B — not marked passed without pasted Pi output. |
| CR-2 | R2 | Multi-channel `sounddevice` behaviour, `max_input_channels`, and stereo `check_input_settings` are verified against the installed version before use — not assumed. |
| CR-3 | R5, R33 | Every number is labelled with the machine it ran on and reported as measured, including misses. |
| CR-4 | R32 | No "true ANC" claim (see D6). |
| CR-5 | R31 | Dual-mic results reported on a separate reference-assisted track. |
| CR-6 | R8 | Self-tests for both new modules. |
| CR-7 | R9 | Pi-bound code under `live/`. |
| CR-8 | R7 | `architecture.md` updated **before** the restructure, with rationale. |
| CR-9 | R1, R3 | No quality claim for the new stage in Phase 1 — capability + stability only. |
| CR-10 | R6 | `uv` on the dev machine; `pip` on the Pi as the logged exception. |

---

## 5. Work breakdown

### T0 — Dependency spike (BLOCKING, do first, ~1 hour)

The reference NLMS is numba-JIT: a pure-Python NLMS at 256 taps × 4800 samples/chunk is far too slow
for real time. numba is currently **optional** and lives in a file that **cannot be installed
wholesale on the Pi** because of the ONNX entries.

1. On the Pi: `pip install numba==0.67.0` (standalone, **not** `-r requirements-optional.txt`).
2. Verify: `python -c "import numba, numpy; print(numba.__version__, numpy.__version__)"` — numpy must
   still read `1.26.4`.
3. Re-run `python scripts/run_all_selftests.py` on the Pi; `residual_filter` must flip SKIP → PASS.
4. Decide the dependency's home:
   - **Recommended:** move `numba==0.67.0` into **`requirements.txt`** with the exact-pin rationale
     comment, because dual-mic is now a core demo feature — then re-verify a clean
     `pip install -r requirements.txt` on the Pi (that file's stated contract is that it must always
     install cleanly).
   - Also split the ONNX block out of `requirements-optional.txt` into `requirements-onnx-dev.txt`
     so `requirements-optional.txt` itself becomes Pi-installable.

**Gate:** if numba cannot be installed on the Pi, Phase 1 stops here and we re-plan. A pure-numpy
block-LMS is a *different algorithm* with different results — it would fail FR-5, so it is not an
acceptable silent substitute.

**Evidence to paste:** install output, the version print, and the self-test summary.

---

### T1 — Hardware acquisition & enumeration

1. Purchase per D1.
2. On the Pi: `arecord -l`, `arecord -L`, `python live/main.py detect`.
3. Confirm the interface enumerates with `max_input_channels >= 2` (Topology A) or that both devices
   appear (Topology B).
4. Record the **exact device indices and names** — note the USB re-enumeration hazard already
   documented in `config/audio_config.yaml`.
5. Capture 5 s of two-channel audio: `arecord -D plughw:X,0 -c 2 -f S32_LE -r 48000 -d 5 test2ch.wav`,
   then print per-channel peak/RMS and confirm both channels carry independent signal.

**Evidence:** `detect` output + per-channel peak/RMS.

---

### T2 — Config schema extension (`config/audio_config.yaml`)

Add to the `audio:` section, fully commented in the file's existing house style:

```yaml
  # --- P1-2: dual-microphone (primary + reference) capture ---
  dual_mic:
    # Master switch. false => byte-for-byte today's single-mic behaviour.
    enabled: false

    # "single_device_stereo" (RECOMMENDED): one interface, >=2 input channels,
    #   both mics on ONE hardware clock -- no inter-device drift.
    # "two_devices": two independent InputStreams. Supported, but the two
    #   devices free-run on separate crystals; see docs/dual_mic_topology.md
    #   for the measured drift and why it degrades NLMS over a session.
    topology: "single_device_stereo"

    primary_channel: 0
    reference_channel: 1

    # two_devices topology only (ignored otherwise):
    reference_input_device: null
    reference_channels: 1

    # Written by `python live/main.py calibrate`. Merged in from
    # config/mic_calibration.yaml when that file exists -- do NOT hand-edit
    # here; this block is the documented default, the machine-written file wins.
    calibration:
      reference_delay_samples: 0   # +ve = reference LAGS primary; pipeline advances it
      reference_gain: 1.0          # linear, applied to reference before the filter
      measured_on: null            # ISO timestamp + machine, filled by the script
      method: null                 # "passive_clap" | "active_chirp"
```

Add to the `pipeline:` section:

```yaml
  # P1-2: reference-based NLMS stage (Widrow adaptive noise cancelling).
  # Requires audio.dual_mic.enabled: true. OFF by default until Phase 3's
  # PESQ/STOI A/B says it is a net quality win -- the same discipline applied
  # to pipeline.residual_filter. Phase 1 proves capability, not quality.
  reference_nlms: false
  reference_nlms_stage: "post_dfn"     # or "pre_dfn" -- see phase1_plan.md D5
  reference_nlms_filter_length: 256    # 256 taps @48kHz = 5.3 ms of acoustic path
  reference_nlms_mu: 0.01
  reference_nlms_eps: 1.0e-6
```

Mirror every new key in `_load_config()`'s `defaults` dict (`live/pipeline.py:80-108`) so a stale or
missing config file cannot produce a `KeyError`.

---

### T3 — `live/reference_nlms.py` (new module)

**Algorithm:** NLMS, identical formulation to `baselines/nlms/nlms.py:19` —
`e[n] = d[n] − wᵀx[n]`, `w ← w + (μ / (‖x‖² + ε))·e[n]·x[n]` — returning **`e[n]`** as the enhanced
output, with the same `L−1` zero-prepad convention at stream start.

**Streaming state carried between chunks:** `weights (L,)`, `ref_history (L−1,)`, plus a
`delay_samples`-length reference alignment queue.

**Public API:**

```python
class ReferenceNLMSFilter:
    def __init__(self, filter_length=256, mu=0.01, eps=1e-6,
                 delay_samples=0, ref_gain=1.0): ...

    def process_chunk(self, primary: np.ndarray, reference: np.ndarray) -> np.ndarray:
        """Both 1-D float32, equal length. Returns e[n], same length."""

    def reset(self) -> None: ...

    @property
    def erle_db(self) -> float:
        """Running Echo-Return-Loss-Enhancement estimate, 10*log10(P_d / P_e).
        TELEMETRY ONLY -- an internal sanity number, never a quality metric.
        PESQ/STOI come from the eval harness, not from here."""
```

**Numba kernel:** `_nlms_process(primary, reference, ref_history, weights, filter_length, mu, eps)
-> (out, weights, new_history)`, `@jit(nopython=True, fastmath=True)`, JIT-warmed in `__init__`
(same pattern as `ResidualALEFilter.__init__`, `live/residual_filter.py:145-150`) so the first live
chunk never eats the compile stall.

**Docstring must state, up front:** the output-convention difference vs `residual_filter.py`
(error vs prediction), the D5 post-DFN linearity caveat, and that no quality claim exists yet.

**Self-test — `python live/reference_nlms.py --self-test` (Mode A, no hardware), 6 tests:**

| # | Test | Pass criterion |
|---|---|---|
| 1 | Chunked (100 ms) vs one-shot on the same signal | `max|Δ| == 0.0` (bit-exact) |
| 2 | Agreement with `baselines/nlms/nlms.py:19` one-shot, same `L`/`mu`, same prepad | `max|Δ| <= 1e-6` |
| 3 | Convergence: `primary = speech + (h * noise)`, `reference = noise` | SI-SNR improves; the threshold is **set from the first measured run and then frozen in the file** — never asserted from a guess (Rule 1) |
| 4 | Delay handling: reference delayed by K samples, `delay_samples=K` | within 0.5 dB of the K=0 result |
| 5 | Degenerate inputs: all-zero reference, all-zero primary, digital silence | finite output, no NaN/Inf, no div-by-zero |
| 6 | State isolation: `reset()` returns the filter to its constructed state | weights and history all-zero; output matches a fresh instance |

Register in `scripts/run_all_selftests.py` `TESTS` as
`("reference_nlms", [sys.executable, "live/reference_nlms.py", "--self-test"], False, "numba")`.

---

### T4 — `live/pipeline.py` changes

Ordered, each independently testable:

1. **Split channel counts.** Replace `self._channels` (`:308`) with `self._in_channels` /
   `self._out_channels`. `_out_channels` always comes from `audio.channels` (unchanged, mono);
   `_in_channels` becomes 2 when `dual_mic.enabled` and topology is `single_device_stereo`.
   Update `:337-338` (ring buffers), `:563-566` (`_resolve_stream_samplerate`), `:584`/`:594`
   (stream open), `:609` (priming silence array).
2. **Input callback:** *no change required for Topology A* — `:381-389` already writes all channels.
   This is the whole reason to prefer Topology A: **zero hot-path modification.**
3. **Topology B additions (only if D1 → B):** `self._ref_buf`, `self._stream_in_ref`,
   `_ref_input_callback`, independent `_ref_stream_sr` resolution + resampling. Reference reads use
   non-blocking semantics: if the reference chunk is unavailable, process DFN-only for that chunk and
   increment `self._ref_starved_chunks` (NFR-3) — never block, never drop audio.
4. **Inference loop** (`:464-466`): extract `primary = chunk[:, primary_ch]` and
   `reference = chunk[:, reference_ch]`; apply `ref_gain`. The delay alignment lives inside
   `ReferenceNLMSFilter` (it needs cross-chunk state anyway).
5. **Stage insertion:**
   - `pre_dfn`: `mono = self._ref_nlms.process_chunk(mono, reference)` before `enhance_chunk`.
   - `post_dfn` (default): `out_mono = self._ref_nlms.process_chunk(out_mono, reference)` alongside
     the existing residual hook at `:497-500`.
   - Both are **enhance-mode only**, matching the residual-filter precedent, so `bypass` stays a
     clean latency baseline.
   - Ordering when both stages are on: DFN3 → reference NLMS → residual ALE. Documented in code.
6. **Lazy import** of `live.reference_nlms` inside `start()`, mirroring `:539-556` exactly, with the
   same actionable `RuntimeError` naming the install command (NFR-4).
7. **Runtime toggle:** `def toggle_reference_stage(self) -> bool:` — flips the stage and calls
   `reset()` on the filter so stale weights from the previous state don't bias the next (FR-9).
8. **Telemetry:** `self.last_ref_chunk` (display-only, same benign race as `last_in_chunk` — comment
   it identically), `self._ref_starved_chunks`, and ERLE. Add all three to `_print_stats()` (`:637`).

---

### T5 — `live/calibrate_mic_pair.py` (new, Mode B)

**Purpose:** measure the integer sample delay and the level ratio between primary and reference.
Mis-alignment is the single most common cause of an NLMS stage doing nothing — the same class of bug
as the offline `combo_seed` alignment fix.

**Two measurement modes:**

- `--passive` (**default, safest**): records N seconds of two-channel input and asks the operator for
  a sharp transient (a clap). Cross-correlates ch0 vs ch1 over ±5 ms and takes the argmax lag.
  **No playback → no feedback-loop risk**, which matters given the documented incident where an
  acoustic mic→headset loop at high gain froze the Pi.
- `--active`: plays a short log chirp through the output device while recording. Requires an explicit
  acknowledgement flag and prints the feedback warning first.

**Outputs:** median and p95 lag over ≥5 transients, RMS ratio → `reference_gain`, plus a per-channel
sanity print (peak/RMS, dead-channel detection — the defective-headset incident of 2026-08-26 is
precedent for making a dead mic loudly visible rather than silently plausible).

**Writes:** `config/mic_calibration.yaml` (D3), with `measured_on` = ISO timestamp + hostname.
`--dry-run` prints only. Refuses to write when lag p95 − median > 1 sample (an unstable measurement,
which almost always means two free-running clocks, i.e. Topology B drift).

**Self-test** `--self-test` (Mode A): runs the correlation/gain math against synthetically delayed
and attenuated signal pairs; must recover the injected delay exactly and the gain within 1 %.

**CLI:** exposed as `python live/main.py calibrate` (add to `live/main.py:27-32` choices + dispatch).

---

### T6 — `live/detect_devices.py` extension

Print `Max Inputs` prominently, tag any device with `max_input_channels >= 2` as
`[2-in candidate — dual-mic capable]`, and extend the "Suggested YAML Config Settings" block to emit a
complete, paste-ready `dual_mic:` block for the best candidate found. If none is found, say so
explicitly and name the Topology B fallback.

---

### T7 — Demo UI updates

- **`demo/dashboard.py`:** new status row — `REF: ON/OFF · stage: post_dfn · ERLE: x.x dB ·
  ref-starved: N`. Bind **`r`** to `pipeline.toggle_reference_stage()` alongside the existing `b`
  (`demo/dashboard.py:114-116`).
- **`demo/spectrogram.py`:** same `r` binding (`demo/spectrogram.py:148`); header shows
  `ENHANCE + REF` / `ENHANCE`. *Optional, clearly marked nice-to-have:* a third waterfall panel for
  the reference channel — implement only if it does not complicate the two-panel judged demo.

---

### T8 — Stress test extension (`live/stress_test.py`)

Add a `dual_mic` block to the `summary` dict (`:147-165`): `enabled`, `topology`, `reference_nlms`
(bool), `stage`, `ref_starved_chunks`, and `calibration` (the exact values in force). Verdict logic is
unchanged — `ref_starved_chunks` is **reported, not gated** (it degrades quality, not real-time
integrity), and that distinction is stated in the file, consistent with how `_teardown_underruns` is
already kept separate from real dropouts.

---

### T9 — Packaging & deployment

- `scripts/deploy_to_pi.py`: no include-list change needed **if** D4 → `live/` (recommended). If
  D4 → `scripts/`, add `scripts/calibrate_mic_pair.py` to `includes` (`:35-36`) — otherwise the script
  will simply not exist on the Pi.
- `requirements.txt` / `requirements-optional.txt` per T0's outcome, each with the exact-pin rationale
  comment in the existing house style.
- Rebuild `pi_deploy.zip`; re-verify a clean `pip install -r requirements.txt` on the Pi.

---

### T10 — Documentation & evidence

| File | Update |
|---|---|
| `architecture.md` | **First** (Rule 7): component-matrix rows for the two new modules, updated live data-flow diagram showing two capture channels, decisions-log entries dated for D1–D6 including the `reference_ale` → `reference_nlms` rename against `prototype.md` |
| `README.md` | Wording per D6 (no "true ANC"); dual-mic presented as a capability with its measured stability evidence, and explicitly **not** yet a quality claim |
| `progress.md` | One append-only entry with every command and its **pasted** output: T0 install, T1 enumeration, self-tests, calibration, 60 s bypass, enhance session, 600 s stress |
| `docs/dual_mic_topology.md` (new) | The topology decision, the clock-drift reasoning, and — if Topology B is used — the **measured** drift over 10 minutes |
| `config/audio_config.yaml` | Inline documentation for every new key, in the file's existing annotated style |

---

## 6. Test plan

### 6.1 Mode A — dev machine, no hardware (`uv`, per Rule 6)

| # | Command | Pass criterion |
|---|---|---|
| A1 | `uv run python live/reference_nlms.py --self-test` | 6/6 PASS |
| A2 | `uv run python live/calibrate_mic_pair.py --self-test` | delay recovered exactly, gain within 1 % |
| A3 | `uv run python scripts/run_all_selftests.py` | 10/10 PASS (9 existing + 1 new) |
| A4 | Construct `LivePipeline` with `dual_mic.enabled: false` | constructs; `_in_channels == _out_channels == 1`; identical to today (NFR-1) |
| A5 | Same with `dual_mic.enabled: true` but `numba` hidden | raises the actionable `RuntimeError`, **not** `ModuleNotFoundError` at import (NFR-4) |

### 6.2 Mode B — Raspberry Pi 5, real hardware (Rule 29: paste output or it did not happen)

| # | Command | Pass criterion |
|---|---|---|
| B1 | `python live/main.py detect` | interface enumerates with ≥2 input channels (or both devices listed) |
| B2 | `arecord -D plughw:X,0 -c 2 -r 48000 -f S32_LE -d 5 t.wav` + per-channel peak/RMS | both channels carry independent, non-dead signal |
| B3 | `python live/main.py calibrate --passive --seconds 15` | stable lag (p95 − median ≤ 1 sample); `config/mic_calibration.yaml` written |
| B4 | `python live/main.py pipeline --mode bypass` for 60 s | 0 dropouts, 0 overflows, both channels captured |
| B5 | `python live/main.py pipeline --mode enhance` with `reference_nlms: true` | runs clean; ERLE finite and non-zero; p95 RTF < 0.7 (NFR-5) |
| B6 | `python demo/spectrogram.py` — real crowd/babble source, toggle `r` | operator-observed A/B; **recorded as an observation, not as a metric** (Rule 1) |
| B7 | `python live/main.py stress --duration 600 --output-json results/stress_dualmic.json` | verdict PASS; **0 dropouts, 0 inference errors**; max temp < 80 °C |
| B8 | Repeat B7 with `dual_mic.enabled: false` | verdict PASS — proves no single-mic regression (DoD-4) |
| B9 | `python scripts/run_all_selftests.py` on the Pi | ≥8 PASS; the only remaining SKIPs are the known ONNX ones |

> **Note on B6:** Phase 1 records *what the operator saw*. The claim "dual-mic improves crowd-babble
> suppression" requires the offline A/B in Phase 3 § 3.2 and must not be written anywhere until then.

---

## 7. Risk register

| ID | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | **Inter-device clock drift** (Topology B): two USB devices free-run; ~50 ppm ⇒ ~2.4 samples/s at 48 kHz, so alignment dies within seconds | NLMS silently does nothing | Prefer Topology A (D1). If B is unavoidable: measure drift over 10 min, document it in `docs/dual_mic_topology.md`, and treat NLMS output as unvalidated |
| R2 | **Electret mics get no plug-in power** from an XLR/phantom interface | Dead reference channel that looks alive | Settle D1 before purchase; B2's dead-channel detection catches it immediately |
| R3 | **Post-DFN linearity gap** (D5): DFN3's mask is non-linear, so the residual noise is not a linear function of the reference | Weak measured cancellation | Both stage orders implemented and config-switched; caveat documented in the module docstring from day one; measured in Phase 3 |
| R4 | **numba unavailable/unbuildable on the Pi** | Feature cannot ship | T0 is a hard blocking gate before any code is written; no silent algorithm substitution |
| R5 | **Acoustic feedback loop** (precedent: froze a Pi) | Hardware/demo failure | Calibration defaults to `--passive` (no playback); `--active` requires an explicit acknowledgement flag; gain limits restated in the runbook |
| R6 | **Added stage blows the RTF budget** at 100 ms chunks | Real-time claim regresses | NFR-5 gate at B5; 256 taps is a starting point and the tap count is config-driven, so it can be reduced with a measured trade-off — never silently re-tuned to make a number pass (Rule 33) |
| R7 | **USB re-enumeration** changes indices after reboot/replug (an already-documented hazard) | Demo-day failure | Re-run `detect` in the pre-flight; the existing `_resolve_device` fallback already warns loudly rather than crashing |
| R8 | **Filter length too short for the real acoustic path** — 64 taps ≈ 1.3 ms ≈ 45 cm | Poor cancellation misread as a broken implementation | Start at 256 taps; sweep as a measured experiment; record the chosen value with its rationale |
| R9 | **Calibration script destroys the annotated config** | Loss of the project's best documentation | D3: write to a separate machine-owned file; never `yaml.safe_dump` over `audio_config.yaml` |
| R10 | **Scope creep into quality claims** | Rule 1/3 violation, credibility loss | CR-9: Phase 1 asserts capability and stability only |

---

## 8. Backward compatibility & rollback

**Compatibility contract:** with `audio.dual_mic.enabled: false` (the shipped default), the pipeline
opens exactly one input stream with exactly one channel, allocates the same two mono ring buffers, and
executes the same inference path as commit `baf2b74`. Test A4 and stress run B8 exist purely to prove
this.

**Rollback:** every change is additive and sits behind the `dual_mic.enabled` / `reference_nlms`
switches. Reverting is: set both to `false` (config-only, zero code change). A full revert is a
single-commit `git revert` — the two new modules are leaf files that nothing imports at module scope.

**Demo-safety invariant:** the judged demo path must remain runnable at all times. No commit lands
that has not passed A3 on the dev machine, and no Pi-side change lands without B7 or B8 green.

---

## 9. Phase 1 acceptance checklist

Derived from `prototype.md` § "Phase 1 Deliverables Checklist", expanded to be verifiable and
rule-compliant. **Nothing is ticked without pasted evidence (Rule 3).**

### Gate 0 — Dependency
- [ ] `numba==0.67.0` installs on the Pi standalone; `numpy` still reads `1.26.4` (output pasted)
- [ ] `residual_filter` self-test flips SKIP → PASS on the Pi
- [ ] Dependency home decided; both requirements files updated with rationale comments
- [ ] `pip install -r requirements.txt` still completes cleanly on the Pi (its stated contract)

### Gate 1 — Hardware
- [ ] Interface + second mic physically connected and enumerated on the Pi (`detect` output pasted)
- [ ] Device reports `max_input_channels >= 2` (Topology A) or both devices enumerate (Topology B)
- [ ] Two-channel `arecord` capture shows independent, non-dead signal on both channels
- [ ] Chosen topology and its rationale recorded in `docs/dual_mic_topology.md`

### Gate 2 — Software
- [ ] `config/audio_config.yaml` carries the documented `dual_mic` + `reference_nlms` schema
- [ ] `_load_config()` defaults mirror every new key (no `KeyError` on a stale config)
- [ ] `live/reference_nlms.py` exists; 6/6 self-tests PASS, including bit-exact chunked ≡ one-shot and
      ≤1e-6 agreement with `baselines/nlms/nlms.py`
- [ ] `live/pipeline.py` runs dual-channel capture with no dropouts
- [ ] Reference stage insertable at both `pre_dfn` and `post_dfn`, config-switched
- [ ] Runtime `r` toggle works in both demo UIs
- [ ] `live/calibrate_mic_pair.py` self-test PASSES; hardware run writes `config/mic_calibration.yaml`
- [ ] `live/main.py calibrate` subcommand wired
- [ ] `detect_devices.py` emits a paste-ready `dual_mic` block
- [ ] `stress_test.py` reports the `dual_mic` block in its JSON
- [ ] New module registered in `scripts/run_all_selftests.py`; full suite green on the dev machine

### Gate 3 — Hardware validation (Mode B, Rule 29)
- [ ] 60 s bypass, dual-mic active: 0 dropouts, 0 overflows
- [ ] Enhance + reference stage: runs clean, ERLE finite, p95 RTF < 0.7 (number pasted)
- [ ] Calibration produces a stable lag (p95 − median ≤ 1 sample)
- [ ] **10-minute dual-mic stress test PASS**, `results/stress_dualmic.json` committed
- [ ] **10-minute single-mic regression stress test PASS** (`dual_mic.enabled: false`) — DoD-4
- [ ] Spectrogram `r` A/B performed on real crowd babble; observation recorded as an observation
- [ ] Pi self-test suite: ≥8 PASS, only the known ONNX SKIPs remain

### Gate 4 — Documentation & compliance
- [ ] `architecture.md` updated **first**, with the D1–D6 decisions log (Rule 7)
- [ ] `README.md` wording per D6 — no "true ANC" claim (Rule 32)
- [ ] Dual-mic results framed as a separate reference-assisted track (Rule 31)
- [ ] `progress.md` entry with every command and its real pasted output, failures included (Rules 1–4)
- [ ] Every number labelled with the machine that produced it (Rule 5), reported as measured (Rule 33)
- [ ] No quality/PESQ/STOI claim anywhere for the new stage (CR-9) — deferred to Phase 3
- [ ] `pi_deploy.zip` rebuilt and verified to contain both new modules

---

## 10. Out of scope for Phase 1 (deliberately deferred)

| Item | Where it belongs |
|---|---|
| PESQ/STOI A/B proving the reference stage is a quality win | Phase 3 § 3.2 |
| Turning `reference_nlms` ON by default | Phase 3, only if the A/B says so |
| Latency re-optimisation with the added stage (chunk sweep, core pinning, sub-150 ms) | Phase 2 |
| True acoustic mouth-to-ear latency measurement | Phase 2 § 2.4 |
| Noise classifier, web dashboard, DNSMOS | Phase 4 |
| Model fine-tuning, ONNX on the Pi, INT8 | Out of the 60–80 % scope by design |
| Beamforming / multi-channel neural front-end | Not scoped — a different architecture |

---

## 11. Effort estimate

| Task | Effort | Dependency |
|---|---|---|
| T0 dependency spike | 1 h | Pi access — **blocking** |
| T1 hardware + enumeration | 2 h | Purchase arrival — **blocking** |
| T2 config schema | 1 h | D1–D5 answered |
| T3 `reference_nlms.py` + self-tests | 4–5 h | T0 |
| T4 pipeline integration | 3–4 h | T2, T3 |
| T5 calibration script | 3 h | T2 |
| T6 detect extension | 1 h | — |
| T7 demo UIs | 1.5 h | T4 |
| T8 stress extension | 0.5 h | T4 |
| T9 packaging | 1 h | T0, T5 |
| T10 docs + evidence | 2 h | all |
| Mode B validation (incl. 2 × 10-min stress) | 2.5 h wall-clock | all |

**≈ 2 days of focused work**, matching `prototype.md`'s estimate, with T0 and T1 as the two hard
blockers that gate everything else.
