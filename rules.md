# PS26052 — Non-Negotiable Project Rules

**Anti-hallucination / anti-fabrication:**
1. Never write a metric, benchmark number, "it works", or performance claim into `progress.md`, `README`, or any report unless it came from an actual command you (or the user, per Section 4) executed and whose output you can quote.
2. Never assume a library's API, CLI flags, config keys, or file formats. Check with `--help`, `uv pip show <pkg>`, reading the installed package's actual source, or official docs before using an API you're not 100% certain of from *this* installed version.
3. Never claim a task is "done" in progress.md without pasting the evidence (command + relevant output) in the same log entry.
4. If something fails, log the failure honestly with the real error message. Do not silently retry-and-hide, do not paraphrase an error into something that sounds better, do not skip a broken step and move on without flagging it.
5. Never report a PC-measured benchmark as a Pi/edge result, under any framing. Label every benchmark with the exact machine it ran on.

**Engineering discipline:**
6. Use `uv` exclusively for all Python package/environment management on the computer side. Do not use bare `pip install`. (`uv venv`, `uv add <pkg>`, `uv sync`, `uv run <script>`, `uv pip install` only as a last-resort compat shim if `uv add` truly can't resolve something — and log why.)
   - *Pi Exception Note:* `uv` is not installed on the target Raspberry Pi 5 (Debian 13 trixie). Packages on the Pi may be installed using standard `venv` + `pip` or `apt` as an explicitly logged exception.
7. Follow the folder structure in `architecture.md`. If you need to restructure, update `architecture.md` first with the rationale, then restructure.
8. Every script you write must be independently runnable and, where feasible, include a minimal self-test or sanity check (e.g., asserting output file exists, sample rate matches, array shape correct).
9. Keep Pi-bound code physically separate (under a clearly named directory, e.g. `pi_deploy/` or `live/`) from training/dataset code, per the roadmap's rule that the Pi should never carry the full research tree.
10. Commit-worthy checkpoints: after each meaningful working increment, note it in progress.md even if you're not the one running `git commit`.

**Scope discipline:**
11. Do not start Phase 2+ work (dataset generation at scale, fine-tuning, live pipeline) until Phase 1's Definition of Done (Section 6) is fully met and logged. It's fine to prep Phase 0 folders that Phase 2 will use, but don't jump ahead on implementation.

---
## Phase 2 Rules Addendum

12. Every noise/speech source used in the dataset must be traceable to a real, verifiable, licensed origin, recorded in `data/SOURCES.md`. No fabricated dataset names or unverified URLs.
13. Every mixture's *actual achieved SNR* must be computed post-mixing and compared against the *requested* SNR — don't trust the mixing gain math blindly. Log the mean/max deviation across the dataset. A silent mismatch here would poison every downstream metric.
14. All dataset audio must be verified at a consistent 48 kHz before being written to `data/mixtures/` — resample explicitly and log when resampling was needed (source rate → 48 kHz), don't assume source files already match.
15. Dataset size must stay proportionate to the hackathon timeline — prefer small, well-documented, reproducible subsets over exhaustive downloads. If a source's full download would be large/slow, don't fetch all of it "just in case."
16. `manifest.csv` row count must equal the actual number of mixture files on disk, verified programmatically, before Phase 2 is marked done — no manifest entries for files that don't exist, no orphan files missing from the manifest.

---
## Phase 3 Rules Addendum

17. Classical DSP baselines must be genuine implementations of their named textbook algorithm (verified against the standard formula), never a substituted library that produces superficially similar output under a different method name.
18. NLMS must use the true original pre-mix noise clip as its reference-channel input, sourced via the manifest's `noise_id`, for every mixture it processes — never the mixed signal, a delayed/shifted version of it, or a fabricated stand-in.
19. Before running any DSP baseline across the full 300-file dataset, time it on a small pilot subset (e.g. 5–10 files) first and extrapolate total runtime. Log the pilot timing and the decision it led to (run directly vs. checkpointed/backgrounded) in `progress.md`.
20. Batch-processing scripts for this phase must be resumable/idempotent — skip files whose output already exists rather than reprocessing, so a long run can be safely interrupted and continued without duplicating work or silently losing progress.
21. No PESQ/STOI/SI-SNR numbers may appear anywhere in Phase 3 outputs or logs. If a lightweight internal sanity metric is needed to confirm an algorithm isn't producing silence/NaNs/garbage, it must be clearly labeled as an internal sanity check, not a Phase 4 evaluation result.

---
## Phase 4 Rules Addendum

22. Every metric score computed in this phase — for all 5 conditions including the unprocessed "noisy" condition — must use that mixture's `clean_ref_path` as the reference signal. Never the raw pre-mix clean source file. This applies equally to DeepFilterNet outputs.
23. PESQ-WB and STOI must each be computed using the exact input sample-rate behavior verified from the actual installed library (docs/signature/source), not assumed from memory. Any required resampling for a metric call must be done on an in-memory copy only — the underlying 48 kHz files on disk are never altered.
24. Any per-file metric computation that throws an exception must be logged with the mixture_id, method, and the real error message, and excluded from that metric's aggregates with the exclusion count explicitly reported — never silently dropped, and never backfilled with a placeholder or estimated value.
25. ΔSI-SNR for a given (mixture, method) row must be computed as that row's SI-SNR minus the SI-SNR of the "noisy" condition for the **same mixture** — never against a dataset-wide average or a different mixture.
26. Before generating `results.csv` or any chart, verify the row count of `eval_raw.csv` equals 1,500 minus any Rule-24 exclusions, and state the exclusion count explicitly in `progress.md`. No silent gaps between expected and actual coverage.

---
## Phase 4 Remediation Rules Addendum

27. Any anomalous or surprising result must be root-caused against the actual code and data before being explained in a report. A plausible-sounding narrative must not be presented as a finding unless it has been checked against the specific implementation in use — if the explanation describes a limitation the actual architecture doesn't have (e.g. citing single-channel/no-reference limitations for a design that uses a true separate reference channel), it must be corrected, not repeated.
28. All required metrics for a phase (here: PESQ-WB, STOI, SI-SNR, ΔSI-SNR) must be visibly present for every method/category cell in the summary table, or explicitly marked as unavailable with a quantified, evidenced failure count — never silently omitted with no trace.
