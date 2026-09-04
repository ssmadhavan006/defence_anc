"""
live/latency_budget.py — Single source of truth for the Phase 2 latency budget.

Replaces the arithmetic that used to live inline in a print statement in
live/e2e_latency_test.py. Every component of the end-to-end latency estimate
is a named field with its own `source` tag ("measured" / "estimated" /
"configured"), and every LatencyBudget carries a mandatory `machine` field
(Rule 5) so a dev-machine number can never be silently presented as a Pi
result.

Usage:
    from live.latency_budget import LatencyBudget

    budget = LatencyBudget(
        machine="pi5",
        device_roundtrip_ms=42.67, device_roundtrip_source="measured",
        inference_ms=29.5, inference_source="measured",
        priming_ms=100.0, priming_source="configured",
    )
    print(budget.render_table())
    budget.to_json()  # -> str, round-trips via LatencyBudget.from_json()

Self-test (Mode A — no hardware required):
    python live/latency_budget.py
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Optional

VALID_SOURCES = ("measured", "estimated", "configured")
VALID_MACHINES = ("pi5", "devmachine")


def _validate_source(name: str, value: str) -> None:
    if value not in VALID_SOURCES:
        raise ValueError(
            f"{name} must be one of {VALID_SOURCES}, got {value!r}"
        )


@dataclass
class LatencyBudget:
    """
    One end-to-end latency budget, with per-component provenance.

    `machine` is mandatory and unconstrained-but-checked against the two
    known values ("pi5", "devmachine") -- Rule 5 requires every latency
    figure to name the machine it was measured on.
    """

    machine: str

    device_roundtrip_ms: float = 0.0
    device_roundtrip_source: str = "estimated"

    inference_ms: float = 0.0
    inference_source: str = "estimated"

    priming_ms: float = 0.0
    priming_source: str = "configured"

    resample_ms: float = 0.0
    resample_source: str = "estimated"

    lookahead_ms: float = 0.0
    lookahead_source: str = "estimated"

    # Stays None until a real physical acoustic measurement (§ A5) fills it.
    measured_physical_ms: Optional[float] = None

    def __post_init__(self):
        if self.machine not in VALID_MACHINES:
            raise ValueError(
                f"machine must be one of {VALID_MACHINES}, got {self.machine!r} "
                "(Rule 5: every latency figure must name its machine)"
            )
        for attr in (
            "device_roundtrip_source", "inference_source", "priming_source",
            "resample_source", "lookahead_source",
        ):
            _validate_source(attr, getattr(self, attr))

    # ------------------------------------------------------------------
    # Derived values
    # ------------------------------------------------------------------

    @property
    def total_estimate_ms(self) -> float:
        """Sum of all analytical components. NOT the same as measured_physical_ms."""
        return (
            self.device_roundtrip_ms + self.inference_ms + self.priming_ms
            + self.resample_ms + self.lookahead_ms
        )

    def _components(self):
        return [
            ("device_roundtrip", self.device_roundtrip_ms, self.device_roundtrip_source),
            ("inference", self.inference_ms, self.inference_source),
            ("priming", self.priming_ms, self.priming_source),
            ("resample", self.resample_ms, self.resample_source),
            ("lookahead", self.lookahead_ms, self.lookahead_source),
        ]

    def is_mixed_source(self) -> bool:
        """True if the components were not all obtained the same way."""
        return len({src for _, _, src in self._components()}) > 1

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, s: str) -> "LatencyBudget":
        return cls(**json.loads(s))

    # ------------------------------------------------------------------
    # Human-readable rendering
    # ------------------------------------------------------------------

    def render_table(self) -> str:
        total = self.total_estimate_ms
        lines = [f"Latency budget — machine={self.machine}"]
        for name, ms, src in self._components():
            share = (ms / total * 100.0) if total > 0 else 0.0
            lines.append(f"  {name:<18} {ms:8.2f} ms  {share:5.1f}%  [{src}]")
        lines.append(f"  {'TOTAL (estimate)':<18} {total:8.2f} ms")
        if self.measured_physical_ms is not None:
            lines.append(
                f"  {'MEASURED PHYSICAL':<18} {self.measured_physical_ms:8.2f} ms  [measured]"
            )
        if self.is_mixed_source():
            lines.append(
                "  NOTE: this budget mixes measured/estimated/configured sources "
                "-- see the per-row tags above; do not quote TOTAL as a single "
                "physical measurement."
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Self-test (Mode A — no hardware required)
# ---------------------------------------------------------------------------

def _self_test():
    print("live/latency_budget.py self-test -- start")

    # --- Test 1: total is the sum of all components ---
    b = LatencyBudget(
        machine="pi5",
        device_roundtrip_ms=42.67, device_roundtrip_source="measured",
        inference_ms=29.5, inference_source="measured",
        priming_ms=100.0, priming_source="configured",
    )
    expected_total = 42.67 + 29.5 + 100.0
    assert abs(b.total_estimate_ms - expected_total) < 1e-9, b.total_estimate_ms
    print(f"  [PASS] test 1: total_estimate_ms == {expected_total} (sum of components)")

    # --- Test 2: mixed-source rendering flags itself ---
    assert b.is_mixed_source(), "measured+configured mix should be flagged"
    table = b.render_table()
    assert "NOTE: this budget mixes" in table
    assert "machine=pi5" in table
    print("  [PASS] test 2: mixed-source budget flags itself in render_table()")

    # --- Test 3: single-source budget does NOT flag itself ---
    b_uniform = LatencyBudget(
        machine="devmachine",
        device_roundtrip_ms=1.0, device_roundtrip_source="estimated",
        inference_ms=1.0, inference_source="estimated",
        priming_ms=1.0, priming_source="estimated",
        resample_ms=1.0, resample_source="estimated",
        lookahead_ms=1.0, lookahead_source="estimated",
    )
    assert not b_uniform.is_mixed_source()
    assert "NOTE: this budget mixes" not in b_uniform.render_table()
    print("  [PASS] test 3: uniform-source budget does not flag itself")

    # --- Test 4: JSON round-trip fidelity ---
    s = b.to_json()
    b2 = LatencyBudget.from_json(s)
    assert b2 == b, f"round-trip mismatch: {b2} != {b}"
    print("  [PASS] test 4: to_json()/from_json() round-trip is exact")

    # --- Test 5: invalid machine / source rejected ---
    try:
        LatencyBudget(machine="my_laptop")
        assert False, "expected ValueError for unknown machine"
    except ValueError:
        pass
    try:
        LatencyBudget(machine="pi5", inference_source="guessed")
        assert False, "expected ValueError for unknown source"
    except ValueError:
        pass
    print("  [PASS] test 5: unknown machine/source values raise ValueError")

    # --- Test 6: measured_physical_ms defaults to None, renders only when set ---
    assert b.measured_physical_ms is None
    assert "MEASURED PHYSICAL" not in b.render_table()
    b.measured_physical_ms = 150.0
    assert "MEASURED PHYSICAL" in b.render_table()
    print("  [PASS] test 6: measured_physical_ms stays None until filled in, then renders")

    print("live/latency_budget.py self-test -- ALL PASSED")


if __name__ == "__main__":
    _self_test()
