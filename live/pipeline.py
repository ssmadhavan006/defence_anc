"""
live/pipeline.py — Real-time audio pipeline for Phase 5 live inference.

Architecture:
  sounddevice InputStream  (audio callback thread, highest priority)
      |
      | write()
      v
  RingBuffer (in_buf)          [pre-allocated, lock-free hot path]
      |
      | read()
      v
  InferenceThread              [daemon thread, runs enhance_chunk() loop]
      |
      | write()
      v
  RingBuffer (out_buf)
      |
      | read()
      v
  sounddevice OutputStream (playback callback thread, highest priority)

Operating modes (set via config or --mode CLI flag):
  "enhance"  — InferenceEngine.enhance_chunk() on every chunk
  "bypass"   — InferenceEngine.bypass_chunk() (pass-through, latency baseline)

Usage:
    # Enhance mode (default):
    python live/pipeline.py

    # Bypass mode (latency baseline):
    python live/pipeline.py --mode bypass

    # List audio devices:
    python live/pipeline.py --list-devices

    # Custom config:
    python live/pipeline.py --config config/audio_config.yaml --mode enhance

IMPORTANT: This script requires physical audio hardware.
Mode B tests (requiring hardware) must not be marked passed until real output
is pasted back from the Pi. (Rule 29)
"""

import os
import sys
import time
import argparse
import threading
import numpy as np

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path when run directly from live/ or repo root.
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import sounddevice as sd

from live.ring_buffer import RingBuffer
from live.inference_engine import InferenceEngine
from live.residual_filter import ResidualALEFilter


# ---------------------------------------------------------------------------
# Config loader (YAML via PyYAML, falls back to defaults if not installed)
# ---------------------------------------------------------------------------

def _load_config(config_path: str) -> dict:
    """
    Load audio_config.yaml. Falls back to hard-coded defaults if PyYAML is
    not available or the file is missing.
    """
    defaults = {
        "audio": {
            "sample_rate": 48000,
            "channels": 1,
            "chunk_duration_sec": 0.1,
            "ring_buffer_duration_sec": 2.0,
            "input_device": None,
            "output_device": None,
        },
        "model": {
            "atten_lim_db": 100.0,
            "output_gain": 1.0,
        },
        "pipeline": {
            "mode": "enhance",
            "log_timing": False,
            "latency_warn_sec": 0.30,
            "warmup_passes": 3,
            "priming_chunks": 1,
            "residual_filter": False,
            "inference_backend": "pytorch",
            "onnx_dir": "results/onnx",
        },
    }
    if not os.path.exists(config_path):
        print(
            f"[pipeline] Config not found at {config_path!r}, using defaults.",
            file=sys.stderr,
        )
        return defaults

    try:
        import yaml
        with open(config_path, "r") as f:
            loaded = yaml.safe_load(f)
        # Deep-merge loaded over defaults.
        for section, values in loaded.items():
            if section in defaults and isinstance(values, dict):
                defaults[section].update(values)
            else:
                defaults[section] = values
        return defaults
    except ImportError:
        print(
            "[pipeline] PyYAML not installed; using defaults. "
            "Install with: pip install pyyaml",
            file=sys.stderr,
        )
        return defaults
    except Exception as exc:
        print(
            f"[pipeline] Failed to parse {config_path!r}: {exc}. Using defaults.",
            file=sys.stderr,
        )
        return defaults


# ---------------------------------------------------------------------------
# Device resolver — prevents PortAudioError(-1) on Linux when device is None
# ---------------------------------------------------------------------------

