import os
import glob
import time
import argparse
import torch
import soundfile as sf
try:
    from models.deepfilternet.df_compat import init_df, enhance, load_audio, save_audio
except ImportError:
    from df_compat import init_df, enhance, load_audio, save_audio

def process_file(model, df_state, input_path: str, output_path: str, atten_lim_db: float = None) -> float:
    """
    Enhances a single wav file using DeepFilterNet.
    Returns processing time in seconds.
    """
    target_sr = df_state.sr()
    audio, sr = load_audio(input_path, sr=target_sr)
    
    start_time = time.perf_counter()
    enhanced_audio = enhance(model, df_state, audio, pad=True, atten_lim_db=atten_lim_db)
    elapsed_time = time.perf_counter() - start_time
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    save_audio(output_path, enhanced_audio, target_sr)
    return elapsed_time

def batch_inference(input_dir: str, output_dir: str, atten_lim_db: float = None, post_filter: bool = False):
    """
    Batch processes all wav files in input_dir and saves enhanced results to output_dir.
    """
    print(f"Initializing DeepFilterNet model (post_filter={post_filter})...")
    model, df_state, suffix = init_df(post_filter=post_filter, log_level="ERROR")
    target_sr = df_state.sr()
    print(f"DeepFilterNet initialized (Native SR: {target_sr} Hz, Suffix: {suffix})")
    
    wav_files = glob.glob(os.path.join(input_dir, "*.wav")) + glob.glob(os.path.join(input_dir, "**", "*.wav"), recursive=True)
    if not wav_files:
        print(f"No .wav files found in {input_dir}")
        return []
    
    os.makedirs(output_dir, exist_ok=True)
    processed = []
    print(f"Processing {len(wav_files)} file(s) from '{input_dir}' to '{output_dir}'...")
    
    for in_path in wav_files:
        rel_path = os.path.relpath(in_path, input_dir)
        out_filename = f"{os.path.splitext(rel_path)[0]}_{suffix}.wav"
        out_path = os.path.join(output_dir, out_filename)
        
        elapsed = process_file(model, df_state, in_path, out_path, atten_lim_db=atten_lim_db)
        
        # Sanity check output
        assert os.path.exists(out_path), f"Output file missing: {out_path}"
        info = sf.info(out_path)
        assert info.samplerate == target_sr, f"SR mismatch: expected {target_sr}, got {info.samplerate}"
        
        rtf = elapsed / info.duration if info.duration > 0 else 0.0
        print(f"  [OK] {rel_path} -> {out_filename} ({info.duration:.2f}s audio, {elapsed*1000:.1f}ms latency, RTF: {rtf:.4f})")
        processed.append({
            "input": in_path,
            "output": out_path,
            "duration": info.duration,
            "latency": elapsed,
            "rtf": rtf
        })
        
    print(f"Batch processing complete. Enhanced {len(processed)} file(s).")
    return processed

def process_manifest(
    manifest_path: str = "data/manifest.csv",
    output_dir: str = "results/baselines/deepfilternet",
    limit: int = None,
    post_filter: bool = False,
    atten_lim_db: float = None,
) -> list:
    """
    Processes mixtures listed in manifest.csv through DeepFilterNet.
    Saves outputs to output_dir/<mix_filename>.
    Idempotent / resumable: skips already existing files.
    """
    import csv
    print(f"Initializing DeepFilterNet model for manifest processing (post_filter={post_filter})...")
    model, df_state, suffix = init_df(post_filter=post_filter, log_level="ERROR")
    target_sr = df_state.sr()

    with open(manifest_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))

    if limit is not None and limit < len(rows):
        rows = rows[:limit]

    os.makedirs(output_dir, exist_ok=True)
    processed = []
    skipped = 0

    print(f"DeepFilterNet processing {len(rows)} mixture(s) to '{output_dir}'...")
    t0_all = time.time()

    for row in rows:
        in_path = row["output_path"]
        mix_filename = os.path.basename(in_path)
        out_path = os.path.join(output_dir, mix_filename)

        if os.path.exists(out_path):
            skipped += 1
            processed.append({"row": row, "output": out_path, "skipped": True, "elapsed": 0.0})
            continue

        elapsed = process_file(model, df_state, in_path, out_path, atten_lim_db=atten_lim_db)
        processed.append({"row": row, "output": out_path, "skipped": False, "elapsed": elapsed})

    total_time = time.time() - t0_all
    print(f"DeepFilterNet processing finished in {total_time:.2f}s ({skipped} skipped, {len(processed) - skipped} processed).")
    return processed

def run_self_test():
    """
    Minimal self-test for run_inference.py pipeline correctness.
    """
    test_input = "data/mixtures/noisy.wav"
    test_out_dir = "results/test_enhanced"
    assert os.path.exists(test_input), f"Self-test input missing: {test_input}"
    
    results = batch_inference(
        input_dir=os.path.dirname(test_input),
        output_dir=test_out_dir,
        post_filter=False
    )
    assert len(results) > 0, "Self-test failed: no files processed"
    out_file = results[0]["output"]
    assert os.path.exists(out_file), f"Self-test output missing: {out_file}"
    assert os.path.getsize(out_file) > 0, f"Self-test output empty: {out_file}"
    print("Self-test PASSED successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DeepFilterNet Batch Inference Pipeline")
    parser.add_argument("--manifest", default="data/manifest.csv", help="Manifest path for dataset processing")
    parser.add_argument("--input-dir", "-i", default="data/mixtures", help="Input directory containing noisy wav files")
    parser.add_argument("--output-dir", "-o", default="results/baselines/deepfilternet", help="Output directory for enhanced wav files")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of files to process")
    parser.add_argument("--atten-lim", type=float, default=None, help="Noise attenuation limit in dB")
    parser.add_argument("--post-filter", "--pf", action="store_true", help="Enable DeepFilterNet post-filter")
    parser.add_argument("--self-test", action="store_true", help="Run self-test sanity check")
    
    args = parser.parse_args()
    
    if args.self_test:
        run_self_test()
    else:
        process_manifest(
            manifest_path=args.manifest,
            output_dir=args.output_dir,
            limit=args.limit,
            post_filter=args.post_filter,
            atten_lim_db=args.atten_lim
        )
