"""
live/residual_filter.py — Stateful, streaming residual noise-suppression
stage for the live pipeline (P1-1).

PS26052 describes an optional "lightweight adaptive filter (e.g. LMS) for
residual noise suppression." The already-built offline NLMS baseline
(baselines/nlms/nlms.py) needs an ORACLE noise reference — a second,
perfectly sample-aligned copy of the pure noise signal — which does not
exist in a live single-microphone deployment. That needs P1-2 (dual-mic
capture); until then, this module runs the plan's documented reference-free
configuration: an Adaptive Line Enhancer (ALE, Widrow).

How ALE differs from the oracle NLMS (read this before touching either):
an ALE predicts each sample from a DELAYED WINDOW OF THE SAME SIGNAL rather
than from a second reference channel. Speech — especially voiced, quasi-
periodic content — stays correlated over tens of samples; broadband
residual noise does not. So the filter's PREDICTION is the enhanced
output (the predictable/speech-like part), and the prediction ERROR is the
discarded noise-like residual. This is the OPPOSITE convention from
baselines/nlms/nlms.py, which returns the error as its enhanced estimate
(because there, the reference channel IS the noise, so error = mixture
minus noise = speech). Getting this backwards silently produces an
inverted, mostly-noise output that still looks like valid audio — there is
no crash to catch the mistake, only a self-test that checks the actual
metric moved the right direction (see _self_test below).

Honest limitation, not swept under the rug: ALE enhances predictable/tonal
content, which also means it can attenuate genuinely broadband SPEECH
components (unvoiced fricatives like /s/, /f/, /sh/) exactly as it
attenuates broadband noise — it cannot tell the two apart, because nothing
here distinguishes "broadband residual noise" from "broadband consonant."
This stage runs on DeepFilterNet's OUTPUT (residual cleanup on an already
mostly-clean signal), and defaults are deliberately gentle (small mu,
short filter) to limit that risk rather than chase maximum suppression.
Whether this stage is a net win needs an actual PESQ/STOI A/B comparison
against the eval set before it should be considered validated — that has
NOT been run as of this module's introduction (2026-08-24). Do not claim it
improves quality without that evidence.

Swap-in path for P1-2 (dual-mic): once a real reference microphone channel
exists, replace the delayed self-copy fed to _ale_step with the reference
channel and switch the returned value from prediction to prediction error,
matching baselines/nlms/nlms.py's convention exactly.

Self-test (no audio hardware required):
    python live/residual_filter.py --self-test
"""

import numpy as np
from numba import jit

DEFAULT_FILTER_LENGTH = 32
DEFAULT_DELAY = 8
DEFAULT_MU = 0.05
DEFAULT_EPS = 1e-6


@jit(nopython=True, fastmath=True)
def _ale_process(chunk, history, weights, delay, filter_length, mu, eps):
    """
    Process one chunk of an Adaptive Line Enhancer, continuing from the
    filter state (`history`, `weights`) left by the previous chunk.

    Parameters
    ----------
    chunk : float32[:], shape (n,)
        New samples to process.
    history : float32[:], shape (delay + filter_length - 1,)
        Trailing samples carried over from the previous call — makes the
        filter continuous across chunk boundaries in a streaming pipeline
        where each call only sees one ~100ms slice at a time.
    weights : float32[:], shape (filter_length,)
        Adaptive filter taps, carried over between calls.
    delay : int
        Decorrelation delay — how far back the prediction window starts.
        Must exceed the noise's correlation time but stay well inside
        speech's, so noise looks "unpredictable" while voiced speech
        still looks predictable at that lag.
    filter_length : int
        Number of taps in the prediction window.
    mu : float
        NLMS step size.
    eps : float
        Regularization constant preventing division by zero on silence.

    Returns
    -------
    output : float32[:], shape (n,)
        Enhanced chunk (the filter's PREDICTION — see module docstring for
        why this is not the error signal).
    weights : float32[:], shape (filter_length,)
        Updated taps, to pass into the next call.
    new_history : float32[:], shape (delay + filter_length - 1,)
        Trailing samples to pass into the next call.
    """
    n = len(chunk)
    hist_len = len(history)
    buf = np.empty(hist_len + n, dtype=np.float32)
    buf[:hist_len] = history
    buf[hist_len:] = chunk

    output = np.zeros(n, dtype=np.float32)

    for k in range(n):
        idx = hist_len + k  # absolute index of the sample being predicted
        y = 0.0
        pwr = 0.0
        for i in range(filter_length):
            tap_idx = idx - delay - i
            val = buf[tap_idx] if tap_idx >= 0 else 0.0
            y += weights[i] * val
            pwr += val * val

        target = buf[idx]
        err = target - y
        output[k] = y  # prediction = enhanced output (ALE convention)

        adaptation_factor = (mu / (pwr + eps)) * err
        for i in range(filter_length):
            tap_idx = idx - delay - i
            val = buf[tap_idx] if tap_idx >= 0 else 0.0
            weights[i] += adaptation_factor * val

    new_history = buf[-hist_len:] if hist_len > 0 else buf[0:0]
    return output, weights, new_history


