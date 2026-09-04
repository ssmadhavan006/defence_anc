"""
live/telemetry.py — Phase 4 shared telemetry namespace.

A single PipelineTelemetry instance is created by the pipeline owner and
passed to the Phase 4 background threads (NoiseClassifier, DNSMOSMonitor).
Display surfaces (terminal dashboard, webdash) read from it.

Thread-safety: each field is written with a single Python assignment, which
is atomic in CPython (same GIL guarantee used by pipeline._mode and the
existing display hooks last_in_chunk / last_out_chunk). No lock needed for
display-only reads.
"""

import math
import time


class PipelineTelemetry:
    """Shared telemetry written by background threads, read by display surfaces."""

    def __init__(self):
        # WOW #1 — noise classifier
        self.noise_category: str = "UNKNOWN"   # STATIONARY / NON_STATIONARY / IMPULSIVE / UNCERTAIN
        self.noise_confidence: float = 0.0
        self.impulsive_event_count: int = 0    # cumulative since process start

        # WOW #3 — DNSMOS
        self.mos_sig: float = float("nan")
        self.mos_bak: float = float("nan")
        self.mos_ovr: float = float("nan")
        self.mos_valid: bool = False           # False until first full 9-s window

        # Updated timestamp (monotonic) so consumers can detect stale data
        self.last_updated: float = time.monotonic()

    def snapshot(self) -> dict:
        """Return a JSON-safe dict of current telemetry values."""
        def _safe(v):
            if isinstance(v, float) and math.isnan(v):
                return None
            return v

        return {
            "noise_category": self.noise_category,
            "noise_confidence": round(self.noise_confidence, 3),
            "impulsive_event_count": self.impulsive_event_count,
            "mos_sig": _safe(round(self.mos_sig, 3)) if self.mos_valid else None,
            "mos_bak": _safe(round(self.mos_bak, 3)) if self.mos_valid else None,
            "mos_ovr": _safe(round(self.mos_ovr, 3)) if self.mos_valid else None,
            "mos_valid": self.mos_valid,
        }
