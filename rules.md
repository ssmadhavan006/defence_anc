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
