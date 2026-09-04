"""
demo/backup_playback.py — Phase 5.1: backup demo mode.

If the live demo microphone fails (dead battery, bad cable, USB drop mid-
session), this lets the presenter switch to a pre-recorded 60-second noisy
clip with ONE flag, and the audience still hears the real enhancement
pipeline work on real, previously-unseen-by-the-model audio.

Two pieces:

  1. generate_backup_clip() — builds the 60-second demo WAV from the
     project's own real corpus: a continuous engine noise bed (real ESC-50
     recording), two gunshot bursts (real Zenodo firearm recordings), and a
     spoken-command track built by concatenating several real LibriSpeech
     utterances with silence gaps between them (this project has no actual
     military command-phrase recordings, so this is honestly real recorded
     human speech standing in for "a spoken command" -- not synthesized
     text-to-speech, not claimed to be scripted command phraseology).
     Mixed at a fixed SNR using the SAME mix_signals() the real 300-mixture
     dataset uses (data/mix_dataset.py), so the clip is representative of
     what results/final/target_compliance.md actually measures, not a
     separately-tuned "looks good" demo clip.

  2. BackupAudioSource — reads that WAV in real-time-paced chunks and feeds
     them into a RingBuffer using the exact same write() call shape as
     live/pipeline.py's _input_callback(). live/pipeline.py's start()
     substitutes this for the real sd.InputStream when --backup is passed;
     the output stream (real speakers/headset) is untouched, so judges hear
     it through the actual demo hardware, not a separate playback tool.

Usage:
    python demo/backup_playback.py --generate            # build the clip (idempotent)
    python demo/backup_playback.py --generate --force     # rebuild even if it exists
    python demo/backup_playback.py --info                 # print clip duration/composition
    python demo/backup_playback.py --self-test             # Mode A, no hardware

    # Actual demo use (Phase 5.1's "one command switch"):
    python live/main.py pipeline --backup demo/backup_audio/backup_60s.wav
"""

import os
import sys
import time
import argparse
import threading
import numpy as np
import soundfile as sf

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

DEFAULT_CLIP_PATH = os.path.join("demo", "backup_audio", "backup_60s.wav")
DEFAULT_DURATION_SEC = 60.0
DEFAULT_SNR_DB = -5.0

# Real corpus sources used to build the clip (same files the offline eval
# pipeline draws from -- see data/SOURCES.md for provenance/licence).
DEFAULT_ENGINE_NOISE = os.path.join("data", "noise", "stationary", "engine")
DEFAULT_GUNSHOT_NOISE = os.path.join("data", "noise", "impulsive", "gunshot")
DEFAULT_CLEAN_SPEECH = "data/clean"


