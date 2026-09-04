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
from live.cpu_affinity import set_thread_affinity
# NOTE: live.fast_resample IS imported at module scope (unlike residual_filter
# / reference_nlms below) because it degrades gracefully on its own -- it is
# importable without numba (see its module docstring) and only raises if
# resample_fast() is actually CALLED without numba installed. That call path
# is guarded in start() so a disabled (default) pipeline.fast_resample never
# reaches it.
from live.fast_resample import resample_fast as _resample_fast_impl, _NUMBA_AVAILABLE as _FAST_RESAMPLE_NUMBA_AVAILABLE
# NOTE: live.residual_filter is imported LAZILY, inside start(), only when
# pipeline.residual_filter is actually enabled. It depends on numba, which is
# an OPTIONAL dependency (see requirements-optional.txt). Importing it at
# module scope made a default-OFF feature break the entire live pipeline on
# any machine without numba -- confirmed on the Pi 2026-08-24, where
# `python live/main.py stress` died with ModuleNotFoundError: No module named
# 'numba' despite residual_filter being set to false. A disabled feature must
# never be able to take down the core audio path.


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
            "priming_chunks": 1.0,
            "startup_grace_sec": 0.5,
            "cpu_affinity": None,
            "fast_resample": False,
            "residual_filter": False,
            "inference_backend": "pytorch",
            "onnx_dir": "results/onnx",
            "health_check": {
                "enabled": True,
                "rtf_threshold": 0.9,
                "sustained_sec": 5.0,
                "auto_bypass": True,
            },
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
        with open(config_path, "r", encoding="utf-8") as f:
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


def _resolve_stream_samplerate(device, requested_sr, channels, kind="input"):
    """
    Return the sample rate to actually open the given device's stream at.

    PortAudio's ALSA hostapi opens the device's raw "hw:" PCM directly (no
    software rate conversion), so it fails with PaInvalidSampleRate whenever
    a device's hardware doesn't natively support `requested_sr` -- e.g. a
    conferencing speakerphone fixed at 16 kHz, used alongside a headset mic
    that reports a 44.1 kHz default. `arecord -D plughw:...` doesn't hit
    this because ALSA's "plug" wrapper resamples in software; PortAudio's
    enumerated devices here are the raw (non-plug) PCMs, so this pipeline
    does the equivalent resampling itself instead (see _resample()).

    Uses sd.check_input/output_settings(), which validates against the
    driver without actually opening a stream.
    """
    check_fn = sd.check_input_settings if kind == "input" else sd.check_output_settings
    try:
        check_fn(device=device, samplerate=requested_sr, channels=channels, dtype="float32")
        return requested_sr
    except Exception as exc:
        try:
            native_sr = int(round(sd.query_devices(device)["default_samplerate"]))
        except Exception:
            # Query itself failed -- return the requested rate so the
            # subsequent sd.InputStream/OutputStream call raises the real,
            # actionable PortAudioError instead of failing silently here.
            return requested_sr
        print(
            f"[pipeline] {kind} device {device!r} does not support {requested_sr} Hz "
            f"directly ({exc}). Opening at its native {native_sr} Hz instead and "
            f"resampling {'up' if kind == 'input' else 'down'} to/from the "
            f"{requested_sr} Hz processing rate in software.",
            file=sys.stderr,
        )
        return native_sr


def _resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    """
    Lightweight linear-interpolation resampler, mono 1-D array in, 1-D out.

    No scipy dependency on purpose -- scipy is deliberately kept OUT of
    requirements.txt (see requirements-optional.txt: it previously made the
    whole install ResolutionImpossible on the Pi's numpy<2.0 pin). Only used
    on the live-mic/speaker I/O path when a device's hardware rate differs
    from the DeepFilterNet processing rate; the offline eval path
    (models/deepfilternet/run_inference.py, results/results.csv) never
    touches this.
    """
    if sr_from == sr_to or x.shape[0] == 0:
        return x
    n_out = int(round(x.shape[0] * sr_to / sr_from))
    if n_out <= 0:
        return np.zeros(0, dtype=x.dtype)
    src_idx = np.arange(x.shape[0])
    dst_idx = np.linspace(0, x.shape[0] - 1, num=n_out)
    return np.interp(dst_idx, src_idx, x).astype(x.dtype)


def _resample_multi(x: np.ndarray, sr_from: int, sr_to: int, use_fast: bool = False) -> np.ndarray:
    """_resample() (or the numba fast_resample, per D4) applied independently
    per channel. x shape (n, channels)."""
    if sr_from == sr_to or x.shape[0] == 0:
        return x
    resample_fn = _resample_fast_impl if use_fast else _resample
    return np.stack(
        [resample_fn(x[:, ch], sr_from, sr_to) for ch in range(x.shape[1])], axis=1
    )


def _compute_priming_samples(priming_chunks: float, chunk_samples: int) -> int:
    """
    Number of silence samples to pre-load into the output ring buffer at
    startup (Phase 2, D1). `priming_chunks` is a float number of chunk
    durations; `1.0` reproduces the pre-Phase-2 behaviour exactly (one whole
    chunk of silence), since round(1.0 * chunk_samples) == chunk_samples.
    """
    if priming_chunks < 0:
        raise ValueError(f"priming_chunks must be >= 0, got {priming_chunks}")
    return round(priming_chunks * chunk_samples)


