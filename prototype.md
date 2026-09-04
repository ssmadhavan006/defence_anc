PS26052 — Development Draft: Current → 60–80% Complete

Internal Hackathon Sprint Plan
From verified working prototype to award-winning submission

Where we start vs. where we need to land

Current state (verified): Pi 5 hardware pipeline running, real mic + headset, DFN3 at RTF 0.29–0.40, offline eval 1500/1500 valid, 1 of 3 PESQ targets pass, terminal dashboard + spectrogram demo working, ~172 ms end-to-end latency.

60–80% target: Every explicit PS26052 requirement demonstrated (including dual-mic), real-time latency under 150 ms, most numeric targets met, live judged demo bulletproof, and three genuine wow-factor differentiators that competitors won't have. Fine-tuning-from-scratch (needing the Rust libdfdata + HDF5 pipeline) stays out of scope — it's the last 20–40% by design.

Guiding principle: we already have real, evidenced results. Every phase below validates or extends what exists rather than rebuilding. No phase depends on any external service or approval we don't already have. All work is Pi-hardware-testable end-to-end.

Phase 1 — Dual-Channel Hardware & Software Foundation

Duration: 2 days · Cost: ~₹3,500 · Blocking: buy hardware first

Objective

Bring the system from single-mic to primary + reference microphone, the one PS-explicit requirement not currently met. This alone lifts the pitch from "single-channel enhancement" to "true adaptive noise cancellation" — a categorically different technical claim.

1.1 Hardware acquisition
2-in USB audio interface (Behringer UMC202HD ~₹8,000 or generic USB-C 2-in adapter ~₹2,000)
Second electret/lavalier mic ~₹800–1,500
Active cooler for Pi 5 ~₹600
Spare 64 GB microSD card pre-flashed with deploy zip ~₹500
1.2 Software work

File-level changes:

config/audio_config.yaml: extend audio section with reference_input_device, reference_channels; document that primary and reference can live on different ALSA cards.
live/pipeline.py: add second sd.InputStream for reference mic, second ring buffer (_ref_buf), pass reference chunks alongside primary into the inference thread.
live/reference_ale.py (new): reference-based NLMS/LMS stage — real second-channel version of what live/residual_filter.py currently does reference-free. Sample-aligned adaptive filter with numba JIT, matching the offline baselines/nlms/nlms.py algorithm but streaming and chunk-continuous.
live/pipeline.py: route DFN3 output → reference_ale.process_chunk(dfn_output, reference_chunk) when pipeline.reference_ale: true.
Physical calibration script scripts/calibrate_mic_pair.py (new): measures per-mic latency offset and gain difference, writes to config so the reference channel is time- and level-aligned before it hits the adaptive filter (mis-alignment kills NLMS performance — same lesson as the offline combo_seed alignment fix in Phase 4).
1.3 Validation
Bypass mode with dual-mic active: both streams captured cleanly, 0 dropouts for 60 s.
Enhance mode with reference ALE on: real crowd-babble test, verify AFTER panel in spectrogram shows meaningful improvement over single-mic mode.
Rerun 10-min stress test with both inputs active, both modes, log to results/stress_dualmic.json.
✅ Phase 1 Deliverables Checklist
 2-in USB audio interface + second mic physically connected and enumerated on Pi
 config/audio_config.yaml supports dual-mic; documented in file
 live/pipeline.py runs two InputStreams in parallel, no dropouts
 live/reference_ale.py self-test PASS (bit-exact against offline NLMS reference implementation)
 scripts/calibrate_mic_pair.py runs and writes calibration into config
 10-min dual-mic stress test PASS on Pi (0 dropouts, results JSON committed)
 Demo spectrogram shows visibly stronger crowd-babble suppression vs. single-mic
 progress.md entry with pasted evidence
 README updated: system now described as "true dual-channel adaptive noise cancellation"
Phase 2 — Latency Engineering & Real-Time Grade

Duration: 1.5 days · No hardware dependency

Objective

Bring end-to-end latency under 150 ms (ITU-T G.114 interactive-voice threshold), from the current ~172 ms. This turns "real-time" from a hedged claim into a defensible number against any evaluator's stopwatch.

