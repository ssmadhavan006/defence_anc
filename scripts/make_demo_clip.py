"""
scripts/make_demo_clip.py — One-off generator for a realistic demo clip:
clean speech + sustained engine noise + a gunshot burst, mixed together.

This is NOT part of the evaluation pipeline (data/mix_dataset.py handles the
real 300-mixture dataset) -- it's a single illustrative "before" clip for
demos/presentation slides, reusing the same validated mix_signals() SNR
logic so the result is representative of what the project actually measures.

Usage:
    python scripts/make_demo_clip.py --output results/demo_audio/before_demo.wav --snr -5
"""
import os
import sys
import argparse
import numpy as np
import soundfile as sf

sys.path.insert(0, ".")
from data.mix_dataset import load_and_resample, mix_signals, TARGET_SR


def make_demo_clip(clean_path: str, gunshot_path: str, engine_path: str,
                    output_path: str, target_snr_db: float, seed: int = 42):
    np.random.seed(seed)
    import random
    random.seed(seed)

    clean, _ = load_and_resample(clean_path, TARGET_SR)
    gunshot, _ = load_and_resample(gunshot_path, TARGET_SR)
    engine, _ = load_and_resample(engine_path, TARGET_SR)

    n = len(clean)

    # Engine: sustained background, loop/crop to clean's length.
    if len(engine) < n:
        engine = np.tile(engine, int(np.ceil(n / len(engine))))
    engine = engine[:n]

    # Gunshot: a short transient burst placed roughly a third of the way in
    # (not at t=0, so the "before" clip has a clean lead-in you can hear the
    # engine alone for a second before the shot hits).
    burst = np.zeros(n, dtype=np.float32)
    place_at = min(n // 3, max(0, n - len(gunshot)))
    end = min(place_at + len(gunshot), n)
    burst[place_at:end] = gunshot[: end - place_at]

    # Combine engine (continuous) + gunshot (transient) into one noise track,
    # weighting the burst up so it's clearly audible as a distinct event on
    # top of the sustained engine bed, then hand off to the project's own
    # validated SNR-mixing logic.
    combined_noise = engine * 0.6 + burst * 1.4

    mixed, scaled_clean, achieved_snr, norm_factor = mix_signals(clean, combined_noise, target_snr_db)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    sf.write(output_path, mixed, TARGET_SR)

    clean_ref_path = os.path.splitext(output_path)[0] + "_clean_ref.wav"
    sf.write(clean_ref_path, scaled_clean, TARGET_SR)

    print(f"Clean speech : {clean_path} ({n/TARGET_SR:.2f}s)")
    print(f"Engine noise : {engine_path}")
    print(f"Gunshot burst: {gunshot_path} (placed at {place_at/TARGET_SR:.2f}s)")
    print(f"Target SNR   : {target_snr_db} dB, achieved: {achieved_snr:.2f} dB")
    print(f"Demo 'before' (noisy) clip -> {output_path}")
    print(f"Clean reference           -> {clean_ref_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a demo before/after clip (clean speech + engine + gunshot)")
    parser.add_argument("--clean", default="data/clean/2277-149896-0010.flac")
    parser.add_argument("--gunshot", default="data/noise/impulsive/gunshot/03fc4685-909e-42c5-aff0-f519f1d14b12_mean_v0.wav")
    parser.add_argument("--engine", default="data/noise/stationary/engine/1-18527-A-44.wav")
    parser.add_argument("--output", default="results/demo_audio/before_demo.wav")
    parser.add_argument("--snr", type=float, default=-5.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    make_demo_clip(args.clean, args.gunshot, args.engine, args.output, args.snr, args.seed)
