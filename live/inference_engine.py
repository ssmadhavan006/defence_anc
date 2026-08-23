"""
live/inference_engine.py â€” DeepFilterNet inference engine for the Phase 5 live pipeline.

Responsibilities:
- Load DeepFilterNet model once at startup and keep it resident in memory.
- Expose a stateless `enhance_chunk(chunk_np)` method suitable for calling from
  the live pipeline's consumer thread.
- Manage warmup passes (eliminate first-run jitter).
- Emit optional per-call timing to stderr when configured to do so.
- Provide a `bypass_chunk(chunk_np)` pass-through for latency baseline testing.

Design constraints:
- No file I/O in the hot path (enhance_chunk / bypass_chunk).
- Accepts numpy float32 arrays; returns numpy float32 arrays.
- Compatible with the df_compat shim used in models/deepfilternet/df_compat.py.
- Python 3.9+ compatible (no X | Y union syntax, no match/case).

Self-test (Mode A â€” dev machine):
    python live/inference_engine.py
"""

import os
import sys
import time
import numpy as np
import torch

# ---------------------------------------------------------------------------
# Import DeepFilterNet via the established df_compat compatibility shim.
# Try the installed package path first (when run from repo root), then fall
# back to local (when run from the live/ directory directly).
# ---------------------------------------------------------------------------
try:
    from models.deepfilternet.df_compat import init_df, enhance
except ImportError:
    # Running from repo root but models/ not on path; add parent.
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from models.deepfilternet.df_compat import init_df, enhance


class InferenceEngine:
    """
    Stateful wrapper around DeepFilterNet for live chunk-by-chunk inference.

    Parameters
    ----------
    sample_rate : int
        Expected audio sample rate. Must match DeepFilterNet's native SR (48 kHz).
    atten_lim_db : float
        Noise attenuation limit passed to df.enhance(). 100 = full suppression.
    warmup_passes : int
        Number of dummy inference calls on startup to warm up JIT / caches.
    log_timing : bool
        If True, print per-call latency (ms) to stderr. Suitable for profiling;
        disable in production.
    """

    NATIVE_SR = 48000  # DeepFilterNet3 only supports 48 kHz

    def __init__(
        self,
        sample_rate: int = 48000,
        atten_lim_db: float = 100.0,
        warmup_passes: int = 3,
        log_timing: bool = False,
    ):
        if sample_rate != self.NATIVE_SR:
            raise ValueError(
                f"InferenceEngine requires sample_rate={self.NATIVE_SR} Hz "
                f"(DeepFilterNet3 native SR). Got {sample_rate}."
            )

        self._sample_rate = sample_rate
        self._atten_lim_db = atten_lim_db
        self._log_timing = log_timing

        print("[InferenceEngine] Loading DeepFilterNet model...", file=sys.stderr)
        t0 = time.perf_counter()
        self._model, self._df_state, suffix = init_df(
            post_filter=False, log_level="ERROR"
        )
        load_time = time.perf_counter() - t0
        print(
            f"[InferenceEngine] Model loaded in {load_time*1000:.1f} ms "
            f"(suffix={suffix})",
            file=sys.stderr,
        )

        # Verify DeepFilterNet's native SR matches what we expect.
        dfn_sr = self._df_state.sr()
        if dfn_sr != self.NATIVE_SR:
            raise RuntimeError(
                f"DeepFilterNet native SR={dfn_sr} != expected {self.NATIVE_SR}"
            )

        self._warmup(warmup_passes)

    # ------------------------------------------------------------------
    # Warmup
    # ------------------------------------------------------------------

    def _warmup(self, n_passes: int) -> None:
        """Run n_passes dummy inference passes to warm up JIT and caches."""
        if n_passes <= 0:
            return
        # Use a 0.1-second silence chunk for warmup (same size as live chunks).
        dummy_samples = int(self._sample_rate * 0.1)
        dummy_np = np.zeros((1, dummy_samples), dtype=np.float32)
        dummy_tensor = torch.from_numpy(dummy_np)

        print(
            f"[InferenceEngine] Running {n_passes} warmup passes...", file=sys.stderr
        )
        t0 = time.perf_counter()
        for _ in range(n_passes):
            enhance(
                self._model,
                self._df_state,
                dummy_tensor,
                pad=True,
                atten_lim_db=self._atten_lim_db,
            )
        warmup_ms = (time.perf_counter() - t0) * 1000
        print(
            f"[InferenceEngine] Warmup complete ({warmup_ms:.1f} ms total).",
            file=sys.stderr,
        )

    # ------------------------------------------------------------------
    # Hot path â€” enhance_chunk
    # ------------------------------------------------------------------

    def enhance_chunk(self, chunk: np.ndarray) -> np.ndarray:
        """
        Enhance a single audio chunk through DeepFilterNet.

        Parameters
        ----------
        chunk : np.ndarray
            Shape (n_samples,) mono or (1, n_samples).
            Must be float32. Must NOT be empty.

        Returns
        -------
        np.ndarray
            Enhanced audio, shape (1, n_samples_out), float32.
            n_samples_out may differ slightly from n_samples when pad=True.
        """
        chunk = np.asarray(chunk, dtype=np.float32)
        if chunk.ndim == 1:
            chunk = chunk[np.newaxis, :]          # (n,) â†’ (1, n)
        elif chunk.ndim == 2 and chunk.shape[0] != 1:
            # Take first channel only if multi-channel was inadvertently passed.
            chunk = chunk[:1, :]

        audio_tensor = torch.from_numpy(chunk)

        if self._log_timing:
            t0 = time.perf_counter()

        enhanced = enhance(
            self._model,
            self._df_state,
            audio_tensor,
            pad=True,
            atten_lim_db=self._atten_lim_db,
        )

        if self._log_timing:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            n_samples = chunk.shape[-1]
            audio_dur_ms = n_samples / self._sample_rate * 1000
            rtf = elapsed_ms / audio_dur_ms if audio_dur_ms > 0 else 0.0
            print(
                f"[InferenceEngine] enhance_chunk: {elapsed_ms:.2f} ms "
                f"({audio_dur_ms:.1f} ms audio, RTF={rtf:.4f})",
                file=sys.stderr,
            )

        return enhanced.cpu().detach().numpy()

    # ------------------------------------------------------------------
    # Bypass path (latency baseline)
    # ------------------------------------------------------------------

    def bypass_chunk(self, chunk: np.ndarray) -> np.ndarray:
        """
        Pass the audio chunk through without processing.

        Used to establish a raw I/O latency baseline that excludes model
        inference time. Keeps the same input/output contract as enhance_chunk.
        """
        chunk = np.asarray(chunk, dtype=np.float32)
        if chunk.ndim == 1:
            chunk = chunk[np.newaxis, :]
        elif chunk.ndim == 2 and chunk.shape[0] != 1:
            chunk = chunk[:1, :]
        return chunk.copy()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def atten_lim_db(self) -> float:
        return self._atten_lim_db


