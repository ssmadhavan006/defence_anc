#!/usr/bin/env bash
#
# demo/run_judged_demo.sh — Phase 5.2: one-command judged-demo launcher.
#
# IMPORTANT ARCHITECTURAL NOTE, read before editing this script:
#   demo/dashboard.py, demo/spectrogram.py, and demo/webdash/app.py EACH
#   independently construct their own live.pipeline.LivePipeline and call
#   pipeline.start() -- each one opens its own real sd.InputStream /
#   sd.OutputStream against the physical audio hardware. They CANNOT run
#   simultaneously as separate processes against the same devices (ALSA
#   hw: devices, which this project targets, do not allow more than one
#   exclusive open). "One command starts everything ... dashboard, web
#   server, ... spectrogram, pipeline" (prototype.md 5.2) is therefore
#   honoured here as: run preflight checks, refresh the QR code (one-shot,
#   no hardware conflict), then launch exactly ONE UI process that owns the
#   live pipeline -- default the web dashboard, since it is the
#   judge-interactive one with phone/QR access (WOW #2). --ui lets the
#   presenter pick dashboard or spectrogram instead for a given run.
#   This is a corrected, truthful version of the plan's literal wording,
#   not a shortcut -- launching all four as real parallel processes would
#   fail with a device-busy error the moment two of them opened the mic,
#   which is exactly the kind of demo-day failure Phase 5 exists to
#   prevent (Rule 27: a plausible-sounding plan must be checked against
#   the actual implementation, not built as if it already matched).
#
# Idempotent: safe to re-run. Detects and cleanly stops a previous run
# (via its PID file) before starting a new one, rather than erroring out
# or leaving two processes fighting over the same audio device.
#
# Usage:
#   demo/run_judged_demo.sh                          # webdash (default), auto-detect LAN IP
#   demo/run_judged_demo.sh --ui dashboard            # terminal dashboard instead
#   demo/run_judged_demo.sh --ui spectrogram          # terminal spectrogram instead
#   demo/run_judged_demo.sh --backup demo/backup_audio/backup_60s.wav
#   demo/run_judged_demo.sh --ip 192.168.1.42 --port 8080
#   demo/run_judged_demo.sh --auto-restart            # wrap the UI process in a
#                                                        while-loop restarter (5.3a)
#   demo/run_judged_demo.sh --skip-preflight          # for a fast dry run only
#   demo/run_judged_demo.sh --stop                    # stop a running demo session
#
# NOTE: the "cold Pi boot to full demo in under 60s" timing claim in
# prototype.md 5.2 has NOT been measured -- that is Mode B (Rule 29). This
# script's logic (idempotency, cleanup, argument handling, the auto-restart
# loop, and a real webdash launch/failure/cleanup cycle) HAS been exercised
# on the dev machine (Windows, Git Bash) -- see progress.md for the pasted
# evidence. Wall-clock cold-boot timing on a real Pi has not.
#
# PYTHON env var: set this to the venv's python if `python` on PATH isn't
# it (e.g. PYTHON=.venv/bin/python on the Pi, or the venv is simply not
# activated in the shell running this script) -- discovered during dev-side
# testing: a bare `python` with no active venv fails on `import sounddevice`
# well before reaching any of the actual checks this script is verifying.

set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

RUN_DIR="${REPO_ROOT}/.demo_run"
PID_FILE="${RUN_DIR}/ui.pid"
# Tracks THIS script's own PID (the auto-restart while-loop's supervisor),
# separate from PID_FILE (the current UI child process). Needed because a
# --stop issued during the 2s cooldown BETWEEN restarts finds no live child
# in PID_FILE (it already exited and was cleaned up) -- without this, --stop
# would silently no-op and the supervisor loop would just keep restarting.
# Found and fixed during dev-side testing of --auto-restart (see progress.md).
SUPERVISOR_PID_FILE="${RUN_DIR}/supervisor.pid"
LOG_FILE="${RUN_DIR}/ui.log"
QR_OUT="${REPO_ROOT}/qr_dashboard.png"

UI="webdash"
IP=""
PORT="8080"
BACKUP=""
AUTO_RESTART=0
SKIP_PREFLIGHT=0
STOP_ONLY=0
PY="${PYTHON:-python}"

while [ $# -gt 0 ]; do
  case "$1" in
    --ui) UI="$2"; shift 2 ;;
    --ip) IP="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --backup) BACKUP="$2"; shift 2 ;;
    --auto-restart) AUTO_RESTART=1; shift ;;
    --skip-preflight) SKIP_PREFLIGHT=1; shift ;;
    --stop) STOP_ONLY=1; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^#//'
      exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1 ;;
  esac
done

mkdir -p "$RUN_DIR"

# ---------------------------------------------------------------------------
# Idempotency: stop any previous run before doing anything else. A stale
# PID file (process already dead) is cleaned up silently; a live previous
# process is stopped so the new run doesn't fight it for the audio device.
# ---------------------------------------------------------------------------
_kill_wait() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null || return 0
  kill "$pid" 2>/dev/null
  for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.2
  done
  kill -9 "$pid" 2>/dev/null
}

stop_previous() {
  if [ -f "$PID_FILE" ]; then
    local old_pid
    old_pid="$(cat "$PID_FILE" 2>/dev/null)"
    if [ -n "$old_pid" ]; then
      echo "[run_judged_demo] Stopping previous UI process (pid=$old_pid)..."
      _kill_wait "$old_pid"
    fi
    rm -f "$PID_FILE"
  fi
  if [ -f "$SUPERVISOR_PID_FILE" ]; then
    local old_super
    old_super="$(cat "$SUPERVISOR_PID_FILE" 2>/dev/null)"
    # Never kill ourselves -- this function also runs at the top of a fresh
    # invocation, whose own $$ could in principle already be in the file
    # from a prior crashed run that never cleaned up.
    if [ -n "$old_super" ] && [ "$old_super" != "$$" ] && kill -0 "$old_super" 2>/dev/null; then
      echo "[run_judged_demo] Stopping previous auto-restart supervisor (pid=$old_super)..."
      _kill_wait "$old_super"
    fi
    rm -f "$SUPERVISOR_PID_FILE"
  fi
}

