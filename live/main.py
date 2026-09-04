"""
live/main.py — Unified CLI command wrapper for the PS26052 Real-Time Live Pipeline.

Usage:
    python live/main.py detect
    python live/main.py pipeline [args]
    python live/main.py latency [args]
    python live/main.py stress [args]
    python live/main.py demo [args]
"""

import os
import sys
import argparse

# Ensure repo root is on sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

def main():
    parser = argparse.ArgumentParser(
        description="PS26052 Phase 5 — Unified Live Pipeline CLI Interface",
        usage="python live/main.py <subcommand> [subcommand_args]"
    )
    parser.add_argument(
        "subcommand",
        choices=["detect", "pipeline", "latency", "stress", "demo", "calibrate", "acoustic-latency"],
        help="Subcommand to execute: 'detect' (enumerate hardware), "
             "'pipeline' (run stream), 'latency' (click loopback test), "
             "'stress' (10-minute gate), 'demo' (terminal TUI dashboard), "
             "'calibrate' (measure primary/reference mic pair delay, Phase 1), "
             "'acoustic-latency' (physical acoustic round-trip / DFN3 lookahead, Phase 2 A5/A6)."
    )
    
    # Parse the subcommand, leaving the rest for the target subcommand script.
    args, remaining = parser.parse_known_args()
    
    # Re-build sys.argv so sub-scripts parse their own parameters correctly.
    sys.argv = [sys.argv[0] + f" {args.subcommand}"] + remaining
    
    if args.subcommand == "detect":
        from live.detect_devices import detect_and_suggest
        detect_and_suggest()
    elif args.subcommand == "pipeline":
        from live.pipeline import _main
        _main()
    elif args.subcommand == "latency":
        from live.latency_test import main as latency_main
        latency_main()
    elif args.subcommand == "stress":
        from live.stress_test import main as stress_main
        stress_main()
    elif args.subcommand == "demo":
        from demo.dashboard import main as dashboard_main
        dashboard_main()
    elif args.subcommand == "calibrate":
        from live.calibrate_mic_pair import main as calibrate_main
        calibrate_main()
    elif args.subcommand == "acoustic-latency":
        from live.acoustic_latency_test import main as acoustic_latency_main
        acoustic_latency_main()

if __name__ == "__main__":
    main()
