"""
demo/dashboard.py — Terminal dashboard for monitoring and toggling the live pipeline.

Features:
- Dynamic system monitoring (CPU, RAM, Temp).
- Dynamic pipeline telemetry (ring buffer fill levels, overflows, underruns).
- Real-time latency statistics (median, p95, RTF).
- Interactive key controls:
    'b' -> dynamically toggle between ENHANCE and BYPASS mode.
    'q' -> quit.

Usage:
    python demo/dashboard.py
"""

import os
import sys
import time
import threading
import numpy as np
import psutil

# Ensure repo root is on sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from live.pipeline import LivePipeline, _load_config
from live.stress_test import get_cpu_temp

# Cross-platform non-blocking key reader
class KeyListener:
    def __init__(self):
        self.is_posix = (os.name != 'nt')
        if self.is_posix:
            import termios
            import tty
            import select
            self.termios = termios
            self.tty = tty
            self.select = select
            self.old_settings = termios.tcgetattr(sys.stdin)
        else:
            import msvcrt
            self.msvcrt = msvcrt
            self.old_settings = None

    def __enter__(self):
        if self.is_posix:
            self.tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, type, value, traceback):
        if self.is_posix and self.old_settings:
            self.termios.tcsetattr(sys.stdin, self.termios.TCSADRAIN, self.old_settings)

    def get_key(self):
        """Read a single keypress without blocking, return None if no key pressed."""
        if self.is_posix:
            if self.select.select([sys.stdin], [], [], 0.01)[0]:
                return sys.stdin.read(1).lower()
        else:
            if self.msvcrt.kbhit():
                try:
                    return self.msvcrt.getch().decode('utf-8').lower()
                except Exception:
                    pass
        return None


def print_progress_bar(percentage: float, width: int = 20) -> str:
    """Returns a visual progress bar string."""
    filled_len = int(round(width * percentage / 100))
    bar = "█" * filled_len + "░" * (width - filled_len)
    return f"[{bar}] {percentage:.1f}%"


