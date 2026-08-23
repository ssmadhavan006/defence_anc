import os
import numpy as np
import soundfile as sf

def generate_test_audio(output_path: str, duration_sec: float = 3.0, sr: int = 48000):
    """
    Generates a synthetic noisy audio file for pipeline verification.
    Blends a multi-harmonic tone (simulating speech harmonics) with Gaussian white noise.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
    
    # Synthetic clean signal (fundamental 220Hz + harmonics)
    clean = (
        0.5 * np.sin(2 * np.pi * 220 * t) +
        0.3 * np.sin(2 * np.pi * 440 * t) +
        0.2 * np.sin(2 * np.pi * 880 * t)
    )
    
    # Amplitude envelope to simulate speech pauses
    envelope = 0.5 * (1 + np.sin(2 * np.pi * 1.5 * t))
    clean = clean * envelope
    
    # Synthetic noise (stationary white noise)
    noise = np.random.normal(0, 0.25, size=t.shape)
    
    # Mixed noisy signal
    noisy = clean + noise
    
    # Normalize to prevent clipping
    max_val = np.max(np.abs(noisy))
    if max_val > 0:
        noisy = noisy / max_val * 0.9
        
    sf.write(output_path, noisy, sr)
    print(f"Generated test noisy audio: {output_path} (SR: {sr} Hz, Duration: {duration_sec}s, Samples: {len(noisy)})")
    return output_path

if __name__ == "__main__":
    generate_test_audio("data/mixtures/noisy.wav", duration_sec=3.0, sr=48000)