stop_previous

if [ "$STOP_ONLY" -eq 1 ]; then
  echo "[run_judged_demo] Stopped. Nothing else requested (--stop)."
  exit 0
fi

echo "$$" > "$SUPERVISOR_PID_FILE"

# Clean up on exit/interrupt so Ctrl-C during a demo doesn't leave an
# orphaned process holding the audio device hostage for the next run.
cleanup() {
  stop_previous
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# 1. Preflight check (Phase 5.3c) -- gate the whole launch on it.
# ---------------------------------------------------------------------------
if [ "$SKIP_PREFLIGHT" -eq 0 ]; then
  echo "[run_judged_demo] Running preflight check..."
  if ! "$PY" scripts/preflight_check.py; then
    echo "[run_judged_demo] Preflight check FAILED — aborting. Fix the FAIL item(s) above, or pass --skip-preflight for a dry run only." >&2
    exit 1
  fi
else
  echo "[run_judged_demo] --skip-preflight set; NOT gating on device/model checks. Do not use this for the actual judged run."
fi

# ---------------------------------------------------------------------------
# 2. QR code (one-shot, no hardware conflict — safe to always refresh).
#    Only meaningful for --ui webdash, but harmless to generate regardless
#    (the presenter may switch --ui mid-rehearsal).
# ---------------------------------------------------------------------------
if [ -z "$IP" ]; then
  if command -v hostname >/dev/null 2>&1 && hostname -I >/dev/null 2>&1; then
    IP="$(hostname -I | awk '{print $1}')"
  fi
fi
if [ -n "$IP" ]; then
  echo "[run_judged_demo] Generating QR code for http://${IP}:${PORT} ..."
  if "$PY" demo/webdash/generate_qr.py --ip "$IP" --port "$PORT" --out "$QR_OUT"; then
    echo "[run_judged_demo] QR code -> ${QR_OUT}"
    if command -v xdg-open >/dev/null 2>&1 && [ -n "${DISPLAY:-}" ]; then
      xdg-open "$QR_OUT" >/dev/null 2>&1 &
    else
      echo "[run_judged_demo] No GUI image viewer detected — show ${QR_OUT} manually, "
      echo "                  or print it: http://${IP}:${PORT}"
    fi
  else
    echo "[run_judged_demo] QR generation skipped (qrcode not installed? see requirements-optional.txt) — continuing without it."
  fi
else
  echo "[run_judged_demo] Could not auto-detect a LAN IP — pass --ip explicitly for the QR code. Continuing without it."
fi

# ---------------------------------------------------------------------------
# 3. Launch exactly one UI process — the one that owns the live pipeline.
# ---------------------------------------------------------------------------
BACKUP_ARGS=()
if [ -n "$BACKUP" ]; then
  BACKUP_ARGS=(--backup "$BACKUP")
  echo "[run_judged_demo] Backup audio mode requested: ${BACKUP}"
fi

case "$UI" in
  webdash)
    CMD=("$PY" demo/webdash/app.py --host 0.0.0.0 --port "$PORT" "${BACKUP_ARGS[@]}")
    ;;
  dashboard)
    if [ -n "$BACKUP" ]; then
      echo "[run_judged_demo] WARNING: --ui dashboard does not (yet) accept --backup; ignoring it." >&2
    fi
    CMD=("$PY" demo/dashboard.py)
    ;;
  spectrogram)
    if [ -n "$BACKUP" ]; then
      echo "[run_judged_demo] WARNING: --ui spectrogram does not (yet) accept --backup; ignoring it." >&2
    fi
    CMD=("$PY" demo/spectrogram.py)
    ;;
  pipeline)
    CMD=("$PY" live/main.py pipeline "${BACKUP_ARGS[@]}")
    ;;
  *)
    echo "Unknown --ui '$UI' (expected: webdash | dashboard | spectrogram | pipeline)" >&2
    exit 1 ;;
esac

echo "[run_judged_demo] Launching UI: ${CMD[*]}"

run_once() {
  "${CMD[@]}" >>"$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  wait "$(cat "$PID_FILE")"
}

if [ "$AUTO_RESTART" -eq 1 ]; then
  # Phase 5.3(a) — portable auto-restart wrapper (the "while true; do ... ;
  # done" alternative to a systemd unit; see demo/ps26052-demo.service for
  # the systemd version). 2s cooldown between restarts, matching the plan.
  echo "[run_judged_demo] Auto-restart ENABLED (2s cooldown on crash). Ctrl-C to stop for real."
  trap 'stop_previous; exit 0' INT TERM
  while true; do
    run_once
    code=$?
    if [ -f "$PID_FILE" ]; then rm -f "$PID_FILE"; fi
    echo "[run_judged_demo] UI process exited (code=$code). Restarting in 2s... (see $LOG_FILE)"
    # Backgrounded + waited (not a plain foreground `sleep 2`) so SIGINT/TERM
    # interrupts the cooldown immediately instead of waiting for it to
    # finish -- a plain foreground sleep as a bash script's direct child can
    # delay trap delivery until the sleep itself returns, most reliably
    # observed on Windows/MSYS2's signal emulation layer during dev-side
    # testing (see progress.md), but this pattern is the more portable one
    # regardless of platform.
    sleep 2 &
    wait $!
  done
else
  run_once
fi
