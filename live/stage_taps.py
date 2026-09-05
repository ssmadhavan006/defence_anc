"""
live/stage_taps.py — Per-stage audio taps for dashboard visibility.

Generalises the existing last_in_chunk / last_out_chunk pattern in
live/pipeline.py (single atomic assignment, no lock, no allocation) to the
five real per-chunk stage boundaries inside LivePipeline._inference_loop:

  capture    — raw mono chunk straight off the mic (or backup source)
  pre_filter — mono chunk just before the DeepFilterNet3 call. Equals
               `capture` unless pipeline.reference_nlms is enabled with
               stage="pre_dfn", in which case it reflects that filter's output.
  dfn_core   — DeepFilterNet3's raw output, before any post-processing stage.
  residual   — output of the P1-1 residual ALE filter, only when
               pipeline.residual_filter is enabled.
  output     — the final chunk written to the output ring buffer (identical
               to pipeline.last_out_chunk).

A stage's attribute stays None when that stage doesn't run this session
(e.g. `residual` when residual_filter is disabled) -- this is what lets the
dashboard grey out a stage honestly instead of drawing a fake pass-through
value. Written with a single Python assignment (atomic under CPython's GIL),
exactly like last_in_chunk/last_out_chunk -- read/write races are benign
because these are display-only, never used for an audio-path decision.
"""

STAGE_NAMES = ("capture", "pre_filter", "dfn_core", "residual", "output")


class StageTaps:
    """Holds the most recent chunk (or None) for each named pipeline stage."""

    def __init__(self):
        for name in STAGE_NAMES:
            setattr(self, name, None)

    def snapshot(self) -> dict:
        """Return {stage_name: ndarray_or_None} for the current instant."""
        return {name: getattr(self, name) for name in STAGE_NAMES}


def _self_test():
    print("live/stage_taps.py self-test -- start")
    import numpy as np

    taps = StageTaps()
    assert all(getattr(taps, n) is None for n in STAGE_NAMES), "all stages must start None"
    print("  [PASS] test 1: fresh StageTaps has every stage None")

    chunk = np.ones(4800, dtype=np.float32)
    taps.capture = chunk
    taps.dfn_core = chunk * 0.5
    snap = taps.snapshot()
    assert snap["capture"] is chunk
    assert snap["dfn_core"] is not None and snap["pre_filter"] is None
    assert set(snap.keys()) == set(STAGE_NAMES)
    print("  [PASS] test 2: snapshot reflects written stages, leaves untouched stages None")

    print("live/stage_taps.py self-test -- ALL PASSED")


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        _self_test()
    else:
        print("Usage: python live/stage_taps.py --self-test")