def _auto_detect_device(kind="input"):
    """
    Find a plausible device via, in order:
      1. sd.default.device (PortAudio default, only if >= 0)
      2. First loopback/USB device found in query_devices()
      3. First any-channel device in query_devices()
      4. Known snd-aloop ALSA hw: strings (hw:2,0 for input / hw:2,1 for output)
    Never returns the string "default", which is not a valid ALSA device on
    many Pi configurations.
    """
    idx_pos = 0 if kind == "input" else 1
    try:
        def_dev = sd.default.device[idx_pos]
        if isinstance(def_dev, int) and def_dev >= 0:
            return def_dev
    except Exception:
        pass

    try:
        devs = sd.query_devices()
        if devs is not None and len(devs) > 0:
            chk_key = "max_input_channels" if kind == "input" else "max_output_channels"

            # Prefer loopback/USB/hw: named devices first
            for idx, d in enumerate(devs):
                if d.get(chk_key, 0) > 0:
                    name = d.get("name", "").lower()
                    if "loopback" in name or "hw:" in name or "usb" in name:
                        return idx

            # Fall back to any device with the right channel direction
            for idx, d in enumerate(devs):
                if d.get(chk_key, 0) > 0:
                    return idx
    except Exception:
        pass

    # query_devices() returned nothing (snd-aloop may not be loaded yet).
    # Try the known snd-aloop Loopback hw: strings directly — card 2
    # subdevice 0 handles input, subdevice 1 handles output on most Pi configs.
    return "hw:2,0" if kind == "input" else "hw:2,1"


def _resolve_device(dev_spec, kind="input"):
    """
    Resolve an audio device specifier for sounddevice.

    If dev_spec is an explicit int or str, VALIDATE it (query_devices) before
    trusting it -- a hardcoded config index goes stale the moment device
    enumeration order changes (reboot, USB re-plug, snd-aloop not yet loaded
    this boot). Falls through to _auto_detect_device() with a clear stderr
    warning rather than letting a raw PortAudioError crash the whole
    pipeline/stress-test/latency-test run on an otherwise-healthy machine.

    If dev_spec is None, resolves directly via _auto_detect_device().
    """
    if dev_spec is not None:
        try:
            sd.query_devices(dev_spec)
            return dev_spec
        except Exception as exc:
            print(
                f"[pipeline] WARNING: configured {kind}_device={dev_spec!r} is not valid "
                f"on this machine right now ({exc}). Falling back to auto-detection -- "
                f"run `python live/main.py detect` and update config/audio_config.yaml "
                f"with the current device index so this doesn't happen again.",
                file=sys.stderr,
            )
            return _auto_detect_device(kind)

    return _auto_detect_device(kind)


# ---------------------------------------------------------------------------
# LivePipeline
# ---------------------------------------------------------------------------

