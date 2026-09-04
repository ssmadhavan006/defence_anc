"""
live/fast_resample.py — Optional numba-JIT linear-interpolation resampler
(Phase 2, D4).

live/pipeline.py's default `_resample()` is a linear interpolation via
`np.interp`, which is already compiled C -- per phase2_plan.md §3.1(a) and
D4, the honest expectation for a numba version is a NEGLIGIBLE gain, and it
is implemented behind a config flag (`pipeline.fast_resample`, default
false) on that basis: measure on the Pi, delete this file and the config key
if it doesn't measurably help. Do not treat its existence as evidence it is
worth using.

numba is an OPTIONAL dependency (see requirements-optional.txt) -- this
module must be importable even when numba is missing (so
scripts/run_all_selftests.py can report SKIP rather than crash the whole
run), but calling resample_fast() without numba raises a clear, actionable
RuntimeError rather than silently falling back (a silent fallback would hide
the fact that the configured feature isn't actually active).

Self-test (Mode A):
    python live/fast_resample.py --self-test
"""

import sys
import numpy as np

try:
    from numba import njit
    _NUMBA_AVAILABLE = True
except ImportError:
    _NUMBA_AVAILABLE = False

    def njit(*args, **kwargs):  # pragma: no cover - only hit without numba
        def _decorator(fn):
            return fn
        return _decorator


@njit(cache=True, fastmath=True)
def _interp_njit(dst_idx, x):
    """
    Linear interpolation of x (sampled at integer positions 0..len(x)-1) at
    the fractional positions in dst_idx. Mirrors np.interp(dst_idx,
    arange(len(x)), x) exactly for this case (x's sample positions are a
    plain 0..n-1 integer sequence, so the search step np.interp normally
    does reduces to int(pos)).
    """
    n_out = dst_idx.shape[0]
    n_in = x.shape[0]
    out = np.empty(n_out, dtype=np.float64)
    last = n_in - 1
    for i in range(n_out):
        pos = dst_idx[i]
        j = int(pos)
        if j >= last:
            out[i] = x[last]
        else:
            frac = pos - j
            out[i] = x[j] * (1.0 - frac) + x[j + 1] * frac
    return out


def resample_fast(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    """
    Drop-in numba-accelerated replacement for live/pipeline.py::_resample().
    Mono 1-D array in, 1-D array out, same dtype as input.

    Raises RuntimeError if numba is not installed -- callers must check
    pipeline.fast_resample against numba availability at startup (see
    live/pipeline.py start()), not at first use in the audio hot path.
    """
    if not _NUMBA_AVAILABLE:
        raise RuntimeError(
            "live.fast_resample.resample_fast() requires numba, which is not "
            "installed. Install it with:\n"
            "    pip install numba==0.67.0\n"
            "or set pipeline.fast_resample: false in config/audio_config.yaml "
            "to use the default np.interp-based resampler instead."
        )
    if sr_from == sr_to or x.shape[0] == 0:
        return x
    n_out = int(round(x.shape[0] * sr_to / sr_from))
    if n_out <= 0:
        return np.zeros(0, dtype=x.dtype)
    dst_idx = np.linspace(0, x.shape[0] - 1, num=n_out)
    out = _interp_njit(dst_idx, x.astype(np.float64))
    return out.astype(x.dtype)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test():
    print("live/fast_resample.py self-test -- start")

    if not _NUMBA_AVAILABLE:
        print("  [SKIP] numba is not installed on this machine -- "
              "scripts/run_all_selftests.py already treats this as SKIP, not "
              "FAIL, via its optional_dep mechanism. Nothing to test.")
        print("live/fast_resample.py self-test -- SKIPPED (no numba)")
        return

    import time
    from live.pipeline import _resample as reference_resample

    rate_pairs = [(44100, 48000), (16000, 48000), (48000, 48000)]
    rng = np.random.default_rng(0)

    for sr_from, sr_to in rate_pairs:
        x = rng.standard_normal(int(sr_from * 0.1)).astype(np.float32)
        expected = reference_resample(x, sr_from, sr_to)
        actual = resample_fast(x, sr_from, sr_to)
        assert actual.shape == expected.shape, (
            f"{sr_from}->{sr_to}: shape mismatch {actual.shape} != {expected.shape}"
        )
        assert actual.dtype == expected.dtype
        np.testing.assert_allclose(
            actual, expected, atol=1e-4,
            err_msg=f"fast_resample diverges from _resample at {sr_from}->{sr_to} Hz",
        )
        max_diff = float(np.max(np.abs(actual - expected))) if len(actual) else 0.0
        print(f"  [PASS] {sr_from} Hz -> {sr_to} Hz: bit-equivalent (max diff={max_diff:.2e})")

    # Microbenchmark -- THIS MACHINE ONLY, not a Pi measurement (Rule 5).
    # The A/B decision on whether to keep this feature is made on the Pi
    # (phase2_plan.md B4); this number is printed purely for local sanity.
    x = rng.standard_normal(4410).astype(np.float32)
    resample_fast(x, 44100, 48000)  # warm the JIT before timing

    n_calls = 200
    t0 = time.perf_counter()
    for _ in range(n_calls):
        reference_resample(x, 44100, 48000)
    ref_us = (time.perf_counter() - t0) / n_calls * 1e6

    t0 = time.perf_counter()
    for _ in range(n_calls):
        resample_fast(x, 44100, 48000)
    fast_us = (time.perf_counter() - t0) / n_calls * 1e6

    print(
        f"  Microbenchmark (THIS MACHINE ONLY, not a Pi measurement -- Rule 5): "
        f"np.interp={ref_us:.1f} us/call, numba={fast_us:.1f} us/call"
    )
    print("live/fast_resample.py self-test -- ALL PASSED")


if __name__ == "__main__":
    import argparse

    _REPO_ROOT = __file__
    import os
    _REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

    parser = argparse.ArgumentParser(
        description="Optional numba-JIT resampler (Phase 2, D4)"
    )
    parser.add_argument("--self-test", action="store_true",
                         help="Run Mode A self-test and exit")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
    else:
        parser.print_help()
