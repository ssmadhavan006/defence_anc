import os
import glob
import random
import numpy as np
import soundfile as sf
import torchaudio
import torch

import sys
sys.path.insert(0, ".")

from models.deepfilternet.df_compat import resample

def create_babble_clip(speech_files: list, duration_sec: float = 10.0, num_speakers: int = 6, sr: int = 48000, seed: int = 42) -> np.ndarray:
    """
    Synthesizes a multi-talker babble noise clip by overlapping multiple clean speech utterances
    at random offsets and gain levels.
    """
    random.seed(seed)
    np.random.seed(seed)
    target_samples = int(duration_sec * sr)
    babble_mix = np.zeros(target_samples, dtype=np.float32)
    
    selected_files = random.sample(speech_files, min(num_speakers, len(speech_files)))
    
    for idx, filepath in enumerate(selected_files):
        # Load audio using soundfile
        data, orig_sr = sf.read(filepath, dtype="float32")
        if data.ndim > 1:
            data = data[:, 0]
            
        tensor_data = torch.from_numpy(data).unsqueeze(0)
        if orig_sr != sr:
            tensor_data = resample(tensor_data, orig_sr, sr)
        audio = tensor_data.squeeze(0).numpy()
        
        # Loop audio if shorter than target duration
        if len(audio) < target_samples:
            tile_count = int(np.ceil(target_samples / len(audio)))
            audio = np.tile(audio, tile_count)[:target_samples]
        else:
            # Pick a random crop
            start_offset = random.randint(0, max(0, len(audio) - target_samples))
            audio = audio[start_offset:start_offset + target_samples]
            
        # Apply random gain shift per speaker (-3dB to +3dB)
        gain = 10.0 ** (random.uniform(-3.0, 3.0) / 20.0)
        
        # Apply slight temporal shift (random roll)
        shift = random.randint(0, sr * 2)
        audio = np.roll(audio, shift)
        
        babble_mix += audio * gain

    # Normalize amplitude
    max_val = np.max(np.abs(babble_mix))
    if max_val > 0:
        babble_mix = (babble_mix / max_val) * 0.85
        
    return babble_mix

def generate_babble_dataset(clean_dir: str, output_dir: str, num_clips: int = 20, duration_sec: float = 10.0, sr: int = 48000, seed: int = 1234):
    """
    Generates a set of synthetic crowd babble noise files saved into output_dir.
    """
    os.makedirs(output_dir, exist_ok=True)
    clean_files = glob.glob(os.path.join(clean_dir, "*.flac")) + glob.glob(os.path.join(clean_dir, "*.wav"))
    if len(clean_files) < 6:
        print(f"Warning: Not enough clean files in {clean_dir} to generate multi-talker babble (found {len(clean_files)})")
        return []

    print(f"Generating {num_clips} synthetic babble crowd clips into '{output_dir}'...")
    generated_paths = []
    for i in range(num_clips):
        clip_seed = seed + i
        babble = create_babble_clip(clean_files, duration_sec=duration_sec, num_speakers=6, sr=sr, seed=clip_seed)
        out_filename = f"babble_crowd_{i+1:03d}.wav"
        out_path = os.path.join(output_dir, out_filename)
        sf.write(out_path, babble, sr)
        generated_paths.append(out_path)

    print(f"Generated {len(generated_paths)} babble crowd clips at {sr} Hz.")
    return generated_paths

if __name__ == "__main__":
    generate_babble_dataset("data/clean", "data/noise/non_stationary/crowd", num_clips=20)