# ---------------------------------------------------------------------------
# Self-test (Mode A â€” runs on dev machine without physical audio hardware)
# ---------------------------------------------------------------------------

def _self_test():
    print("=== InferenceEngine self-test (Mode A â€” dev machine) ===")

    SR = 48000
    CHUNK_SEC = 0.1
    chunk_samples = int(SR * CHUNK_SEC)

    # --- Test 1: Engine initialises and warms up ---
    engine = InferenceEngine(
        sample_rate=SR,
        atten_lim_db=100.0,
        warmup_passes=3,
        log_timing=True,
    )
    print("[PASS] test 1: engine initialised and warmed up")

    # --- Test 2: bypass_chunk preserves shape and dtype ---
    mono_chunk = np.random.randn(chunk_samples).astype(np.float32)
    out_bypass = engine.bypass_chunk(mono_chunk)
    assert out_bypass.shape == (1, chunk_samples), (
        f"bypass shape wrong: {out_bypass.shape}"
    )
    assert out_bypass.dtype == np.float32
    np.testing.assert_allclose(out_bypass[0], mono_chunk, atol=1e-6)
    print(f"[PASS] test 2: bypass_chunk shape {out_bypass.shape}, dtype {out_bypass.dtype}")

    # --- Test 3: enhance_chunk runs without error on silence ---
    silence = np.zeros(chunk_samples, dtype=np.float32)
    out_silence = engine.enhance_chunk(silence)
    assert out_silence.ndim == 2, f"expected 2-D output, got shape {out_silence.shape}"
    assert out_silence.dtype == np.float32
    assert out_silence.shape[-1] >= chunk_samples, (
        f"output shorter than input: {out_silence.shape[-1]} < {chunk_samples}"
    )
    print(f"[PASS] test 3: enhance_chunk on silence â†’ shape {out_silence.shape}")

    # --- Test 4: enhance_chunk on white noise (checks no NaN/Inf) ---
    noise_chunk = (np.random.randn(chunk_samples) * 0.1).astype(np.float32)
    out_noise = engine.enhance_chunk(noise_chunk)
    assert not np.any(np.isnan(out_noise)), "NaN in output"
    assert not np.any(np.isinf(out_noise)), "Inf in output"
    print(f"[PASS] test 4: enhance_chunk on white noise â†’ no NaN/Inf, shape {out_noise.shape}")

    # --- Test 5: enhance_chunk on speech-like sine tone ---
    t = np.linspace(0, CHUNK_SEC, chunk_samples, dtype=np.float32)
    speech_like = (np.sin(2 * np.pi * 300 * t) * 0.5).astype(np.float32)
    out_speech = engine.enhance_chunk(speech_like)
    assert out_speech.shape[-1] >= chunk_samples
    print(f"[PASS] test 5: enhance_chunk on 300 Hz sine â†’ shape {out_speech.shape}")

    # --- Test 6: latency profile over 10 calls ---
    latencies = []
    for _ in range(10):
        chunk = np.random.randn(chunk_samples).astype(np.float32) * 0.05
        t0 = time.perf_counter()
        engine.enhance_chunk(chunk)
        latencies.append(time.perf_counter() - t0)

    latencies_ms = np.array(latencies) * 1000.0
    audio_dur_ms = CHUNK_SEC * 1000.0
    rtf_vals = latencies_ms / audio_dur_ms
    print(
        f"[PASS] test 6: 10-call latency profile\n"
        f"         median={np.median(latencies_ms):.2f} ms, "
        f"p95={np.percentile(latencies_ms, 95):.2f} ms, "
        f"median_RTF={np.median(rtf_vals):.4f}"
    )

    print("=== InferenceEngine self-test â€” ALL PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(_self_test())