def _resample_mono(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    """
    Linear-interpolation resampler, matching live/pipeline.py::_resample's
    method exactly (kept as a local copy rather than importing pipeline's
    underscore-prefixed internal, since this module must also work with zero
    pipeline/sounddevice dependency for --generate/--info/--self-test).
    """
    if sr_from == sr_to or x.shape[0] == 0:
        return x
    n_out = int(round(x.shape[0] * sr_to / sr_from))
    if n_out <= 0:
        return np.zeros(0, dtype=x.dtype)
    src_idx = np.arange(x.shape[0])
    dst_idx = np.linspace(0, x.shape[0] - 1, num=n_out)
    return np.interp(dst_idx, src_idx, x).astype(x.dtype)


def _load_mono(path: str, target_sr: int) -> np.ndarray:
    data, sr = sf.read(path, dtype="float32")
    if data.ndim > 1:
        data = data[:, 0]
    return _resample_mono(data, sr, target_sr)


def generate_backup_clip(
    output_path: str = DEFAULT_CLIP_PATH,
    duration_sec: float = DEFAULT_DURATION_SEC,
    target_snr_db: float = DEFAULT_SNR_DB,
    sample_rate: int = 48000,
    engine_dir: str = DEFAULT_ENGINE_NOISE,
    gunshot_dir: str = DEFAULT_GUNSHOT_NOISE,
    clean_dir: str = DEFAULT_CLEAN_SPEECH,
    seed: int = 42,
    force: bool = False,
) -> str:
    """
    Build the 60-second backup demo clip. Idempotent: skips regeneration if
    output_path already exists, unless force=True (same convention as
    data/mix_dataset.py's other one-off generator scripts).

    Composition:
      - Engine noise bed, looped/cropped to fill the full duration.
      - Two gunshot bursts, placed at roughly 1/4 and 3/4 through the clip
        (an "under fire" scenario, not a single isolated event).
      - 3-4 real LibriSpeech utterances concatenated with 1.5s silence gaps,
        standing in for spoken radio traffic across the clip.
      - Mixed via data.mix_dataset.mix_signals() at target_snr_db, the same
        function results/eval_raw.csv's numbers come from.
    """
    if os.path.exists(output_path) and not force:
        print(f"[backup_playback] {output_path} already exists (use --force to rebuild). Skipping.")
        return output_path

    import glob
    import random
    from data.mix_dataset import mix_signals

    random.seed(seed)
    np.random.seed(seed)

    n_total = int(round(duration_sec * sample_rate))

    # --- Engine bed: loop a real recording to fill the clip ---
    # Recursive glob (** ) matches data/mix_dataset.py's own noise-discovery pattern
    # (mix_dataset.py:173) -- the gunshot corpus in particular is nested one level
    # deeper by firearm type (data/noise/impulsive/gunshot/<type>/*.wav), not flat.
    engine_files = sorted(glob.glob(os.path.join(engine_dir, "**", "*.wav"), recursive=True))
    if not engine_files:
        raise FileNotFoundError(f"No engine noise files found in {engine_dir!r}")
    engine = _load_mono(random.choice(engine_files), sample_rate)
    if len(engine) < n_total:
        engine = np.tile(engine, int(np.ceil(n_total / len(engine))))
    engine = engine[:n_total]

    # --- Gunshot bursts: two real transients, placed away from the edges ---
    gunshot_files = sorted(glob.glob(os.path.join(gunshot_dir, "**", "*.wav"), recursive=True))
    if not gunshot_files:
        raise FileNotFoundError(f"No gunshot files found in {gunshot_dir!r}")
    burst_track = np.zeros(n_total, dtype=np.float32)
    burst_positions_frac = [0.25, 0.70]
    chosen_shots = random.sample(gunshot_files, min(2, len(gunshot_files)))
    for frac, shot_path in zip(burst_positions_frac, chosen_shots):
        shot = _load_mono(shot_path, sample_rate)
        place_at = int(round(frac * n_total))
        end = min(place_at + len(shot), n_total)
        burst_track[place_at:end] += shot[: end - place_at]

    combined_noise = engine * 0.6 + burst_track * 1.4

    # --- Spoken track: concatenate real speech utterances with silence gaps ---
    clean_files = sorted(glob.glob(os.path.join(clean_dir, "*.flac")) +
                          glob.glob(os.path.join(clean_dir, "*.wav")))
    if not clean_files:
        raise FileNotFoundError(f"No clean speech files found in {clean_dir!r}")
    gap = np.zeros(int(round(1.5 * sample_rate)), dtype=np.float32)
    speech_track = np.zeros(n_total, dtype=np.float32)
    cursor = int(round(2.0 * sample_rate))   # 2s lead-in of noise-only before speech starts
    chosen_speech = random.sample(clean_files, min(4, len(clean_files)))
    for speech_path in chosen_speech:
        utt = _load_mono(speech_path, sample_rate)
        end = min(cursor + len(utt), n_total)
        if cursor >= n_total:
            break
        speech_track[cursor:end] = utt[: end - cursor]
        cursor = end + len(gap)

    mixed, scaled_clean, achieved_snr, norm_factor = mix_signals(
        speech_track, combined_noise, target_snr_db
    )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    sf.write(output_path, mixed, sample_rate)
    clean_ref_path = os.path.splitext(output_path)[0] + "_clean_ref.wav"
    sf.write(clean_ref_path, scaled_clean, sample_rate)

    print(f"[backup_playback] Generated {output_path}")
    print(f"  Duration        : {n_total / sample_rate:.1f}s")
    print(f"  Engine bed      : {os.path.basename(engine_files[0]) if len(engine_files)==1 else '(random pick)'}")
    print(f"  Gunshot bursts  : {[os.path.basename(p) for p in chosen_shots]} at {burst_positions_frac}")
    print(f"  Speech track    : {[os.path.basename(p) for p in chosen_speech]}")
    print(f"  Target/achieved SNR: {target_snr_db} / {achieved_snr:.2f} dB")
    print(f"  Clean reference : {clean_ref_path}")
    return output_path


class BackupAudioSource:
    """
    Feeds a pre-recorded WAV file into a RingBuffer at real-time cadence,
    mimicking live/pipeline.py's _input_callback() write() shape exactly
    ((chunk_samples, channels) float32 arrays) so the rest of the pipeline
    (inference thread, output stream) doesn't need to know the difference.

    Pull-based read_chunk() is kept separate from the real-time feeding
    thread so the chunking/looping/resampling logic is unit-testable without
    any timing or threading involved (see _self_test below).
    """

    def __init__(self, wav_path: str, sample_rate: int, channels: int = 1, loop: bool = True):
        if not os.path.exists(wav_path):
            raise FileNotFoundError(
                f"Backup audio file not found: {wav_path!r}. "
                f"Generate it first: python demo/backup_playback.py --generate"
            )
        data, file_sr = sf.read(wav_path, dtype="float32")
        if data.ndim > 1:
            data = data[:, 0]
        if file_sr != sample_rate:
            data = _resample_mono(data, file_sr, sample_rate)
        self._audio = data
        self._pos = 0
        self._sample_rate = sample_rate
        self._channels = channels
        self._loop = loop
        self._exhausted = False
        self.wav_path = wav_path

    @property
    def duration_sec(self) -> float:
        return len(self._audio) / self._sample_rate

    def read_chunk(self, chunk_samples: int):
        """
        Returns the next (chunk_samples, channels) float32 array, or None if
        the clip has ended and loop=False. Loops back to the start
        automatically when loop=True (default -- a demo backup clip should
        keep playing, not go silent partway through a long Q&A).
        """
        if self._exhausted:
            return None
        remaining = len(self._audio) - self._pos
        if remaining <= 0:
            if self._loop:
                self._pos = 0
                remaining = len(self._audio)
            else:
                self._exhausted = True
                return None
        take = min(chunk_samples, remaining)
        mono = self._audio[self._pos:self._pos + take]
        self._pos += take
        if take < chunk_samples:
            # Ran off the end mid-chunk; pad with silence rather than
            # returning a short array the ring buffer isn't expecting.
            mono = np.pad(mono, (0, chunk_samples - take))
        return np.tile(mono[:, np.newaxis], (1, self._channels))

    def start_feeding(self, ring_buffer, running_event: threading.Event, chunk_sec: float) -> threading.Thread:
        """
        Spawn a daemon thread that pushes real-time-paced chunks into
        ring_buffer until running_event is cleared. Uses a monotonic-clock
        deadline per iteration (not a flat sleep(chunk_sec)) so small
        per-chunk processing overhead doesn't accumulate into audible drift
        over a 60s+ clip.
        """
        def _feed_loop():
            next_deadline = time.monotonic()
            chunk_samples = round(chunk_sec * self._sample_rate)
            while running_event.is_set():
                chunk = self.read_chunk(chunk_samples)
                if chunk is None:
                    break
                ring_buffer.write(chunk.copy())
                next_deadline += chunk_sec
                sleep_for = next_deadline - time.monotonic()
                if sleep_for > 0:
                    time.sleep(sleep_for)
                else:
                    # Fell behind real-time pacing; resync instead of
                    # spinning to catch up all at once.
                    next_deadline = time.monotonic()

        t = threading.Thread(target=_feed_loop, daemon=True, name="BackupAudioFeed")
        t.start()
        return t


# ---------------------------------------------------------------------------
# Self-test (Mode A -- no hardware, no sounddevice)
# ---------------------------------------------------------------------------

def _self_test():
    print("demo/backup_playback.py self-test -- start")
    ok = True

    # --- Test 1: generate a short synthetic clip end-to-end (uses real corpus files) ---
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="backup_selftest_")
    tmp_clip = os.path.join(tmp_dir, "tiny_backup.wav")
    try:
        generate_backup_clip(
            output_path=tmp_clip,
            duration_sec=3.0,     # short, for a fast self-test
            target_snr_db=-5.0,
            sample_rate=48000,
        )
        if os.path.exists(tmp_clip):
            print("  [PASS] test 1: generate_backup_clip() produces a WAV file from real corpus sources")
        else:
            print("  [FAIL] test 1: output file missing after generate_backup_clip()")
            ok = False
    except FileNotFoundError as exc:
        print(f"  [SKIP] test 1: real corpus not available on this machine ({exc})")

    # --- Test 2: BackupAudioSource chunking is exact and shape-correct ---
    if os.path.exists(tmp_clip):
        src = BackupAudioSource(tmp_clip, sample_rate=48000, channels=1, loop=False)
        chunk_samples = 4800  # 100ms @ 48kHz, project default
        total_read = 0
        n_chunks = 0
        while True:
            c = src.read_chunk(chunk_samples)
            if c is None:
                break
            assert c.shape == (chunk_samples, 1), f"unexpected chunk shape {c.shape}"
            total_read += chunk_samples
            n_chunks += 1
            if n_chunks > 100:   # safety cap, a 3s clip is ~30 chunks
                break
        expected_chunks = int(np.ceil(3.0 * 48000 / chunk_samples))
        if n_chunks == expected_chunks:
            print(f"  [PASS] test 2: non-looping source reads exactly {n_chunks} chunks "
                  f"for a 3.0s clip at 100ms chunks, then stops")
        else:
            print(f"  [FAIL] test 2: expected {expected_chunks} chunks, got {n_chunks}")
            ok = False

    # --- Test 3: looping source never returns None, wraps cleanly ---
    if os.path.exists(tmp_clip):
        src = BackupAudioSource(tmp_clip, sample_rate=48000, channels=1, loop=True)
        chunk_samples = 4800
        n_probe = 50   # more chunks than fit in a 3s clip -- forces at least one wrap
        got_none = False
        for _ in range(n_probe):
            c = src.read_chunk(chunk_samples)
            if c is None:
                got_none = True
                break
        if not got_none:
            print(f"  [PASS] test 3: looping source returns audio across a wraparound "
                  f"({n_probe} chunks pulled from a ~30-chunk clip, no None)")
        else:
            print("  [FAIL] test 3: looping source returned None before loop=False should apply")
            ok = False

    # --- Test 4: --generate is idempotent (skips existing file without --force) ---
    if os.path.exists(tmp_clip):
        mtime_before = os.path.getmtime(tmp_clip)
        time.sleep(0.05)
        generate_backup_clip(output_path=tmp_clip, duration_sec=3.0)
        mtime_after = os.path.getmtime(tmp_clip)
        if mtime_before == mtime_after:
            print("  [PASS] test 4: generate_backup_clip() is idempotent (skips existing file)")
        else:
            print("  [FAIL] test 4: file was rewritten despite already existing and force=False")
            ok = False

    # --- Test 5: mismatched-rate resampling produces the correct sample count ---
    x = np.linspace(-1, 1, 1000, dtype=np.float32)
    y = _resample_mono(x, sr_from=44100, sr_to=48000)
    expected_len = round(1000 * 48000 / 44100)
    if len(y) == expected_len:
        print(f"  [PASS] test 5: _resample_mono 44.1kHz->48kHz gives {len(y)} samples (expected {expected_len})")
    else:
        print(f"  [FAIL] test 5: expected {expected_len} samples, got {len(y)}")
        ok = False

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print("demo/backup_playback.py self-test -- " + ("ALL PASSED" if ok else "FAILURES PRESENT"))
    return ok


def main():
    parser = argparse.ArgumentParser(description="Phase 5.1 -- backup demo playback (pre-recorded audio)")
    parser.add_argument("--generate", action="store_true", help="Build the backup demo clip")
    parser.add_argument("--force", action="store_true", help="Rebuild even if the clip already exists")
    parser.add_argument("--output", default=DEFAULT_CLIP_PATH)
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION_SEC)
    parser.add_argument("--snr", type=float, default=DEFAULT_SNR_DB)
    parser.add_argument("--info", action="store_true", help="Print info about the existing clip")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        ok = _self_test()
        sys.exit(0 if ok else 1)

    if args.generate:
        generate_backup_clip(
            output_path=args.output,
            duration_sec=args.duration,
            target_snr_db=args.snr,
            force=args.force,
        )
        return

    if args.info:
        if not os.path.exists(args.output):
            print(f"No clip at {args.output!r}. Run with --generate first.")
            sys.exit(1)
        info = sf.info(args.output)
        print(f"{args.output}: {info.duration:.1f}s @ {info.samplerate} Hz, {info.channels} ch")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
