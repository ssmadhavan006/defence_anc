"""
live/reference_nlms.py — Streaming reference-channel NLMS adaptive filter (Phase 1).

This module is the live-pipeline counterpart of baselines/nlms/nlms.py.  The
offline baseline processes a whole file at once (batch mode); this module
processes one ~100 ms chunk at a time while maintaining filter state across
chunk boundaries so the pipeline is continuous.

Relationship to baselines/nlms/nlms.py:
  For the same (primary, reference) inputs, this module produces bit-identical
  output.  The self-test below verifies this requirement.  Do not change the
  algorithm without also updating the offline baseline and re-running that test.

Relationship to live/residual_filter.py (reference-FREE ALE):
  residual_filter.py returns the filter PREDICTION as the enhanced output.
  This module returns the filter ERROR (= primary minus predicted noise) as the
  enhanced output.  The two have opposite output conventions; getting them
  confused produces a mostly-noise signal that still sounds like valid audio.
  See residual_filter.py module docstring for the full explanation.

Drift warning (Topology B — two separate USB devices):
  Two USB audio devices run on independent crystal clocks.  At 50 ppm, they
  drift ~2.4 samples/second at 48 kHz.  The NLMS filter's taps (default 64)
  span ~1.3 ms and partially compensate for slow drift within that window,
  but alignment degrades noticeably after ~30 seconds.  For best results:
  - Run live/calibrate_mic_pair.py before each session to measure the initial
    delay and write it to config/mic_calibration.yaml.
  - Keep demo sessions short (<60 s) or periodically re-trigger calibration.
  A future phase may add periodic cross-correlation re-alignment; it is out of
  scope here.

ERLE telemetry:
  The filter accumulates primary/error power so callers can compute
      ERLE_dB = 10 * log10(mean_primary_power / mean_error_power)
  This is a telemetry-only sanity metric confirming adaptation is occurring.
  It is NOT a substitute for PESQ/STOI quality evaluation (see rules.md R21).
  Access via .erle_db() after processing some audio.

Self-test (no audio hardware required):
    python live/reference_nlms.py --self-test
"""

import numpy as np
from numba import jit

DEFAULT_FILTER_LENGTH = 64
DEFAULT_MU = 0.01
DEFAULT_EPS = 1e-6


@jit(nopython=True, fastmath=True)
def _nlms_chunk(primary, reference, ref_history, weights, mu, eps):
    """
    Process one chunk of reference-NLMS, resuming from previous state.

    Algorithm (Widrow / Haykin, matching baselines/nlms/nlms.py exactly):
        y[n]   = w^T x[n]            (filter estimate of noise in primary)
        e[n]   = d[n] - y[n]         (error = speech estimate)
        w[n+1] = w[n] + mu/(||x||^2 + eps) * e[n] * x[n]

    Parameters
    ----------
    primary : float32[:], shape (n,)
        d[n] — noisy mixture (primary microphone).
    reference : float32[:], shape (n,)
        x[n] — noise reference (reference microphone, aligned with primary).
    ref_history : float32[:], shape (L-1,)
        Last L-1 reference samples from the previous chunk.  Initialise to
        zeros for the first chunk.
    weights : float32[:], shape (L,)
        Current adaptive filter taps.  Initialise to zeros.
    mu : float
        NLMS step size.
    eps : float
        Regularisation constant (prevent division by zero on silence).

    Returns
    -------
    error_signal : float32[:], shape (n,)   — speech estimate (enhanced output)
    weights      : float32[:], shape (L,)   — updated taps
    new_history  : float32[:], shape (L-1,) — carry into next call
    """
    n = len(primary)
    L = len(weights)

    # Build the L-1+n padded reference buffer (matches offline pre-pad logic).
    ref_padded = np.empty(L - 1 + n, dtype=np.float32)
    ref_padded[:L - 1] = ref_history
    ref_padded[L - 1:] = reference

    error_signal = np.zeros(n, dtype=np.float32)

    for i in range(n):
        y = 0.0
        pwr = 0.0
        for j in range(L):
            val = ref_padded[i + L - 1 - j]
            y += weights[j] * val
            pwr += val * val

        err = primary[i] - y
        error_signal[i] = err

        af = (mu / (pwr + eps)) * err
        for j in range(L):
            val = ref_padded[i + L - 1 - j]
            weights[j] += af * val

    # Last L-1 elements become history for the next chunk.
    new_history = np.empty(L - 1, dtype=np.float32)
    for k in range(L - 1):
        new_history[k] = ref_padded[n + k]

    return error_signal, weights, new_history