def run_dashboard(config_path: str):
    config = _load_config(config_path)
    
    # Force log_timing = False to prevent console clutter, we pull stats instead
    config["pipeline"]["log_timing"] = False
    
    pipeline = LivePipeline(config)
    
    # ANSI escape sequences for text formatting
    CLEAR = "\033[H\033[J"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    RESET = "\033[0m"

    print("Initializing dashboard and loading model...", flush=True)
    pipeline.start()
    
    # Warm up finished
    running = True
    start_time = time.time()
    
    print(CLEAR, end="")
    
    try:
        with KeyListener() as listener:
            while running:
                # 1. Capture keys
                key = listener.get_key()
                if key == 'q':
                    running = False
                    break
                elif key == 'b':
                    # Toggle pipeline mode
                    old_mode = pipeline._mode
                    new_mode = "bypass" if old_mode == "enhance" else "enhance"
                    pipeline._mode = new_mode
                
                # 2. Query stats
                elapsed = time.time() - start_time
                cpu_p = psutil.cpu_percent()
                ram_p = psutil.virtual_memory().percent
                temp = get_cpu_temp()
                
                # Buffer states
                in_cap = pipeline._in_buf.capacity
                in_filled = pipeline._in_buf.available
                in_fill_p = (in_filled / in_cap) * 100.0 if in_cap > 0 else 0
                
                out_cap = pipeline._out_buf.capacity
                out_filled = pipeline._out_buf.available
                out_fill_p = (out_filled / out_cap) * 100.0 if out_cap > 0 else 0
                
                overflows = pipeline._in_buf.overflow_count
                underruns = pipeline._dropped_chunks
                
                # Processing times
                lats = np.array(pipeline._chunk_latencies) * 1000.0  # ms
                median_lat = np.median(lats) if len(lats) > 0 else 0.0
                p95_lat = np.percentile(lats, 95) if len(lats) > 0 else 0.0
                
                chunk_sec = pipeline._chunk_sec
                rtf_median = (median_lat / 1000.0) / chunk_sec if chunk_sec > 0 else 0.0
                
                mode_disp = f"{GREEN}ENHANCE{RESET}" if pipeline._mode == "enhance" else f"{YELLOW}BYPASS (Time-Aligned){RESET}"
                
                # Build screen buffer
                lines = []
                lines.append(f"{BOLD}{CYAN}============================================================{RESET}")
                lines.append(f"{BOLD}             PS26052 Live Audio suppression Dashboard      {RESET}")
                lines.append(f"{BOLD}{CYAN}============================================================{RESET}")
                lines.append(f"  Runtime Status   : {GREEN}ACTIVE{RESET} ({int(elapsed)}s)")
                lines.append(f"  Processing Mode  : {mode_disp} (Press {BOLD}'b'{RESET} to toggle)")
                lines.append(f"  Audio Sample Rate: {pipeline._sr} Hz (Mono)")
                lines.append(f"  Frame Chunk Size : {pipeline._chunk_samples} samples ({pipeline._chunk_sec*1000:.0f} ms)")
                lines.append("")
                
                lines.append(f"{BOLD}[System Telemetry]{RESET}")
                lines.append(f"  CPU Utilization  : {print_progress_bar(cpu_p)}")
                lines.append(f"  RAM Utilization  : {print_progress_bar(ram_p)}")
                if temp is not None:
                    color = RED if temp >= 75 else (YELLOW if temp >= 65 else GREEN)
                    lines.append(f"  CPU Temperature  : {color}{temp:.1f} °C{RESET}")
                else:
                    lines.append("  CPU Temperature  : N/A (Windows/Virtual)")
                lines.append("")
                
                lines.append(f"{BOLD}[Pipeline Performance]{RESET}")
                lines.append(f"  Input Ring Buffer: {print_progress_bar(in_fill_p)} ({in_filled}/{in_cap} frames)")
                lines.append(f"  Output Ring Buffer: {print_progress_bar(out_fill_p)} ({out_filled}/{out_cap} frames)")
                
                err_color = RED if overflows > 0 else GREEN
                lines.append(f"  Buffer Overflows : {err_color}{overflows}{RESET}")
                
                und_color = RED if underruns > 0 else GREEN
                lines.append(f"  Buffer Underruns : {und_color}{underruns}{RESET}")
                lines.append("")
                
                lines.append(f"{BOLD}[Latency Statistics]{RESET}")
                lines.append(f"  Median Processing: {median_lat:.2f} ms")
                lines.append(f"  95th-Percentile  : {p95_lat:.2f} ms")
                
                rtf_color = GREEN if rtf_median < 0.5 else (YELLOW if rtf_median < 0.9 else RED)
                lines.append(f"  Median RTF       : {rtf_color}{rtf_median:.4f}{RESET} (1.0000 = Real-time limit)")
                lines.append("")
                
                lines.append(f"{BOLD}{CYAN}------------------------------------------------------------{RESET}")
                lines.append(" Controls:  Press 'b' to Toggle Mode  |  Press 'q' to Quit Demo ")
                lines.append(f"{BOLD}{CYAN}============================================================{RESET}")
                
                # Render screen
                # Write cursor to top home position and print all lines
                sys.stdout.write("\033[H" + "\n".join(lines))
                sys.stdout.flush()
                
                time.sleep(0.2)
                
    finally:
        print("\nStopping audio stream and shutting down...", flush=True)
        pipeline.stop()
        print("Demo stopped. Clean exit.", flush=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="PS26052 Phase 5 — Terminal Dashboard Demo")
    parser.add_argument("--config", default="config/audio_config.yaml", help="Path to audio_config.yaml")
    args = parser.parse_args()
    
    run_dashboard(args.config)

if __name__ == "__main__":
    main()
