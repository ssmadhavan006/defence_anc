import os
import sys
import json
import time
import subprocess
import numpy as np
import torch
import soundfile as sf
from df.enhance import init_df, enhance
from df.io import load_audio

def get_cpu_temp() -> float:
    """
    Attempts to read CPU temperature on Raspberry Pi/Linux.
    First tries vcgencmd, then falls back to sysfs thermal zone.
    Returns temperature in degrees Celsius, or -1.0 if unavailable.
    """
    try:
        res = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and "temp=" in res.stdout:
            # Output format: temp=45.2'C
            temp_str = res.stdout.strip().split("=")[1].replace("'C", "")
            return float(temp_str)
    except Exception:
        pass

    try:
        if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp_mC = int(f.read().strip())
                return temp_mC / 1000.0
    except Exception:
        pass

    return -1.0

def benchmark_config(model, df_state, audio_tensor, num_threads: int, num_runs: int = 20, warmup: int = 3):
    """
    Runs benchmark protocol for a specific thread count.
    Protocol: 20 total runs, discard first 3 as warmup, report median & p95 latency and RTF.
    """
    torch.set_num_threads(num_threads)
    actual_threads = torch.get_num_threads()
    
    temp_before = get_cpu_temp()
    latencies = []
    
    # Warmup runs
    for _ in range(warmup):
        _ = enhance(model, df_state, audio_tensor, pad=True)
        
    # Timed runs
    for _ in range(num_runs - warmup):
        start = time.perf_counter()
        _ = enhance(model, df_state, audio_tensor, pad=True)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)
        
    temp_after = get_cpu_temp()
    
    sr = df_state.sr()
    audio_duration = audio_tensor.shape[-1] / sr
    
    latencies_ms = np.array(latencies) * 1000.0
    median_latency_ms = float(np.median(latencies_ms))
    p95_latency_ms = float(np.percentile(latencies_ms, 95))
    
    rtf_series = np.array(latencies) / audio_duration if audio_duration > 0 else np.zeros_like(latencies)
    median_rtf = float(np.median(rtf_series))
    p95_rtf = float(np.percentile(rtf_series, 95))
    
    return {
        "requested_threads": num_threads,
        "actual_threads": actual_threads,
        "total_runs": num_runs,
        "warmup_runs": warmup,
        "valid_runs": len(latencies),
        "audio_duration_sec": audio_duration,
        "median_latency_ms": round(median_latency_ms, 3),
        "p95_latency_ms": round(p95_latency_ms, 3),
        "median_rtf": round(median_rtf, 5),
        "p95_rtf": round(p95_rtf, 5),
        "cpu_temp_before_C": temp_before,
        "cpu_temp_after_C": temp_after
    }

def run_benchmark(input_wav: str = "data/mixtures/noisy.wav", output_json: str = "results/rtf_pi.json"):
    """
    Executes the complete single-thread and 4-thread RTF benchmark protocol.
    """
    if not os.path.exists(input_wav):
        print(f"Error: Input wav file not found at {input_wav}")
        sys.exit(1)
        
    print(f"=== DeepFilterNet RTF Benchmark ===")
    print(f"Machine Hostname: {os.uname().nodename if hasattr(os, 'uname') else os.getenv('COMPUTERNAME', 'unknown')}")
    print(f"Input file: {input_wav}")
    
    print("Loading DeepFilterNet model...")
    model, df_state, suffix = init_df(post_filter=False, log_level="ERROR")
    target_sr = df_state.sr()
    
    audio, sr = load_audio(input_wav, sr=target_sr)
    duration = audio.shape[-1] / target_sr
    print(f"Audio loaded: {duration:.2f}s at {target_sr} Hz")
    
    print("\n--- Benchmark 1: Single-Thread (1 thread) ---")
    st_results = benchmark_config(model, df_state, audio, num_threads=1)
    print(f"  Median Latency: {st_results['median_latency_ms']} ms | P95 Latency: {st_results['p95_latency_ms']} ms")
    print(f"  Median RTF: {st_results['median_rtf']} | P95 RTF: {st_results['p95_rtf']}")
    print(f"  CPU Temp: {st_results['cpu_temp_before_C']}°C -> {st_results['cpu_temp_after_C']}°C")
    
    print("\n--- Benchmark 2: Multi-Thread (4 threads) ---")
    mt_results = benchmark_config(model, df_state, audio, num_threads=4)
    print(f"  Median Latency: {mt_results['median_latency_ms']} ms | P95 Latency: {mt_results['p95_latency_ms']} ms")
    print(f"  Median RTF: {mt_results['median_rtf']} | P95 RTF: {mt_results['p95_rtf']}")
    print(f"  CPU Temp: {mt_results['cpu_temp_before_C']}°C -> {mt_results['cpu_temp_after_C']}°C")
    
    summary = {
        "hostname": os.uname().nodename if hasattr(os, 'uname') else os.getenv('COMPUTERNAME', 'unknown'),
        "platform": sys.platform,
        "input_file": input_wav,
        "audio_duration_sec": duration,
        "sample_rate": target_sr,
        "model_suffix": suffix,
        "single_thread": st_results,
        "four_threads": mt_results,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, "w") as f:
        json.dump(summary, f, indent=2)
        
    print(f"\nSaved benchmark results to: {output_json}")
    return summary

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DeepFilterNet RTF Benchmark Tool")
    parser.add_argument("--input-wav", "-i", default="data/mixtures/noisy.wav", help="Input wav file for benchmarking")
    parser.add_argument("--output-json", "-o", default="results/rtf_pi.json", help="Output JSON results file")
    args = parser.parse_args()
    
    run_benchmark(input_wav=args.input_wav, output_json=args.output_json)