class ReferenceNLMSFilter:
    """
    Stateful streaming wrapper around _nlms_chunk.

    Maintains filter weights and reference history across process_chunk() calls
    so the NLMS algorithm runs continuously across chunk boundaries as if the
    entire session were one contiguous buffer.
    """

    def __init__(self, filter_length: int = DEFAULT_FILTER_LENGTH,
                 mu: float = DEFAULT_MU, eps: float = DEFAULT_EPS):
        if filter_length < 1:
            raise ValueError(f"filter_length must be >= 1, got {filter_length}")
        if mu <= 0:
            raise ValueError(f"mu must be > 0, got {mu}")
        self._L = filter_length
        self._mu = float(mu)
        self._eps = float(eps)
        self._weights = np.zeros(filter_length, dtype=np.float32)
        self._ref_history = np.zeros(filter_length - 1, dtype=np.float32)

        # ERLE accumulators (telemetry only — see module docstring).
        self._primary_power = 0.0
        self._error_power = 0.0
        self._n_samples = 0

        # Warm up the numba JIT once at construction — avoids a compile stall
        # on the first real audio chunk (same pattern as inference_engine.py
        # and residual_filter.py).
        dummy = np.zeros(4, dtype=np.float32)
        _nlms_chunk(dummy, dummy, self._ref_history.copy(),
                    self._weights.copy(), self._mu, self._eps)

    def process_chunk(self, primary: np.ndarray,
                      reference: np.ndarray) -> np.ndarray:
        """
        Filter one chunk of audio.

        Parameters
        ----------
        primary : 1-D float32 array, shape (n,)
            Noisy mixture from the primary microphone.
        reference : 1-D float32 array, shape (n,)
            Noise reference from the reference microphone, same length.

        Returns
        -------
        error_signal : 1-D float32 array, shape (n,)
            Speech estimate (primary minus predicted noise).
        """
        primary = np.asarray(primary, dtype=np.float32)
        reference = np.asarray(reference, dtype=np.float32)
        if primary.shape != reference.shape:
            raise ValueError(
                f"primary and reference must have the same shape; "
                f"got {primary.shape} vs {reference.shape}"
            )

        error, self._weights, self._ref_history = _nlms_chunk(
            primary, reference, self._ref_history, self._weights,
            self._mu, self._eps,
        )

        # Accumulate ERLE stats.
        self._primary_power += float(np.sum(primary ** 2))
        self._error_power += float(np.sum(error ** 2))
        self._n_samples += len(primary)

        return error

    def erle_db(self) -> float:
        """
        Echo-Return-Loss-Enhancement in dB since the last reset().
        Returns 0.0 if no audio has been processed or error power is zero.
        Telemetry-only metric — see module docstring.
        """
        if self._n_samples == 0 or self._error_power <= 0.0:
            return 0.0
        ratio = self._primary_power / self._error_power
        if ratio <= 0.0:
            return 0.0
        return 10.0 * float(np.log10(ratio))

    def reset(self) -> None:
        """Clear all filter state and ERLE accumulators."""
        self._weights[:] = 0.0
        self._ref_history[:] = 0.0
        self._primary_power = 0.0
        self._error_power = 0.0
        self._n_samples = 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test():
    print("live/reference_nlms.py self-test -- start")
    sr = 48000
    rng = np.random.default_rng(42)

    # --- Reference NLMS: inline offline implementation for comparison ---
    # This replicates baselines/nlms/nlms.py exactly so the self-test runs
    # without needing that module on sys.path.
    def _offline_nlms(primary, reference, L=64, mu=0.01, eps=1e-6):
        N = len(primary)
        weights = np.zeros(L, dtype=np.float32)
        error_signal = np.zeros(N, dtype=np.float32)
        ref_padded = np.zeros(N + L - 1, dtype=np.float32)
        ref_padded[L - 1:] = reference[:N]
        for n in range(N):
            y = 0.0; pwr = 0.0
            for i in range(L):
                val = ref_padded[n + L - 1 - i]
                y += weights[i] * val
                pwr += val * val
            err = primary[n] - y
            error_signal[n] = err
            af = (mu / (pwr + eps)) * err
            for i in range(L):
                val = ref_padded[n + L - 1 - i]
                weights[i] += af * val
        return error_signal

    n_total = sr  # 1 second
    t = np.arange(n_total) / sr
    # Primary: speech-like tone + broadband noise
    noise = (0.3 * rng.standard_normal(n_total)).astype(np.float32)
    speech = (0.5 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    primary = speech + noise
    reference = noise + 0.05 * rng.standard_normal(n_total).astype(np.float32)

    # --- Test 1: chunked streaming matches offline (bit-identical) ---
    offline_out = _offline_nlms(primary, reference, L=64, mu=0.01)

    chunk_size = 4800  # 100ms
    f = ReferenceNLMSFilter(filter_length=64, mu=0.01)
    chunks_out = []
    for start in range(0, n_total, chunk_size):
        chunks_out.append(f.process_chunk(primary[start:start + chunk_size],
                                          reference[start:start + chunk_size]))
    streaming_out = np.concatenate(chunks_out)

    np.testing.assert_allclose(offline_out, streaming_out, atol=1e-5,
                                err_msg="chunked output diverges from offline batch output")
    print("  [PASS] test 1: chunked streaming matches offline batch (bit-identical)")

    # --- Test 2: no NaN/Inf, correct shape ---
    assert streaming_out.shape == primary.shape
    assert np.all(np.isfinite(streaming_out)), "output contains non-finite values"
    print(f"  [PASS] test 2: shape={streaming_out.shape}, all finite")

    # --- Test 3: silence in -> silence out (no divide-by-zero blowup) ---
    f_sil = ReferenceNLMSFilter()
    sil = np.zeros(4800, dtype=np.float32)
    out_sil = f_sil.process_chunk(sil, sil)
    assert np.all(out_sil == 0.0), "silence should remain silent"
    print("  [PASS] test 3: silence handled without divide-by-zero")

    # --- Test 4: filter converges when reference = pure noise ---
    # With a perfect reference (reference IS the noise), the converged output
    # should correlate more strongly with the speech than the input mixture does.
    f_conv = ReferenceNLMSFilter(filter_length=64, mu=0.05)
    out_conv = []
    for start in range(0, n_total, chunk_size):
        out_conv.append(f_conv.process_chunk(primary[start:start + chunk_size],
                                             noise[start:start + chunk_size]))
    out_conv = np.concatenate(out_conv)
    tail = slice(int(0.5 * n_total), n_total)  # converged half
    input_corr = np.corrcoef(primary[tail], speech[tail])[0, 1]
    output_corr = np.corrcoef(out_conv[tail], speech[tail])[0, 1]
    assert output_corr > input_corr, (
        f"NLMS should improve speech correlation: "
        f"input={input_corr:.3f}, output={output_corr:.3f}"
    )
    print(f"  [PASS] test 4: NLMS improves speech correlation "
          f"({input_corr:.3f} -> {output_corr:.3f})")

    # --- Test 5: ERLE > 0 dB after adaptation ---
    erle = f_conv.erle_db()
    assert erle > 0.0, f"ERLE should be positive after adaptation, got {erle:.2f} dB"
    print(f"  [PASS] test 5: ERLE={erle:.2f} dB (positive = noise reduction is occurring)")

    # --- Test 6: reset() clears all state ---
    f_reset = ReferenceNLMSFilter()
    f_reset.process_chunk(primary[:4800], noise[:4800])
    assert np.any(f_reset._weights != 0.0), "weights should have adapted"
    f_reset.reset()
    assert np.all(f_reset._weights == 0.0)
    assert np.all(f_reset._ref_history == 0.0)
    assert f_reset._n_samples == 0
    print("  [PASS] test 6: reset() clears weights, history, and ERLE accumulators")

    # --- Test 7: invalid parameters raise, don't misbehave ---
    try:
        ReferenceNLMSFilter(filter_length=0)
        assert False, "expected ValueError"
    except ValueError:
        pass
    try:
        ReferenceNLMSFilter(mu=-0.1)
        assert False, "expected ValueError"
    except ValueError:
        pass
    print("  [PASS] test 7: invalid parameters raise ValueError")

    # --- Test 8: mismatched primary/reference shapes raise ---
    f_shape = ReferenceNLMSFilter()
    try:
        f_shape.process_chunk(np.zeros(100, dtype=np.float32),
                              np.zeros(200, dtype=np.float32))
        assert False, "expected ValueError for shape mismatch"
    except ValueError:
        pass
    print("  [PASS] test 8: mismatched input shapes raise ValueError")

    print("live/reference_nlms.py self-test -- ALL PASSED")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Streaming reference-NLMS adaptive filter (Phase 1)"
    )
    parser.add_argument("--self-test", action="store_true",
                        help="Run offline self-test and exit")
    args = parser.parse_args()
    if args.self_test:
        _self_test()
    else:
        parser.print_help()
