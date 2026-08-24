"""
live/stress_test.py — 10-minute continuous run stress test in ENHANCE mode.

Logs system and pipeline metrics every 10 seconds.
Checks pass criteria: zero dropouts, max temp < 80°C, no crash.

Usage:
    python live/stress_test.py --duration 600
"""

import os
import sys
import time
import argparse
import json
import psutil

# Ensure repo root is on sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from live.pipeline import LivePipeline, _load_config

def get_cpu_temp():
    """Get CPU temperature in Celsius. Works on Raspberry Pi / Linux."""
    temp_path = "/sys/class/thermal/thermal_zone0/temp"
    if os.path.exists(temp_path):
        try:
            with open(temp_path, "r") as f:
                temp_raw = int(f.read().strip())
            return temp_raw / 1000.0
        except Exception:
            pass
    return None

def run_stress_test(duration_sec: int, config_path: str, output_path: str):
    print("=== Phase 5 Real-Time Stress Test ===")
    print(f"Target Duration : {duration_sec} seconds ({duration_sec / 60:.1f} minutes)")
    print(f"Config File     : {config_path}")
    print()

    # Force mode = enhance
    config = _load_config(config_path)
    config["pipeline"]["mode"] = "enhance"
    config["pipeline"]["log_timing"] = False # Don't flood output
    
    pipeline = LivePipeline(config)
    
    print("Starting real-time audio pipeline in ENHANCE mode...", flush=True)
    pipeline.start()
    
    start_time = time.time()
    next_check = start_time + 10.0
    elapsed = 0.0
    
    records = []
    has_failed = False
    failure_reason = ""
    
    print(f"{'Elapsed (s)':<12} | {'CPU (%)':<8} | {'RAM (%)':<8} | {'Temp (°C)':<10} | {'Overflows':<10} | {'Underruns':<10}")
    print("-" * 68)
    
    try:
        while elapsed < duration_sec:
            time.sleep(0.5)
            now = time.time()
            elapsed = now - start_time
            
            if now >= next_check:
                next_check += 10.0
                
                # Fetch metrics
                cpu_p = psutil.cpu_percent()
                ram_p = psutil.virtual_memory().percent
                temp = get_cpu_temp()
                
                # Access pipeline internal state safe-ish
                overflows = pipeline._in_buf.overflow_count
                underruns = pipeline._dropped_chunks
                
                temp_str = f"{temp:.1f}" if temp is not None else "N/A"
                print(f"{int(elapsed):<12} | {cpu_p:<8.1f} | {ram_p:<8.1f} | {temp_str:<10} | {overflows:<10} | {underruns:<10}", flush=True)
                
                records.append({
                    "elapsed_sec": round(elapsed, 1),
                    "cpu_percent": cpu_p,
                    "ram_percent": ram_p,
                    "temperature_c": temp,
                    "overflows": overflows,
                    "underruns": underruns
                })
                
                # Check temperature threshold (80°C)
                if temp is not None and temp >= 80.0:
                    has_failed = True
                    failure_reason = f"CPU temperature exceeded limit: {temp:.1f}°C >= 80.0°C"
                    print(f"\n[WARNING] Temperature threshold exceeded! Current: {temp:.1f}°C", file=sys.stderr)
                    
    except KeyboardInterrupt:
        print("\nStress test interrupted by user.", file=sys.stderr)
        failure_reason = "Test interrupted by user."
        has_failed = True
    except Exception as e:
        print(f"\n[ERROR] Pipeline or monitoring crash: {e}", file=sys.stderr)
        failure_reason = f"Crash: {e}"
        has_failed = True
    finally:
        print("\nStopping audio pipeline...", flush=True)
        pipeline.stop()
        
    actual_duration = time.time() - start_time
    
    # Process final stats.
    # _dropped_chunks counts ONLY underruns that happened while the pipeline
    # was running. Underruns during the post-stop() drain are tracked
    # separately and deliberately excluded from the verdict -- they are an
    # unavoidable artifact of the output stream outliving the inference
    # thread, not a real-time failure. (See pipeline._output_callback.)
    final_overflows = pipeline._in_buf.overflow_count
    final_underruns = pipeline._dropped_chunks
    teardown_underruns = pipeline._teardown_underruns
    total_dropouts = final_overflows + final_underruns
    
    cpu_vals = [r["cpu_percent"] for r in records]
    ram_vals = [r["ram_percent"] for r in records]
    temp_vals = [r["temperature_c"] for r in records if r["temperature_c"] is not None]
    
    mean_cpu = sum(cpu_vals) / len(cpu_vals) if cpu_vals else 0
    max_cpu = max(cpu_vals) if cpu_vals else 0
    mean_ram = sum(ram_vals) / len(ram_vals) if ram_vals else 0
    max_temp = max(temp_vals) if temp_vals else None
    
    # Evaluate Pass/Fail
    if not has_failed:
        if total_dropouts > 0:
            has_failed = True
            failure_reason = f"Audio dropouts detected: {final_overflows} overflows, {final_underruns} underruns."
        elif actual_duration < duration_sec - 5.0:
            has_failed = True
            failure_reason = "Test stopped prematurely."
            
    verdict = "FAIL" if has_failed else "PASS"
    
    summary = {
        "verdict": verdict,
        "failure_reason": failure_reason,
        "duration_sec": round(actual_duration, 1),
        "mean_cpu_percent": round(mean_cpu, 2),
        "max_cpu_percent": round(max_cpu, 2),
        "mean_ram_percent": round(mean_ram, 2),
        "max_temperature_c": round(max_temp, 2) if max_temp is not None else None,
        "total_overflows": final_overflows,
        "total_underruns": final_underruns,
        "teardown_underruns": teardown_underruns,
        "total_dropouts": total_dropouts,
        "history": records
    }
    
    print("\n=== Stress Test Summary ===")
    print(f"Verdict         : {verdict}")
    if has_failed:
        print(f"Reason          : {failure_reason}")
    print(f"Duration        : {actual_duration:.1f} seconds")
    print(f"CPU Load (%)    : Mean {mean_cpu:.1f}%, Max {max_cpu:.1f}%")
    print(f"RAM Usage (%)   : Mean {mean_ram:.1f}%")
    if max_temp is not None:
        print(f"Max Temperature : {max_temp:.1f}°C")
    print(f"Total Dropouts  : {total_dropouts} ({final_overflows} overflows, {final_underruns} underruns)")
    if teardown_underruns:
        print(f"Shutdown Drain  : {teardown_underruns} underruns after stop() (expected, excluded from verdict)")
    print("==========================")
    
    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"Report saved to: {output_path}")
        
    return 1 if has_failed else 0

def main():
    parser = argparse.ArgumentParser(description="PS26052 Phase 5 — Live pipeline stress tester")
    parser.add_argument("--duration", type=int, default=600, help="Test duration in seconds (default: 600 / 10m)")
    parser.add_argument("--config", default="config/audio_config.yaml", help="Path to audio_config.yaml")
    parser.add_argument("--output-json", default="results/stress_test_report.json", help="Path to write JSON results")
    args = parser.parse_args()
    
    sys.exit(run_stress_test(args.duration, args.config, args.output_json))

if __name__ == "__main__":
    main()