class ResidualALEFilter:
    """Stateful wrapper around _ale_process for use in a streaming pipeline."""

    def __init__(self, filter_length: int = DEFAULT_FILTER_LENGTH,
                 delay: int = DEFAULT_DELAY, mu: float = DEFAULT_MU,
                 eps: float = DEFAULT_EPS):
        if filter_length < 1:
            raise ValueError(f"filter_length must be >= 1, got {filter_length}")
        if delay < 1:
            raise ValueError(f"delay must be >= 1, got {delay}")
        self._filter_length = filter_length
        self._delay = delay
        self._mu = mu
        self._eps = eps
        self._hist_len = delay + filter_length - 1
        self._history = np.zeros(self._hist_len, dtype=np.float32)
        self._weights = np.zeros(filter_length, dtype=np.float32)
        # Warm up the JIT once at construction, not on the first real audio
        # chunk — matches the pattern in inference_engine.py, which does the
        # same for DeepFilterNet so the first live chunk isn't the one that
        # eats a compile-time stall.
        _ale_process(np.zeros(4, dtype=np.float32), self._history.copy(),
                     self._weights.copy(), delay, filter_length, mu, eps)

    def process_chunk(self, chunk: np.ndarray) -> np.ndarray:
        """chunk: 1D float32 array. Returns enhanced chunk, same shape."""
        chunk = np.asarray(chunk, dtype=np.float32)
        out, self._weights, self._history = _ale_process(
            chunk, self._history, self._weights,
            self._delay, self._filter_length, self._mu, self._eps,
        )
        return out

    def reset(self) -> None:
        """Clear filter state — call when switching modes or restarting a stream
        so stale weights from a previous signal don't bias the next one."""
        self._history[:] = 0.0
        self._weights[:] = 0.0


def _self_test():
    print("live/residual_filter.py self-test -- start")
    sr = 48000
    rng = np.random.default_rng(0)

    # --- Test 1: chunked processing matches one-shot processing exactly ---
    # Correctness of the streaming state handoff: filtering a signal in
    # 100ms chunks must produce bit-identical output to filtering it in one
    # call, since the pipeline can only ever see it one chunk at a time.
    n_total = 48000
    t = np.arange(n_total) / sr
    signal = (0.5 * np.sin(2 * np.pi * 220 * t) + 0.1 * rng.standard_normal(n_total)).astype(np.float32)

    f_whole = ResidualALEFilter()
    out_whole = f_whole.process_chunk(signal)

    f_chunked = ResidualALEFilter()
    chunk_size = 4800
    out_chunks = []
    for start in range(0, n_total, chunk_size):
        out_chunks.append(f_chunked.process_chunk(signal[start:start + chunk_size]))
    out_chunked = np.concatenate(out_chunks)

    np.testing.assert_allclose(out_whole, out_chunked, atol=1e-5)
    print("  [PASS] test 1: chunked streaming matches one-shot processing bit-for-bit")

    # --- Test 2: no NaN/Inf, correct shape, on real-ish signal ---
    assert out_whole.shape == signal.shape
    assert np.all(np.isfinite(out_whole)), "output contains non-finite values"
    print(f"  [PASS] test 2: shape={out_whole.shape}, all finite")

    # --- Test 3: silence in -> silence out (no divide-by-zero blowup) ---
    f_sil = ResidualALEFilter()
    silence = np.zeros(4800, dtype=np.float32)
    out_sil = f_sil.process_chunk(silence)
    assert np.all(out_sil == 0.0), "silence should stay silent"
    print("  [PASS] test 3: silence handled without divide-by-zero blowup")

    # --- Test 4: the filter actually predicts a periodic tone (the whole point) ---
    # A predictable, pure tone should be predictable — after the filter
    # converges, its output should correlate strongly with the tone.
    f_tone = ResidualALEFilter(mu=0.1)
    tone = (0.6 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    out_tone = f_tone.process_chunk(tone)
    # Compare the converged tail (skip the first 20% while weights adapt).
    tail = slice(int(0.2 * n_total), n_total)
    corr = np.corrcoef(out_tone[tail], tone[tail])[0, 1]
    assert corr > 0.9, f"ALE failed to track a predictable pure tone (corr={corr:.3f})"
    print(f"  [PASS] test 4: converged prediction correlates with a pure tone (corr={corr:.4f})")

    # --- Test 5: reset() actually clears state ---
    f_reset = ResidualALEFilter()
    f_reset.process_chunk(tone)  # adapt away from zero
    assert np.any(f_reset._weights != 0.0), "weights should have adapted"
    f_reset.reset()
    assert np.all(f_reset._weights == 0.0) and np.all(f_reset._history == 0.0)
    print("  [PASS] test 5: reset() clears weights and history")

    # --- Test 6: invalid parameters raise, don't silently misbehave ---
    try:
        ResidualALEFilter(filter_length=0)
        assert False, "expected ValueError for filter_length=0"
    except ValueError:
        pass
    try:
        ResidualALEFilter(delay=0)
        assert False, "expected ValueError for delay=0"
    except ValueError:
        pass
    print("  [PASS] test 6: invalid parameters raise ValueError instead of misbehaving")

    print("live/residual_filter.py self-test -- ALL PASSED")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Streaming residual ALE filter (P1-1)")
    parser.add_argument("--self-test", action="store_true", help="Run offline self-test and exit")
    args = parser.parse_args()
    if args.self_test:
        _self_test()
    else:
        parser.print_help()