def _classify_underrun(is_running: bool, since_start_sec, grace_sec: float) -> str:
    """
    Bucket a single output-callback underrun (Phase 2, D2).

    Returns one of "teardown" / "startup" / "real":
      - "teardown": the pipeline has already been stop()ped; the output
        stream outliving the inference thread is expected shutdown drain,
        not a failure.
      - "startup":  within `grace_sec` of stream start, while inference may
        not yet have produced its first chunk(s) at reduced priming. Cold
        start transient, excluded from the stress verdict but always
        reported.
      - "real": a genuine real-time miss. This is what PASS/FAIL gates on.

    `since_start_sec` is None only in the (untested-in-practice) case where
    the callback fires before start() has recorded a start time; treated as
    "still in the startup grace window" rather than crashing on None < float.
    """
    if not is_running:
        return "teardown"
    if since_start_sec is None or since_start_sec < grace_sec:
        return "startup"
    return "real"


def _check_rtf_health(rtf_window, threshold: float, sustained_sec: float) -> bool:
    """
    Phase 5.3(b): pure decision function for the RTF health check, kept
    independent of any threading/hardware so it's unit-testable exactly like
    _classify_underrun() above.

    rtf_window is an iterable of (timestamp_monotonic, rtf) pairs, oldest
    first, already trimmed to some recent horizon by the caller. Returns True
    (unhealthy -- should auto-bypass) only when EVERY sample in the window
    exceeds `threshold` AND the window actually spans >= sustained_sec of
    real time (not just >= sustained_sec worth of chunk *count*, which would
    trigger too early on a slow chunk rate and too late on a fast one).

    An empty or single-sample window is never considered unhealthy -- there
    is no way to know a threshold has been *sustained* from one sample.
    """
    window = list(rtf_window)
    if len(window) < 2:
        return False
    span_sec = window[-1][0] - window[0][0]
    if span_sec < sustained_sec:
        return False
    return all(rtf > threshold for _, rtf in window)


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
    backup_audio_path : str or None
        Phase 5.1. If set, the primary microphone's sd.InputStream is never
        opened -- audio comes from this WAV file instead, fed at real-time
        cadence via demo.backup_playback.BackupAudioSource. The output
        stream (real speakers/headset) is unaffected, so a demo can recover
        from a dead mic with this one flag while judges still hear the real
        pipeline. Dual-mic reference capture is also skipped in this mode
        (there is no live reference either) -- see start().
    """

    def __init__(self, config: dict, mode_override: str = None, backup_audio_path: str = None):
        audio_cfg = config["audio"]
        model_cfg = config["model"]
        pipe_cfg = config["pipeline"]

        self._backup_audio_path = backup_audio_path or audio_cfg.get("backup_playback_path", None)
        self._backup_source = None
        self._backup_thread = None

        self._sr = int(audio_cfg["sample_rate"])
        self._channels = int(audio_cfg["channels"])
        self._chunk_sec = float(audio_cfg["chunk_duration_sec"])
        self._chunk_samples = int(round(self._sr * self._chunk_sec))
        self._ring_cap = int(round(self._sr * float(audio_cfg["ring_buffer_duration_sec"])))
        self._in_device = audio_cfg.get("input_device", None)
        self._out_device = audio_cfg.get("output_device", None)
        # Actual hardware stream rates, resolved in start() -- may differ
        # from self._sr (the fixed DeepFilterNet processing rate) when the
        # input and output devices are physically different hardware with
        # different native rates. See _resolve_stream_samplerate().
        self._in_stream_sr = self._sr
        self._out_stream_sr = self._sr
        self._in_blocksize = self._chunk_samples
        self._out_blocksize = self._chunk_samples

        self._atten_lim_db = float(model_cfg.get("atten_lim_db", 100.0))
        self._output_gain = float(model_cfg.get("output_gain", 1.0))
        self._warmup_passes = int(pipe_cfg.get("warmup_passes", 3))
        self._priming_chunks = float(pipe_cfg.get("priming_chunks", 1.0))
        if self._priming_chunks < 0:
            raise ValueError(f"priming_chunks must be >= 0, got {self._priming_chunks}")
        self._startup_grace_sec = float(pipe_cfg.get("startup_grace_sec", 0.5))
        cpu_affinity_cfg = pipe_cfg.get("cpu_affinity", None)
        self._cpu_affinity = list(cpu_affinity_cfg) if cpu_affinity_cfg is not None else None
        self._fast_resample_enabled = bool(pipe_cfg.get("fast_resample", False))
        self._residual_filter_enabled = bool(pipe_cfg.get("residual_filter", False))
        self._inference_backend = str(pipe_cfg.get("inference_backend", "pytorch"))
        self._onnx_dir = str(pipe_cfg.get("onnx_dir", "results/onnx"))
        self._log_timing = bool(pipe_cfg.get("log_timing", False))
        self._latency_warn_sec = float(pipe_cfg.get("latency_warn_sec", 0.30))
        self._mode = (mode_override or pipe_cfg.get("mode", "enhance")).strip().lower()
        # Reference stream hardware rate, resolved in start().
        self._ref_stream_sr = self._sr

        if self._mode not in ("enhance", "bypass"):
            raise ValueError(f"Unknown mode {self._mode!r}. Use 'enhance' or 'bypass'.")

        self._in_buf = RingBuffer(self._ring_cap, channels=self._channels)
        self._out_buf = RingBuffer(self._ring_cap, channels=self._channels)

        # --- Phase 1 dual-mic configuration ---
        dual_mic_cfg = config.get("audio", {}).get("dual_mic", {})
        self._dual_mic_enabled = bool(dual_mic_cfg.get("enabled", False))
        self._ref_device = dual_mic_cfg.get("reference_device", None)
        self._ref_delay_samples = int(dual_mic_cfg.get("ref_delay_samples", 0))

        ref_nlms_cfg = config.get("pipeline", {}).get("reference_nlms", {})
        self._ref_nlms_enabled = bool(ref_nlms_cfg.get("enabled", False))
        self._ref_nlms_filter_length = int(ref_nlms_cfg.get("filter_length", 64))
        self._ref_nlms_mu = float(ref_nlms_cfg.get("mu", 0.01))
        self._ref_nlms_eps = float(ref_nlms_cfg.get("eps", 1e-6))
        self._ref_nlms_stage = str(ref_nlms_cfg.get("stage", "post_dfn"))

        if self._ref_nlms_enabled and not self._dual_mic_enabled:
            raise ValueError(
                "pipeline.reference_nlms.enabled requires audio.dual_mic.enabled: true. "
                "Enable dual_mic first."
            )

        # Second ring buffer + stream for reference channel (single-channel).
        # Created only when dual_mic is enabled to keep the single-mic path
        # completely unmodified.
        self._ref_buf = RingBuffer(self._ring_cap, channels=1) if self._dual_mic_enabled else None
        self._stream_ref = None
        self._ref_nlms = None  # instantiated in start() when enabled

        # Delay line for reference channel alignment (Topology B clock drift
        # compensation). Length = abs(ref_delay_samples). Positive delay means
        # reference is ahead; we delay it by holding samples in this buffer.
        ref_delay_abs = abs(self._ref_delay_samples)
        self._ref_delay_line = (
            np.zeros(ref_delay_abs, dtype=np.float32) if ref_delay_abs > 0 else None
        )

        # ERLE telemetry accumulators (populated from reference_nlms.erle_db()).
        self._erle_db_last = 0.0

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
        # Phase 2 (D2): underruns within self._startup_grace_sec of stream
        # start, bucketed separately from _dropped_chunks -- see
        # _classify_underrun() above and _output_callback below.
        self._startup_underruns = 0
        self._stream_start_t = None
        self._inference_errors = 0

        # Phase 5.3(b): RTF health check. Tracks a rolling window of
        # (timestamp, rtf) so a sustained overload (not a single slow chunk)
        # can trigger an automatic one-way switch to bypass mode -- unlike
        # DNSMOS's auto_bypass (default OFF, see config/audio_config.yaml:
        # a subjective quality score is too noisy a signal to act on
        # automatically during a demo), RTF is an objective, deterministic
        # measurement: if it's genuinely >0.9 sustained, the system cannot
        # keep up in real time and enhance-mode output is already glitching,
        # so bypass is strictly less risky than continuing to try.
        health_cfg = pipe_cfg.get("health_check", {})
        self._health_check_enabled = bool(health_cfg.get("enabled", True))
        self._health_rtf_threshold = float(health_cfg.get("rtf_threshold", 0.9))
        self._health_sustained_sec = float(health_cfg.get("sustained_sec", 5.0))
        self._health_auto_bypass = bool(health_cfg.get("auto_bypass", True))
        self._rtf_window = []  # list of (monotonic_ts, rtf), trimmed to _health_sustained_sec
        self._health_auto_bypass_triggered = False

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
        # indata shape: (frames, channels), float32, at self._in_stream_sr.
        chunk = indata
        if self._in_stream_sr != self._sr:
            chunk = _resample_multi(chunk, self._in_stream_sr, self._sr, use_fast=self._fast_resample_enabled)
        self._in_buf.write(chunk.copy())

    def _ref_callback(self, indata, frames, time_info, status):
        """Receive audio from the reference mic and push to reference ring buffer."""
        if status:
            print(f"[pipeline] Reference status: {status}", file=sys.stderr)
        chunk = indata
        if self._ref_stream_sr != self._sr:
            chunk = _resample_multi(chunk, self._ref_stream_sr, self._sr, use_fast=self._fast_resample_enabled)
        self._ref_buf.write(chunk[:, :1].copy())  # always single-channel

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
        # out_buf holds audio at self._sr (the processing rate); this
        # callback needs `frames` samples at self._out_stream_sr (the
        # device's actual hardware rate, which may differ -- see
        # _resolve_stream_samplerate()). Read the equivalent duration at
        # self._sr first, then resample to the device rate.
        if self._out_stream_sr != self._sr:
            read_frames = int(round(frames * self._sr / self._out_stream_sr))
        else:
            read_frames = frames
        chunk = self._out_buf.read(read_frames, timeout=self._chunk_sec * 2)
        if chunk is None:
            # Buffer underrun — output silence to avoid glitches.
            outdata[:] = 0.0
            since_start = (
                time.monotonic() - self._stream_start_t
                if self._stream_start_t is not None else None
            )
            bucket = _classify_underrun(self._running.is_set(), since_start, self._startup_grace_sec)
            if bucket == "teardown":
                # Post-stop() drain: the inference thread is already gone, so
                # an empty buffer here is expected, not a real-time miss.
                self._teardown_underruns += 1
            elif bucket == "startup":
                # Cold-start transient (Phase 2, D2) -- excluded from the
                # stress verdict but always reported. See _classify_underrun.
                self._startup_underruns += 1
            else:
                self._dropped_chunks += 1
        else:
            if self._out_stream_sr != self._sr:
                chunk = _resample_multi(chunk, self._sr, self._out_stream_sr, use_fast=self._fast_resample_enabled)
            # Resampling rounds to the nearest sample count, which can be
            # off by one relative to `frames` -- pad/trim to the exact size
            # sounddevice expects for this callback.
            if chunk.shape[0] < frames:
                chunk = np.pad(chunk, ((0, frames - chunk.shape[0]), (0, 0)))
            elif chunk.shape[0] > frames:
                chunk = chunk[:frames]
            # Apply output gain and write to device buffer.
            outdata[:] = chunk * self._output_gain

    # ------------------------------------------------------------------
    # Inference thread
    # ------------------------------------------------------------------

    def _update_health_check(self, rtf: float):
        """
        Phase 5.3(b). Called once per processed chunk from _inference_loop
        with that chunk's RTF. Maintains the rolling window and flips to
        bypass mode (one-way -- does not auto-recover back to enhance, to
        avoid flapping mid-demo) the first time _check_rtf_health() reports
        a sustained overload. No-ops entirely if health_check.enabled=false.
        """
        if not self._health_check_enabled or self._health_auto_bypass_triggered:
            return

        now = time.monotonic()
        self._rtf_window.append((now, rtf))
        cutoff = now - self._health_sustained_sec
        self._rtf_window = [(t, r) for t, r in self._rtf_window if t >= cutoff]

        if _check_rtf_health(self._rtf_window, self._health_rtf_threshold, self._health_sustained_sec):
            print(
                f"[pipeline] [WARN] RTF > {self._health_rtf_threshold} sustained for "
                f">= {self._health_sustained_sec}s -- system cannot keep up in real time.",
                file=sys.stderr,
            )
            self._health_auto_bypass_triggered = True
            if self._health_auto_bypass and self._mode == "enhance":
                self._mode = "bypass"
                print(
                    "[pipeline] [WARN] Auto-switched to BYPASS mode to avoid audible failure "
                    "(pipeline.health_check.auto_bypass). This does not auto-recover -- "
                    "restart the pipeline once the overload cause is resolved.",
                    file=sys.stderr,
                )

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

        # Phase 2 (D5): only THIS thread can be pinned from Python -- the
        # audio callbacks run on PortAudio's internal C threads. No-ops with
        # a warning (never raises) when self._cpu_affinity is None or
        # unsupported on this platform. See live/cpu_affinity.py.
        if self._cpu_affinity is not None:
            pinned = set_thread_affinity(self._cpu_affinity)
            print(
                f"[pipeline] Inference thread affinity -> cores={self._cpu_affinity}: "
                f"{'applied' if pinned else 'not applied (see warning above)'}",
                file=sys.stderr,
            )

        while self._running.is_set():
            chunk = self._in_buf.read(self._chunk_samples, timeout=self._chunk_sec * 2)
            if chunk is None:
                # Timeout waiting for input — loop and retry.
                continue

            try:
                # chunk shape: (chunk_samples, channels)
                # InferenceEngine expects (n_samples,) or (1, n_samples) mono.
                mono = chunk[:, 0]   # Take channel 0; DeepFilterNet is single-channel.
                self.last_in_chunk = mono

                # Read reference channel, applying delay compensation.
                ref_mono = None
                if self._dual_mic_enabled and self._ref_buf is not None:
                    ref_chunk = self._ref_buf.read(self._chunk_samples,
                                                   timeout=self._chunk_sec * 2)
                    if ref_chunk is not None:
                        ref_raw = ref_chunk[:, 0]
                        # Apply integer delay to align reference with primary.
                        # ref_delay_samples > 0: reference is ahead; delay it.
                        if self._ref_delay_samples > 0 and self._ref_delay_line is not None:
                            combined = np.concatenate([self._ref_delay_line, ref_raw])
                            ref_mono = combined[:self._chunk_samples]
                            self._ref_delay_line = combined[self._chunk_samples:]
                        # ref_delay_samples < 0: primary is ahead; delay primary.
                        elif self._ref_delay_samples < 0 and self._ref_delay_line is not None:
                            combined = np.concatenate([self._ref_delay_line, mono])
                            mono = combined[:self._chunk_samples]
                            self._ref_delay_line = combined[self._chunk_samples:]
                            ref_mono = ref_raw
                        else:
                            ref_mono = ref_raw

                # Phase 1 pre-DFN reference NLMS stage.
                if (self._mode == "enhance"
                        and self._ref_nlms is not None
                        and ref_mono is not None
                        and self._ref_nlms_stage == "pre_dfn"):
                    mono = self._ref_nlms.process_chunk(mono, ref_mono)
                    self._erle_db_last = self._ref_nlms.erle_db()

                t0 = time.perf_counter()
                if self._mode == "enhance":
                    enhanced = self._engine.enhance_chunk(mono)
                else:
                    enhanced = self._engine.bypass_chunk(mono)
                elapsed = time.perf_counter() - t0
                self._chunk_latencies.append(elapsed)
                audio_dur = self._chunk_samples / self._sr
                rtf = elapsed / audio_dur

                if self._log_timing or elapsed > self._latency_warn_sec:
                    level = "WARN" if elapsed > self._latency_warn_sec else "INFO"
                    print(
                        f"[pipeline] [{level}] chunk: {elapsed*1000:.2f} ms "
                        f"(audio={audio_dur*1000:.0f} ms, RTF={rtf:.4f})",
                        file=sys.stderr,
                    )

                self._update_health_check(rtf)

                # enhanced shape: (1, n_out) — write back as (n_out, 1) for ring buffer.
                out_mono = enhanced[0]   # shape (n_out,)
                # Trim or pad to chunk_samples to keep buffers aligned.
                if len(out_mono) >= self._chunk_samples:
                    out_mono = out_mono[:self._chunk_samples]
                else:
                    out_mono = np.pad(out_mono, (0, self._chunk_samples - len(out_mono)))

                # P1-1 residual ALE stage (reference-free, runs on DFN3 output).
                if self._mode == "enhance" and self._residual_filter is not None:
                    out_mono = self._residual_filter.process_chunk(out_mono)

                # Phase 1 post-DFN reference NLMS stage.
                if (self._mode == "enhance"
                        and self._ref_nlms is not None
                        and ref_mono is not None
                        and self._ref_nlms_stage == "post_dfn"):
                    out_mono = self._ref_nlms.process_chunk(out_mono, ref_mono)
                    self._erle_db_last = self._ref_nlms.erle_db()

            except Exception as exc:
                # A single bad chunk must not kill this thread -- that would
                # silently blackhole all audio output for the rest of the
                # session with no crash and no further log line. Output
                # silence for this chunk and keep going.
                self._inference_errors += 1
                print(f"[pipeline] [ERROR] inference chunk failed: {exc}", file=sys.stderr)
                out_mono = np.zeros(self._chunk_samples, dtype=np.float32)

            self.last_out_chunk = out_mono
            self._out_buf.write(out_mono[:, np.newaxis])

        print("[pipeline] Inference thread exiting.", file=sys.stderr)

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    def start(self):
        """Load model, open streams, start inference thread."""
        if self._fast_resample_enabled and not _FAST_RESAMPLE_NUMBA_AVAILABLE:
            # Fail HERE (before any hardware is touched), not on the first
            # audio callback that actually needs to resample -- same
            # discipline as residual_filter/reference_nlms below.
            raise RuntimeError(
                "pipeline.fast_resample is enabled but numba is not installed. "
                "Install it with:\n"
                "    pip install numba==0.67.0\n"
                "or set pipeline.fast_resample: false in config/audio_config.yaml "
                "to use the default np.interp-based resampler (see "
                "live/fast_resample.py -- D4: measure-first, keep only if it helps)."
            )

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
            # Lazy import -- see the note at the top of this module. numba is
            # optional; if it's missing, fail HERE with an actionable message
            # rather than at import time (which would break the pipeline even
            # with this feature turned off).
            try:
                from live.residual_filter import ResidualALEFilter
            except ImportError as exc:
                raise RuntimeError(
                    "pipeline.residual_filter is enabled but its optional dependency "
                    f"is missing ({exc}). Install it with:\n"
                    "    pip install numba==0.67.0\n"
                    "or set pipeline.residual_filter: false in config/audio_config.yaml "
                    "to run without the residual stage (it is off by default and not "
                    "yet quality-validated -- see live/residual_filter.py)."
                ) from exc
            print("[pipeline] Residual filter (P1-1, reference-free ALE) ENABLED.", file=sys.stderr)
            self._residual_filter = ResidualALEFilter()

        if self._ref_nlms_enabled:
            # Lazy import — same pattern as residual_filter. A disabled feature
            # must never break the core path when numba is absent (rule from
            # the 2026-08-24 Pi incident). Fail here with an actionable message.
            try:
                from live.reference_nlms import ReferenceNLMSFilter
            except ImportError as exc:
                raise RuntimeError(
                    "pipeline.reference_nlms.enabled requires numba, which is not "
                    f"installed ({exc}). Install it with:\n"
                    "    pip install numba==0.67.0\n"
                    "or set pipeline.reference_nlms.enabled: false in "
                    "config/audio_config.yaml."
                ) from exc
            print(
                f"[pipeline] Reference NLMS (Phase 1, stage={self._ref_nlms_stage!r}) ENABLED "
                f"(L={self._ref_nlms_filter_length}, mu={self._ref_nlms_mu}).",
                file=sys.stderr,
            )
            self._ref_nlms = ReferenceNLMSFilter(
                filter_length=self._ref_nlms_filter_length,
                mu=self._ref_nlms_mu,
                eps=self._ref_nlms_eps,
            )

        self._running.set()
        self._inference_thread = threading.Thread(
            target=self._inference_loop, daemon=True, name="InferenceThread"
        )
        self._inference_thread.start()

        # Resolve output device unconditionally — real speakers/headset are
        # used in both normal and backup mode, per Phase 5.1: judges must
        # still hear the actual pipeline output when the mic fails.
        out_dev = _resolve_device(self._out_device, kind="output")
        self._out_stream_sr = _resolve_stream_samplerate(
            out_dev, self._sr, self._channels, kind="output"
        )
        self._out_blocksize = int(round(self._out_stream_sr * self._chunk_sec))

        if self._backup_audio_path:
            # Phase 5.1: backup demo mode. No sd.InputStream is opened at
            # all -- audio is fed from a WAV file at real-time cadence
            # instead. Dual-mic reference capture is skipped too (there is
            # no live reference mic in this mode either); reference_nlms
            # would otherwise silently see a stale/empty reference buffer.
            print(
                f"[pipeline] *** BACKUP AUDIO MODE ACTIVE *** — source={self._backup_audio_path!r}. "
                f"No live microphone is in use; this is pre-recorded audio.",
                file=sys.stderr,
            )
            if self._dual_mic_enabled:
                print(
                    "[pipeline] WARNING: dual_mic.enabled is true but backup mode has no live "
                    "reference mic either — reference_nlms will not run this session.",
                    file=sys.stderr,
                )
            from demo.backup_playback import BackupAudioSource
            self._backup_source = BackupAudioSource(
                self._backup_audio_path, sample_rate=self._sr, channels=self._channels, loop=True
            )
            print(
                f"[pipeline] Backup clip duration: {self._backup_source.duration_sec:.1f}s (loops).",
                file=sys.stderr,
            )
            self._in_stream_sr = self._sr  # file is pre-resampled by BackupAudioSource
        else:
            # Normal mode — resolve and open the real input device.
            in_dev = _resolve_device(self._in_device, kind="input")
            self._in_stream_sr = _resolve_stream_samplerate(
                in_dev, self._sr, self._channels, kind="input"
            )
            self._in_blocksize = int(round(self._in_stream_sr * self._chunk_sec))

            print(
                f"[pipeline] Opening streams "
                f"(input_device={in_dev!r} @ {self._in_stream_sr} Hz, "
                f"output_device={out_dev!r} @ {self._out_stream_sr} Hz, "
                f"processing @ {self._sr} Hz)...",
                file=sys.stderr,
            )
            self._stream_in = sd.InputStream(
                samplerate=self._in_stream_sr,
                blocksize=self._in_blocksize,
                device=in_dev,
                channels=self._channels,
                dtype="float32",
                callback=self._input_callback,
                latency="low",
            )

            # Open reference mic stream (Phase 1 — only when dual_mic is enabled).
            if self._dual_mic_enabled and self._ref_device is not None:
                ref_dev = _resolve_device(self._ref_device, kind="input")
                self._ref_stream_sr = _resolve_stream_samplerate(
                    ref_dev, self._sr, 1, kind="input"
                )
                ref_blocksize = int(round(self._ref_stream_sr * self._chunk_sec))
                print(
                    f"[pipeline] Opening reference stream "
                    f"(device={ref_dev!r} @ {self._ref_stream_sr} Hz, "
                    f"delay={self._ref_delay_samples} samples)...",
                    file=sys.stderr,
                )
                self._stream_ref = sd.InputStream(
                    samplerate=self._ref_stream_sr,
                    blocksize=ref_blocksize,
                    device=ref_dev,
                    channels=1,
                    dtype="float32",
                    callback=self._ref_callback,
                    latency="low",
                )

        # Open output stream (real hardware, both modes).
        self._stream_out = sd.OutputStream(
            samplerate=self._out_stream_sr,
            blocksize=self._out_blocksize,
            device=out_dev,
            channels=self._channels,
            dtype="float32",
            callback=self._output_callback,
            latency="low",
        )

        if self._stream_in is not None:
            self._stream_in.start()
        self._stream_out.start()
        if self._stream_ref is not None:
            self._stream_ref.start()
        if self._backup_source is not None:
            self._backup_thread = self._backup_source.start_feeding(
                self._in_buf, self._running, self._chunk_sec
            )

        # Phase 2 (D2): marks t=0 for the startup-underrun grace window in
        # _output_callback / _classify_underrun. Recorded right after the
        # streams actually start, not at the top of this method.
        self._stream_start_t = time.monotonic()

        # Prime the output buffer with silence so the output callback doesn't
        # underrun before inference produces the first real output. This is a
        # FIFO -- every primed sample is permanent standing latency
        # (priming_chunks * chunk_duration_sec), not a one-time warmup cost.
        # Phase 2 (D1): priming_chunks is now a float; 1.0 writes exactly
        # self._chunk_samples samples, byte-identical to the old int-loop
        # behaviour. Keep this as small as the measured inference jitter
        # allows; verify with stress_test.py after any change (0 real
        # dropouts required -- startup-window underruns are tracked
        # separately, see _startup_underruns).
        n_priming_samples = _compute_priming_samples(self._priming_chunks, self._chunk_samples)
        if n_priming_samples > 0:
            silence = np.zeros((n_priming_samples, self._channels), dtype=np.float32)
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

        if self._stream_ref is not None:
            self._stream_ref.stop()
            self._stream_ref.close()

        if self._stream_out is not None:
            self._stream_out.stop()
            self._stream_out.close()

        if self._inference_thread is not None:
            self._inference_thread.join(timeout=3.0)

        if self._backup_thread is not None:
            # Daemon thread already exits on its own once _running is
            # cleared (checked once per chunk_sec in its feed loop) -- this
            # join is just to avoid a race where _print_stats() below prints
            # while the thread is still mid-iteration.
            self._backup_thread.join(timeout=self._chunk_sec * 3)

        self._print_stats()

    def _print_stats(self):
        if not self._chunk_latencies:
            return
        lats = np.array(self._chunk_latencies) * 1000.0   # ms
        audio_dur_ms = self._chunk_sec * 1000.0
        rtfs = lats / audio_dur_ms
        dual_mic_line = ""
        if self._dual_mic_enabled:
            ref_overflows = self._ref_buf.overflow_count if self._ref_buf else 0
            nlms_line = (
                f"  Reference NLMS ERLE (telemetry): {self._erle_db_last:.1f} dB\n"
                if self._ref_nlms is not None else ""
            )
            dual_mic_line = (
                f"\n  Reference buffer overflows: {ref_overflows}\n"
                f"  ref_delay_samples: {self._ref_delay_samples}\n"
                + nlms_line
            )
        backup_line = (
            f"\n  Backup audio mode: ACTIVE (source={self._backup_audio_path})"
            if self._backup_audio_path else ""
        )
        health_line = (
            f"\n  RTF health check: AUTO-BYPASS TRIGGERED "
            f"(RTF > {self._health_rtf_threshold} sustained >= {self._health_sustained_sec}s)"
            if self._health_auto_bypass_triggered else ""
        )
        print(
            f"\n[pipeline] === Session stats ({len(lats)} chunks) ===\n"
            f"  Latency: median={np.median(lats):.2f} ms, "
            f"p95={np.percentile(lats, 95):.2f} ms, "
            f"max={np.max(lats):.2f} ms\n"
            f"  RTF:     median={np.median(rtfs):.4f}, "
            f"p95={np.percentile(rtfs, 95):.4f}\n"
            f"  Input buffer overflows: {self._in_buf.overflow_count}\n"
            f"  Output buffer underruns: {self._dropped_chunks}"
            f"  (+{self._startup_underruns} during startup grace window, "
            f"+{self._teardown_underruns} during shutdown drain -- neither is a failure)\n"
            f"  Inference errors: {self._inference_errors}"
            + dual_mic_line + backup_line + health_line,
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


# ---------------------------------------------------------------------------
# Self-test (Mode A — no hardware required)
# ---------------------------------------------------------------------------

def _self_test():
    """
    Covers the Phase 2 pure-logic pieces that don't need real audio hardware:
      - D1 fractional priming sample-count arithmetic (A1)
      - D2 startup/teardown/real underrun classification (A2)
    Does NOT open any sounddevice stream or load InferenceEngine/DeepFilterNet
    -- that's Mode B (live/stress_test.py, live/main.py pipeline).
    """
    print("live/pipeline.py self-test -- start")

    chunk_samples = 4800  # 100 ms @ 48 kHz, the project default

    # --- Test 1: priming_chunks=1.0 is byte-identical to the pre-Phase-2 behaviour ---
    n = _compute_priming_samples(1.0, chunk_samples)
    assert n == chunk_samples, f"1.0 should prime exactly one chunk, got {n} samples"
    print(f"  [PASS] test 1: priming_chunks=1.0 -> {n} samples (identical to old int-loop behaviour)")

    # --- Test 2: fractional and zero priming ---
    assert _compute_priming_samples(0.5, chunk_samples) == round(0.5 * chunk_samples)
    assert _compute_priming_samples(0.25, chunk_samples) == round(0.25 * chunk_samples)
    assert _compute_priming_samples(0.0, chunk_samples) == 0
    print(f"  [PASS] test 2: priming_chunks=0.5 -> {_compute_priming_samples(0.5, chunk_samples)} samples, "
          f"0.25 -> {_compute_priming_samples(0.25, chunk_samples)} samples, 0.0 -> 0 samples")

    # --- Test 3: negative priming_chunks raises ---
    try:
        _compute_priming_samples(-0.1, chunk_samples)
        assert False, "expected ValueError for negative priming_chunks"
    except ValueError:
        pass
    print("  [PASS] test 3: negative priming_chunks raises ValueError")

    # --- Test 4: underrun classification -- teardown always wins ---
    assert _classify_underrun(is_running=False, since_start_sec=0.01, grace_sec=0.5) == "teardown"
    assert _classify_underrun(is_running=False, since_start_sec=999.0, grace_sec=0.5) == "teardown"
    print("  [PASS] test 4: not-running underruns always classify as teardown")

    # --- Test 5: underrun classification -- inside vs outside the startup grace window ---
    assert _classify_underrun(is_running=True, since_start_sec=0.1, grace_sec=0.5) == "startup"
    assert _classify_underrun(is_running=True, since_start_sec=0.49, grace_sec=0.5) == "startup"
    assert _classify_underrun(is_running=True, since_start_sec=0.5, grace_sec=0.5) == "real"
    assert _classify_underrun(is_running=True, since_start_sec=10.0, grace_sec=0.5) == "real"
    print("  [PASS] test 5: running underruns classify as startup within the grace window, "
          "real once past it (verdict is unaffected by in-window ones, fails on out-of-window ones)")

    # --- Test 6: RTF health check (Phase 5.3b) -- empty/short windows never trigger ---
    assert _check_rtf_health([], threshold=0.9, sustained_sec=5.0) is False
    assert _check_rtf_health([(0.0, 0.95)], threshold=0.9, sustained_sec=5.0) is False
    print("  [PASS] test 6: empty or single-sample RTF windows never trigger auto-bypass")

    # --- Test 7: sustained overload (span >= sustained_sec, every sample over threshold) triggers ---
    window = [(t, 0.95) for t in [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]]
    assert _check_rtf_health(window, threshold=0.9, sustained_sec=5.0) is True
    print("  [PASS] test 7: 6 samples over 5.0s span, all RTF=0.95 > 0.9 -> triggers")

    # --- Test 8: one healthy sample in the window blocks the trigger ---
    window = [(0.0, 0.95), (1.0, 0.95), (2.0, 0.5), (3.0, 0.95), (4.0, 0.95), (5.0, 0.95)]
    assert _check_rtf_health(window, threshold=0.9, sustained_sec=5.0) is False
    print("  [PASS] test 8: a single healthy sample (RTF=0.5) inside the window blocks the trigger")

    # --- Test 9: all samples over threshold but window doesn't span sustained_sec yet ---
    window = [(t, 0.95) for t in [0.0, 0.5, 1.0, 1.5, 2.0]]   # only 2.0s span
    assert _check_rtf_health(window, threshold=0.9, sustained_sec=5.0) is False
    print("  [PASS] test 9: RTF over threshold but window spans only 2.0s < 5.0s -> does not trigger yet")

    # --- Test 10: LivePipeline wiring for backup_audio_path / health_check config
    # (constructor only -- does not touch sounddevice, safe for Mode A) ---
    minimal_cfg = {
        "audio": {"sample_rate": 48000, "channels": 1, "chunk_duration_sec": 0.1,
                   "ring_buffer_duration_sec": 2.0, "input_device": None, "output_device": None},
        "model": {"atten_lim_db": 30.0, "output_gain": 1.0},
        "pipeline": {"mode": "enhance", "health_check": {"enabled": True, "rtf_threshold": 0.8,
                                                           "sustained_sec": 3.0, "auto_bypass": True}},
    }
    p = LivePipeline(minimal_cfg, backup_audio_path="demo/backup_audio/backup_60s.wav")
    assert p._backup_audio_path == "demo/backup_audio/backup_60s.wav"
    assert p._health_rtf_threshold == 0.8 and p._health_sustained_sec == 3.0
    assert p._health_auto_bypass is True and p._health_auto_bypass_triggered is False
    print("  [PASS] test 10: LivePipeline constructor wires backup_audio_path and "
          "health_check config correctly (no hardware touched)")

    print("live/pipeline.py self-test -- ALL PASSED")


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
    parser.add_argument(
        "--backup",
        default=None,
        metavar="WAV_PATH",
        help="Phase 5.1: play this WAV file instead of the live microphone "
             "(e.g. demo/backup_audio/backup_60s.wav, built via "
             "'python demo/backup_playback.py --generate'). Real output "
             "hardware is still used -- only the input side is replaced.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run Mode A self-test (priming/underrun logic, no hardware) and exit",
    )
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    if args.list_devices:
        _list_devices()
        return

    config = _load_config(args.config)
    if args.log_timing:
        config["pipeline"]["log_timing"] = True

    pipeline = LivePipeline(config, mode_override=args.mode, backup_audio_path=args.backup)
    pipeline.run_blocking()


if __name__ == "__main__":
    _main()