2.1 Chunk-size sweep in dual-mic configuration
Rerun scripts/sweep_chunk_size.py with dual-mic active — the added ALE stage changes the RTF budget, and 50 ms may now be viable or may not.
Selection rule: smallest chunk that holds 0 dropouts over 5 minutes at p95 RTF < 0.7.
2.2 Priming minimization
Current pipeline.priming_chunks: 1 — can this become 0 with a "cold-start silence tolerance" first-chunk policy? Prototype and test.
2.3 Compiled hot path
Convert _output_callback and _input_callback inner logic to numba.njit where numpy overhead is measurable.
Profile inference thread scheduling jitter with perf or py-spy on Pi; pin InferenceThread to a dedicated core via os.sched_setaffinity to eliminate cross-core scheduling latency (Pi 5 has 4 cores, use 2 for audio callbacks, 2 for inference).
2.4 Physical mic-to-headset round-trip
Build scripts/measure_acoustic_latency.py (new): plays a click through headset, records via mic at close range, cross-correlates. First-ever true mouth-to-ear number in this project. Report median + p95 over 20 reps.
✅ Phase 2 Deliverables Checklist
 End-to-end latency confirmed < 150 ms on Pi with dual-mic + full stack, JSON committed
 Physical acoustic round-trip number measured and logged (first in the project)
 Inference thread pinned to dedicated core, verified via taskset/chrt
 Chunk-size sweep rerun with dual-mic; new final config committed with rationale
 10-min stress test at new optimal chunk size PASS
 All latency claims in README/architecture.md updated to real measured numbers
 progress.md entry
Phase 3 — Quality Validation: Activate What's Built

Duration: 2 days · No hardware dependency

Objective

Turn "code exists" into "measured PESQ/STOI improvement" for the two dormant features (data augmentation + residual filter). Also close the offline eval loop for dual-mic. These are cheap wins that convert already-written code into cited results.

3.1 Run the augmented eval
python data/mix_dataset.py --output-dir data/mixtures_augmented --manifest data/manifest_augmented.csv --augment-rir --augment-clipping
Run all baselines + DFN3 through the augmented set
Run eval/run_eval.py --manifest data/manifest_augmented.csv --results results/results_augmented.csv
Compare deltas to clean-condition baseline in a new docs/augmentation_robustness.md
3.2 A/B validate reference ALE (dual-mic offline)
Adapt eval harness to score dual-mic pipeline output on the crowd-babble subset (where classical NLMS already outperformed DFN3 alone, per docs/non_stationary_root_cause.md).
Report: does DFN3 + reference-ALE beat DFN3-alone on crowd babble? Expected yes based on the offline NLMS numbers.
3.3 Post-processing quality tricks (no retraining)

Quick, high-leverage tweaks that shift PESQ without model surgery:

atten_lim_db sweep per noise category (currently fixed at 100): probably we're over-suppressing stationary noise (PESQ 2.48 = so close). Sweep 30–100 dB per category, pick the per-category optimum, store as model.atten_lim_db_by_category.
Post-DFN spectral tilt correction: 1-tap high-shelf EQ to restore consonant energy DFN3 slightly over-suppresses. 3 lines of numpy, measurable STOI/PESQ gain.
Optional pre-emphasis before DFN3, de-emphasis after — standard trick, often lifts PESQ 0.05–0.15.
3.4 Consolidated compliance rerun
Regenerate results/final/target_compliance.md/.json with all above changes applied.
Realistic target: 2 of 3 categories fully PASS on all three metrics, third category (non-stationary) passes SI-SNR and STOI with disclosed PESQ gap → 8/9 metric cells green vs. current 5/9.
✅ Phase 3 Deliverables Checklist
 results/results_augmented.csv committed, 1500 rows
 docs/augmentation_robustness.md shows quantified robustness deltas
 results/results_dualmic_crowd.csv — dual-mic vs single-mic crowd babble comparison
 atten_lim_db per-category tuning applied, new eval numbers committed
 Spectral tilt / pre-emphasis experiments logged (kept if helpful, dropped honestly if not — no cherry-picking)
 Fresh results/final/target_compliance.md reflecting all improvements
 Headline story updated: "2 of 3 categories fully compliant, 3rd category compliant on 2 of 3 metrics"
Phase 4 — WOW FACTORS: Three Differentiators

Duration: 3 days · This is what wins the hackathon

Objective

Every other team will show noise coming in one side of a headset and clean speech coming out the other. We show three things they don't have, each addressing a real gap between "AI project" and "deployable defence system."

🔥 WOW #1 — On-Device Noise Classifier + Adaptive Attenuation Router

The idea: Real-time detection of noise category (stationary / non-stationary / impulsive) using a lightweight classifier that runs in parallel with DFN3, and dynamically routes attenuation strength and residual-stage engagement based on what noise the operator is currently in.

Why it matters: Every other team runs one model with one setting. We show situational awareness — the system knows it's now in a helicopter vs. under gunfire and adjusts. This is genuine defence-context intelligence.