class LivePipeline:
    """
    Orchestrates the real-time audio stream: input -> ring buffer ->
    inference thread -> ring buffer -> output.

    Parameters
    ----------
    config : dict
        Parsed configuration dictionary (from audio_config.yaml).
    mode_override : str or None
        If set, overrides config["pipeline"]["mode"].
    """

    def __init__(self, config: dict, mode_override: str = None):
        audio_cfg = config["audio"]
        model_cfg = config["model"]
        pipe_cfg = config["pipeline"]

        self._sr = int(audio_cfg["sample_rate"])
        self._channels = int(audio_cfg["channels"])
        self._chunk_sec = float(audio_cfg["chunk_duration_sec"])
        self._chunk_samples = int(round(self._sr * self._chunk_sec))
        self._ring_cap = int(round(self._sr * float(audio_cfg["ring_buffer_duration_sec"])))
        self._in_device = audio_cfg.get("input_device", None)
        self._out_device = audio_cfg.get("output_device", None)

        self._atten_lim_db = float(model_cfg.get("atten_lim_db", 100.0))
        self._output_gain = float(model_cfg.get("output_gain", 1.0))
        self._warmup_passes = int(pipe_cfg.get("warmup_passes", 3))
        self._priming_chunks = int(pipe_cfg.get("priming_chunks", 1))
        self._residual_filter_enabled = bool(pipe_cfg.get("residual_filter", False))
        self._inference_backend = str(pipe_cfg.get("inference_backend", "pytorch"))
        self._onnx_dir = str(pipe_cfg.get("onnx_dir", "results/onnx"))
        self._log_timing = bool(pipe_cfg.get("log_timing", False))
        self._latency_warn_sec = float(pipe_cfg.get("latency_warn_sec", 0.30))
        self._mode = (mode_override or pipe_cfg.get("mode", "enhance")).strip().lower()

        if self._mode not in ("enhance", "bypass"):
            raise ValueError(f"Unknown mode {self._mode!r}. Use 'enhance' or 'bypass'.")

        self._in_buf = RingBuffer(self._ring_cap, channels=self._channels)
        self._out_buf = RingBuffer(self._ring_cap, channels=self._channels)

        self._running = threading.Event()
        self._inference_thread = None
        self._stream_in = None
        self._stream_out = None
        self._engine = None
        # Instantiated in start() only when residual_filter is enabled (skips
        # the JIT warmup entirely when unused). See live/residual_filter.py
        # for why this runs in reference-free ALE mode, not the oracle-NLMS
        # baseline, and its honest limitations before treating it as a
        # validated quality improvement.
        self._residual_filter = None

        # Timing stats.
        self._chunk_latencies = []   # seconds, enhance/bypass call only

        # Output underruns are counted in TWO buckets, because they mean
        # different things and only one of them is a real failure:
        #   _dropped_chunks     -- starved while _running was set. A genuine
        #                          real-time miss; this is what PASS/FAIL gates on.
        #   _teardown_underruns -- starved after stop() cleared _running. The
        #                          inference thread has already exited but the
        #                          output stream keeps calling back until it is
        #                          stopped, so it necessarily drains to empty.
        #                          Expected shutdown behaviour, NOT a failure.
        # Conflating these made every stress run report >=1 dropout and FAIL
        # regardless of real-time health (observed 2026-08-24: 0 underruns at
        # every 10 s checkpoint, final count 1).
        self._dropped_chunks = 0
        self._teardown_underruns = 0

        # Last processed chunk, exposed for visual demos (e.g. demo/spectrogram.py).
        # Benign read/write race with the inference thread is acceptable here —
        # these are for display only, never used for audio-path decisions.
        self.last_in_chunk = None    # mono float32, shape (chunk_samples,)
        self.last_out_chunk = None   # mono float32, shape (chunk_samples,)

    # ------------------------------------------------------------------
    # Audio callbacks (called from sounddevice's internal C thread)
    # ------------------------------------------------------------------

    def _input_callback(self, indata, frames, time_info, status):
        """Receive audio from the microphone and push to input ring buffer."""
        if status:
            print(f"[pipeline] Input status: {status}", file=sys.stderr)
        # indata shape: (frames, channels), float32
        self._in_buf.write(indata.copy())

    def _output_callback(self, outdata, frames, time_info, status):
        """Pull enhanced audio from output ring buffer and send to speakers."""
        if status:
            print(f"[pipeline] Output status: {status}", file=sys.stderr)
        # REVERTED 2026-08-24: tried timeout=0.0 here on the theory that this
        # blocking wait_for() stalls the real-time audio thread and causes
        # the driver-level "input overflow" xruns seen at 50ms chunks.
        # Falsified on Pi: with the wait removed, ALSA "output underflow"
        # events dropped to zero (the driver itself was never actually
        # starved) but our own dropped-chunk count nearly QUADRUPLED
        # (170ish -> 722/60s) because the ring buffer gave up on ordinary
        # inference-thread scheduling jitter instead of waiting the ~1-24ms
        # it needed. Meanwhile "input overflow" fired at an unchanged rate
        # with or without this wait -- proving it's an independent,
        # unrelated issue (most likely snd-aloop period-size negotiation at
        # 50ms specifically; 100ms and 20ms don't exhibit it). The blocking
        # wait is retained: it functions as a legitimate short grace period
        # for the inference thread, not a real-time violation in practice
        # (RTF stays well under 1 in all tested configs).
        chunk = self._out_buf.read(frames, timeout=self._chunk_sec * 2)
        if chunk is None:
            # Buffer underrun — output silence to avoid glitches.
            outdata[:] = 0.0
            if self._running.is_set():
                self._dropped_chunks += 1
            else:
                # Post-stop() drain: the inference thread is already gone, so
                # an empty buffer here is expected, not a real-time miss.
                self._teardown_underruns += 1
        else:
            # Apply output gain and write to device buffer.
            outdata[:] = chunk * self._output_gain

    # ------------------------------------------------------------------
    # Inference thread
    # ------------------------------------------------------------------

    def _inference_loop(self):
        """
        Consumer thread: read chunks from in_buf, enhance, write to out_buf.
        Runs until self._running is cleared.
        """
        print(
            f"[pipeline] Inference thread started (mode={self._mode}, "
            f"chunk={self._chunk_samples} samples / {self._chunk_sec*1000:.0f} ms).",
            file=sys.stderr,
        )

        while self._running.is_set():
            chunk = self._in_buf.read(self._chunk_samples, timeout=self._chunk_sec * 2)
            if chunk is None:
                # Timeout waiting for input — loop and retry.
                continue

            # chunk shape: (chunk_samples, channels)
            # InferenceEngine expects (n_samples,) or (1, n_samples) mono.
            mono = chunk[:, 0]   # Take channel 0; DeepFilterNet is single-channel.
            self.last_in_chunk = mono

            t0 = time.perf_counter()
            if self._mode == "enhance":
                enhanced = self._engine.enhance_chunk(mono)
            else:
                enhanced = self._engine.bypass_chunk(mono)
            elapsed = time.perf_counter() - t0
            self._chunk_latencies.append(elapsed)

            if self._log_timing or elapsed > self._latency_warn_sec:
                audio_dur = self._chunk_samples / self._sr
                rtf = elapsed / audio_dur
                level = "WARN" if elapsed > self._latency_warn_sec else "INFO"
                print(
                    f"[pipeline] [{level}] chunk: {elapsed*1000:.2f} ms "
                    f"(audio={audio_dur*1000:.0f} ms, RTF={rtf:.4f})",
                    file=sys.stderr,
                )

            # enhanced shape: (1, n_out) — write back as (n_out, 1) for ring buffer.
            out_mono = enhanced[0]   # shape (n_out,)
            # Trim or pad to chunk_samples to keep buffers aligned.
            if len(out_mono) >= self._chunk_samples:
                out_mono = out_mono[:self._chunk_samples]
            else:
                out_mono = np.pad(out_mono, (0, self._chunk_samples - len(out_mono)))

            # P1-1 residual stage: runs on DeepFilterNet's output, not bypass
            # pass-through (there's no model residual to clean up there).
            if self._mode == "enhance" and self._residual_filter is not None:
                out_mono = self._residual_filter.process_chunk(out_mono)

            self.last_out_chunk = out_mono
            self._out_buf.write(out_mono[:, np.newaxis])

        print("[pipeline] Inference thread exiting.", file=sys.stderr)

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    def start(self):
        """Load model, open streams, start inference thread."""
        print(f"[pipeline] Loading InferenceEngine (mode={self._mode})...", file=sys.stderr)
        self._engine = InferenceEngine(
            sample_rate=self._sr,
            atten_lim_db=self._atten_lim_db,
            warmup_passes=self._warmup_passes,
            log_timing=self._log_timing,
            backend=self._inference_backend,
            onnx_dir=self._onnx_dir if self._inference_backend == "onnx" else None,
        )

        if self._residual_filter_enabled:
            print("[pipeline] Residual filter (P1-1, reference-free ALE) ENABLED.", file=sys.stderr)
            self._residual_filter = ResidualALEFilter()

        self._running.set()
        self._inference_thread = threading.Thread(
            target=self._inference_loop, daemon=True, name="InferenceThread"
        )
        self._inference_thread.start()

        # Resolve devices — prevents PortAudioError(-1) when config is null
        in_dev = _resolve_device(self._in_device, kind="input")
        out_dev = _resolve_device(self._out_device, kind="output")
        print(
            f"[pipeline] Opening streams "
            f"(input_device={in_dev!r}, output_device={out_dev!r})...",
            file=sys.stderr,
        )

        # Open input stream.
        self._stream_in = sd.InputStream(
            samplerate=self._sr,
            blocksize=self._chunk_samples,
            device=in_dev,
            channels=self._channels,
            dtype="float32",
            callback=self._input_callback,
            latency="low",
        )
        # Open output stream.
        self._stream_out = sd.OutputStream(
            samplerate=self._sr,
            blocksize=self._chunk_samples,
            device=out_dev,
            channels=self._channels,
            dtype="float32",
            callback=self._output_callback,
            latency="low",
        )

        self._stream_in.start()
        self._stream_out.start()

        # Prime the output buffer with silence chunks so the output callback
        # doesn't underrun before inference produces the first real output.
        # This is a FIFO -- every primed chunk is permanent standing latency
        # (priming_chunks * chunk_duration_sec), not a one-time warmup cost.
        # Keep this as small as the measured inference jitter allows; verify
        # with stress_test.py after any change (0 dropouts required).
        silence = np.zeros((self._chunk_samples, self._channels), dtype=np.float32)
        for _ in range(self._priming_chunks):
            self._out_buf.write(silence)

        print(
            f"[pipeline] Streaming (SR={self._sr} Hz, chunk={self._chunk_samples} smp, "
            f"mode={self._mode}). Press Ctrl-C to stop.",
            file=sys.stderr,
        )

    def stop(self):
        """Gracefully shut down streams and inference thread."""
        print("[pipeline] Stopping...", file=sys.stderr)
        self._running.clear()

        if self._stream_in is not None:
            self._stream_in.stop()
            self._stream_in.close()

        if self._stream_out is not None:
            self._stream_out.stop()
            self._stream_out.close()

        if self._inference_thread is not None:
            self._inference_thread.join(timeout=3.0)

        self._print_stats()

    def _print_stats(self):
        if not self._chunk_latencies:
            return
        lats = np.array(self._chunk_latencies) * 1000.0   # ms
        audio_dur_ms = self._chunk_sec * 1000.0
        rtfs = lats / audio_dur_ms
        print(
            f"\n[pipeline] === Session stats ({len(lats)} chunks) ===\n"
            f"  Latency: median={np.median(lats):.2f} ms, "
            f"p95={np.percentile(lats, 95):.2f} ms, "
            f"max={np.max(lats):.2f} ms\n"
            f"  RTF:     median={np.median(rtfs):.4f}, "
            f"p95={np.percentile(rtfs, 95):.4f}\n"
            f"  Input buffer overflows: {self._in_buf.overflow_count}\n"
            f"  Output buffer underruns: {self._dropped_chunks}"
            f"  (+{self._teardown_underruns} during shutdown drain, not a failure)",
            file=sys.stderr,
        )

    def run_blocking(self):
        """Start the pipeline and block until Ctrl-C / SIGTERM."""
        self.start()
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _list_devices():
    print(sd.query_devices())


def _main():
    parser = argparse.ArgumentParser(
        description="PS26052 Phase 5 — Real-time noise suppression pipeline"
    )
    parser.add_argument(
        "--config",
        default="config/audio_config.yaml",
        help="Path to audio_config.yaml (default: config/audio_config.yaml)",
    )
    parser.add_argument(
        "--mode",
        choices=["enhance", "bypass"],
        default=None,
        help="Override pipeline mode: 'enhance' (default) or 'bypass'",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="Print available audio devices and exit",
    )
    parser.add_argument(
        "--log-timing",
        action="store_true",
        help="Log per-chunk inference timing to stderr",
    )
    args = parser.parse_args()

    if args.list_devices:
        _list_devices()
        return

    config = _load_config(args.config)
    if args.log_timing:
        config["pipeline"]["log_timing"] = True

    pipeline = LivePipeline(config, mode_override=args.mode)
    pipeline.run_blocking()


if __name__ == "__main__":
    _main()
