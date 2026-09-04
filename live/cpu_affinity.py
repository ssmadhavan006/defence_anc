"""
live/cpu_affinity.py — Thread CPU affinity control (Phase 2, D5).

Only the CALLING thread's affinity can be set this way (os.sched_setaffinity
with pid=0 affects the calling thread, not the whole process) -- see
phase2_plan.md §3.1(b). In this codebase that means it is only meaningful
when called from inside live/pipeline.py's inference thread; PortAudio's
audio callbacks run on its own internal C threads, which are not reachable
from Python this way.

Guarded on hasattr(os, "sched_setaffinity") so this is a clean, silent-except
-for-one-stderr-line no-op on platforms that don't have it (Windows, macOS)
-- the dev machine is Windows, and a disabled/unsupported feature must never
raise and take down the pipeline (same discipline as live/pipeline.py's
lazy-import pattern for residual_filter / reference_nlms).

Usage:
    from live.cpu_affinity import set_thread_affinity
    set_thread_affinity([2, 3])   # best-effort; check the return value if it matters
    set_thread_affinity(None)     # no-op, always returns True

Self-test (Mode A):
    python live/cpu_affinity.py --self-test
"""

import os
import sys


def set_thread_affinity(cores) -> bool:
    """
    Pin the calling thread to the given list of CPU core indices.

    Parameters
    ----------
    cores : list[int] or None
        Core indices to pin to. None means "no pinning requested" and is
        always a successful no-op (matches `pipeline.cpu_affinity: null`,
        today's default behaviour).

    Returns
    -------
    bool
        True if the affinity was applied (or if cores is None). False if
        this platform has no os.sched_setaffinity, or the call failed --
        NEVER raises.
    """
    if cores is None:
        return True

    if not hasattr(os, "sched_setaffinity"):
        print(
            f"[cpu_affinity] os.sched_setaffinity is not available on this "
            f"platform ({sys.platform}); skipping pin to cores={cores}. "
            "This is expected on Windows/macOS and is not an error.",
            file=sys.stderr,
        )
        return False

    try:
        os.sched_setaffinity(0, cores)  # pid=0 -> the calling thread
        return True
    except Exception as exc:
        print(
            f"[cpu_affinity] Failed to set affinity to cores={cores}: {exc}",
            file=sys.stderr,
        )
        return False


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test():
    import platform

    print("live/cpu_affinity.py self-test -- start")

    # --- Test 1: cores=None is always a successful no-op ---
    assert set_thread_affinity(None) is True
    print("  [PASS] test 1: cores=None is a no-op returning True")

    # --- Test 2: platform-appropriate behaviour ---
    if not hasattr(os, "sched_setaffinity"):
        result = set_thread_affinity([0])
        assert result is False, f"expected False on {platform.system()}, got {result}"
        print(f"  [PASS] test 2: graceful no-op on {platform.system()} "
              "(no os.sched_setaffinity) -- did not raise")
    else:
        original = os.sched_getaffinity(0)
        try:
            target = [0]
            ok = set_thread_affinity(target)
            assert ok is True, "expected True on a platform with sched_setaffinity"
            after = os.sched_getaffinity(0)
            assert after == set(target), f"affinity not applied: {after} != {set(target)}"
            print(f"  [PASS] test 2: affinity round-trip via sched_getaffinity ({after})")
        finally:
            os.sched_setaffinity(0, original)

    print("live/cpu_affinity.py self-test -- ALL PASSED")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Thread CPU affinity control (Phase 2, D5)"
    )
    parser.add_argument("--self-test", action="store_true",
                         help="Run Mode A self-test and exit")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
    else:
        parser.print_help()