Implementation:

models/noise_classifier/ (new): small MobileNet-style classifier (~50 KB) trained on our own 300-mixture manifest (labels already exist as category column). 3-class softmax head. Train on dev machine in <5 min.
Runs every 500 ms in a background thread (not per-chunk — no RTF impact).
Feeds decision to LivePipeline._policy_router which sets atten_lim_db and toggles reference ALE.
Demo hook: current detected noise category displayed live on demo/dashboard.py — judges see "STATIONARY (engine)" flip to "IMPULSIVE (gunshot detected 12:34:56)" as they play different sounds.
Bonus: log every impulsive event with timestamp → doubles as acoustic shot-detection, an actual defence capability worth naming.
🔥 WOW #2 — Live Web Dashboard via QR Code

The idea: Judge scans a QR code taped to the Pi. Their phone browser opens a live dashboard showing: current noise category, input/output SNR estimate, RTF, dropout count, temperature, DNSMOS quality score, session waveform, and a big BYPASS/ENHANCE toggle the judge can press themselves from their phone.

Why it matters: Memorable, interactive, hands-on. Judges rate what they touched more than what they watched. Also demonstrates cloud-manageable edge deployment — the exact story for defence fleet ops.

Implementation:

demo/webdash/ (new): FastAPI + a single static HTML page with WebSocket. FastAPI already in Python-optional; add to requirements-optional.txt.
Pi runs a tiny local HTTP server on port 8080; QR code encodes http://<pi-lan-ip>:8080.
WebSocket pushes 4 Hz telemetry from LivePipeline (via the same last_in_chunk/last_out_chunk hooks that feed the terminal spectrogram — zero hot-path change).
Toggle button POSTs to /mode/{enhance|bypass}.
Waveform rendered client-side with <canvas>.
🔥 WOW #3 — On-Device Self-Quality Estimation (DNSMOS)

