"""
models/noise_classifier/impulsive_log.py — Phase 4 WOW #1 T3: impulsive-event log.

Logs detected impulsive acoustic events to a JSONL file with timestamp,
noise category, and confidence.

Naming: "impulsive-event log" — NOT "shot detection".
Rationale (phase4_plan.md §1.5, D5, Rule 32): the 3-class classifier cannot
distinguish a gunshot from a door slam, hand clap, or balloon pop — all
impulsive. It has never been evaluated as a firearm detector (no precision/
recall on an event-detection task). Calling it shot detection would be a
claim that collapses under one follow-up question from a DRDO evaluator.

JSONL format (one JSON object per line):
    {"ts": 1234567890.123, "category": "IMPULSIVE", "confidence": 0.82, "rms_db": -18.5}
"""

import json
import math
import os
import time

import numpy as np


class ImpulsiveEventLog:
    """
    Appends a JSONL record whenever the classifier detects an IMPULSIVE event.

    Parameters
    ----------
    log_path : str — path to the JSONL output file
    """

    def __init__(self, log_path: str = "results/impulsive_events.jsonl"):
        self._path = log_path
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)

    def record(self, category: str, confidence: float,
               audio: "np.ndarray | None" = None) -> None:
        """Write one record. Call only when category == 'IMPULSIVE'."""
        rms_db: float | None = None
        if audio is not None:
            arr = np.asarray(audio, dtype=np.float32)
            rms = float(np.sqrt(np.mean(arr ** 2))) if arr.size > 0 else 0.0
            rms_db = round(20.0 * math.log10(max(rms, 1e-10)), 1)

        record = {
            "ts": round(time.time(), 3),
            "category": category,
            "confidence": round(confidence, 4),
        }
        if rms_db is not None:
            record["rms_db"] = rms_db

        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def count(self) -> int:
        """Return the number of events logged so far."""
        if not os.path.exists(self._path):
            return 0
        with open(self._path, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