The idea: The system continuously rates its own output quality using a reference-free MOS estimator (DNSMOS P.808, from Microsoft's DNS Challenge). Judges see "Current output MOS: 4.2 / 5.0" live on screen. No other team will have this.

Why it matters: Turns a hackathon demo into a self-monitoring production system. Also gives the operator a live "trust indicator" — if MOS drops (e.g. novel noise the model wasn't trained on), the system honestly flags it rather than pretending to be OK. This is exactly the reliability engineering thinking mature defence deployments require.

Implementation:

models/dnsmos/ (new): DNSMOS is an ONNX model (~2 MB, publicly released by Microsoft, MIT license). Runs on 9-second windows at ~5 ms per inference on Pi 5.
Background thread, 0.5 Hz cadence, no hot-path impact.
Score exposed on terminal dashboard, spectrogram, and web dashboard.
Threshold-triggered warnings: if MOS < 2.5, log "output quality degraded" and (optionally) auto-switch to bypass with a UI notification.
✅ Phase 4 Deliverables Checklist
 models/noise_classifier/: trained model, classify_chunk.py, self-test PASS
 Noise category displayed live on all three demo UIs
 Impulsive event log (results/gunshot_events.jsonl) with timestamps demonstrated
 demo/webdash/: FastAPI service starts on Pi, QR code generation script
 Phone-browser demo verified over LAN (tested with Android + iOS)
 Bypass/enhance toggle from phone works
 models/dnsmos/: ONNX model downloaded (with citation to Microsoft DNS Challenge repo), self-test PASS
 Live MOS score visible on all three UIs
 MOS < 2.5 warning path tested (feed intentional garbage, verify warning fires)
 progress.md entry per WOW feature with pasted evidence
Phase 5 — Demo Bulletproofing & Pitch Integration

Duration: 1.5 days · Everything must survive Murphy's Law

Objective

Demo day fails in ways technical excellence can't fix. Latency spikes when the judge's laptop hotspot floods the WiFi. USB dongles enumerate as different indices after a reboot. Someone unplugs something. This phase makes those non-failures.

5.1 Backup demo mode
demo/backup_playback.py (new): 60-second pre-recorded noisy audio (real gunshot + engine mix + spoken command), plays through the pipeline instead of live mic. Single --backup flag on live/main.py. If demo mic fails, one command switch, judges still hear the difference.
5.2 Rehearsed demo script
demo/run_judged_demo.sh (new): one command starts everything in the right order — dashboard, web server, QR code display, spectrogram, pipeline. Idempotent, tested from cold Pi boot to full demo in under 60 s.
5.3 Failure-recovery hardening
Auto-restart if pipeline crashes mid-demo (systemd unit or while true; do ... ; done wrapper with 2 s cooldown).
Health check: if RTF > 0.9 for 5 s straight, log warning + auto-swap to bypass to avoid audible failure.
Pre-flight script: scripts/preflight_check.py — runs 30 s before demo, verifies all devices present, all models loaded, all self-tests green. Red/green terminal output.
5.4 Presentation deck (10–12 slides)

Aligned with the pitch document we drafted:

Title + team + PS26052
The problem (defence acoustics in 30 seconds)
Why classical DSP fails (with the NLMS −7 dB gunshot chart)
Our solution architecture (diagram)
Live demo (this slide = judges look up from screen)
Results table with target compliance matrix
Latency + real-time story (< 150 ms number)
WOW #1: noise classifier + shot detection
WOW #2: web dashboard + QR code
WOW #3: DNSMOS self-quality monitoring
Roadmap to 100% (dual-mic, fine-tuning, Jetson port)
Cost / commercialization / Atmanirbhar close
5.5 Backup demo video
3-min video recorded ahead of time showing the full working demo — insurance if live demo has any issue.
Second file: A/B before/after audio pair judges can listen to on headphones.
✅ Phase 5 Deliverables Checklist
 Backup playback mode works, tested from cold start
 demo/run_judged_demo.sh runs from cold Pi boot to full demo in < 60 s
 Auto-restart wrapper verified with an intentional crash
 scripts/preflight_check.py runs green on demo hardware
 10–12 slide presentation deck complete
 Backup demo video recorded, edited, on a USB stick + cloud backup
 Before/after audio A/B pair ready to hand to judges
 Full-run dress rehearsal completed by every team member at least once
 Second Pi (if procured) has identical setup, tested independently
Final Readiness Gate — Before Submission
🎯 Master Deliverables Checklist

Technical:

 Dual-microphone (primary + reference) hardware live, PS-explicit requirement met
 End-to-end latency < 150 ms, measured and documented
 Physical acoustic mouth-to-ear latency measured (first in project history)
 Data augmentation eval complete, robustness numbers documented
 Dual-mic crowd-babble improvement quantified vs single-mic
 atten_lim_db per-category tuned, PESQ improvements captured
 Target compliance matrix: at least 8/9 metric cells green (up from 5/9)
 Full pipeline runs 10 min zero-dropout on real dual-mic hardware
 All 9 self-tests green on dev machine, 7+ on Pi

WOW factors (differentiators):

 Real-time noise classifier operational, category displayed live
 Impulsive event log demonstrates shot-detection capability
 Web dashboard accessible via QR code from any phone
 Judge can toggle bypass/enhance from their phone
 DNSMOS live quality score visible on all demo UIs
 Auto-degraded-quality warning path verified

Demo:

 Backup playback mode works if live mic fails
 Backup demo video on USB + cloud
 Pre-flight check passes on demo hardware
 Cold-boot-to-demo takes < 60 s
 Full dress rehearsal completed

Documentation & pitch:

 README updated to reflect all improvements
 architecture.md component matrix updated
 progress.md current through demo day
 Compliance report regenerated with final numbers
 Presentation deck complete (10–12 slides)
 Before/after audio A/B pair prepared
 Full pitch document (the one we drafted earlier) reviewed and printed as leave-behind
Effort Summary
Phase	Duration	Hardware	Difficulty	Risk if skipped
1 · Dual-channel	2 days	₹3,500	Medium	PS-explicit requirement missed
2 · Latency	1.5 days	None	Medium	Real-time claim stays fragile
3 · Quality validation	2 days	None	Easy	Existing code stays uncredited
4 · WOW factors	3 days	None	Medium-High	Look like every other team
5 · Demo bulletproofing	1.5 days	None	Easy	Demo-day failure risk
Total	~10 days	~₹3,500		
Why this positions you to win

Most teams will show a noise-in / clean-out demo. Some will show numbers. We show all three of those PLUS:

A dual-mic true adaptive noise cancellation architecture (categorically stronger than "single-channel enhancement" — matches the PS wording exactly, most teams will over-promise on single-channel).
A real-time acoustic environment classifier that adapts behaviour (defence-context intelligence, not just enhancement).
A phone-accessible live control dashboard via QR (interactive, memorable, judges touch the system).
Self-monitored output quality (deployment-mature, not just research-code).
A ~₹15,000 BOM story that beats ₹80,000 imports 10× (Atmanirbhar close).
Documented engineering honesty — including caught-and-fixed real bugs, disclosed limitations, and superseded incorrect measurements — that reads as maturity to any evaluator with actual engineering experience.