"""
data/augment.py — Reverberation and clipping augmentation for the P1-4
dataset-robustness gap (PS26052 explicitly lists "random noise mixing,
reverberation, clipping" as required augmentation techniques; see
summary/02_NEXT_STEPS_PLAN.md P1-4, and the known gap logged in
data/SOURCES.md Section 4).

Reverberation uses a SYNTHETIC room impulse response (RIR), not a real
recorded corpus (e.g. MIT/OpenSLR). Downloading and redistributing a
third-party dataset requires explicit user permission that was not sought
for this change, and synthetic statistical RIR generation is a standard,
well-established substitute (the same technique pyroomacoustics uses in its
non-geometric mode) when a real corpus isn't on hand. It is fully seedable
and reproducible. Swap generate_synthetic_rir() out for real RIR convolution
later if a licensed corpus is added under data/rir/.

Self-test (no audio hardware, no dataset required):
    python data/augment.py --self-test
"""

import numpy as np
from scipy.signal import fftconvolve

# Room-type presets: (rt60_low_sec, rt60_high_sec) reverberation-time range.
# RT60 = time for the reverb tail to decay 60 dB. Chosen to be
# defence-scenario relevant per P1-4: enclosed vehicle cabins, bunkers, and
# open field. mix_dataset.py maps noise categories onto these.
ROOM_PRESETS = {
    "vehicle_cabin": (0.05, 0.15),
    "bunker": (0.30, 0.60),
    "open_field": (0.02, 0.05),
}

# Clipping intensity presets: (clip_frac_low, clip_frac_high). clip_frac is
# the fraction of the signal's own peak amplitude used as the hard-clip
# threshold — smaller = more aggressive clipping. Impulsive noise (gunshot,
# artillery) clips harder: the whole point of this augmentation is
# simulating a transient that exceeds the mic's dynamic range, which is
# specifically realistic for exactly that category (see P1-4 rationale).
CLIP_PRESETS = {
    "aggressive": (0.30, 0.60),
    "mild": (0.60, 0.90),
}


def generate_synthetic_rir(rt60_sec: float, sr: int = 48000, seed: int = 0) -> np.ndarray:
    """
    Synthesize a room impulse response via exponentially-decaying filtered
    noise (Moorer/Schroeder-style statistical RIR model).

    Parameters
    ----------
    rt60_sec : float
        Reverberation time (seconds) for the tail to decay 60 dB.
    sr : int
        Sample rate.
    seed : int
        RNG seed — same seed + rt60_sec + sr always produces the same RIR.

    Returns
    -------
    np.ndarray, shape (n,), float32
        Impulse response, peak-normalized to 1.0, direct path at index 0.
    """
    if rt60_sec <= 0:
        raise ValueError(f"rt60_sec must be > 0, got {rt60_sec}")
    n = max(int(rt60_sec * sr), 8)
    rng = np.random.default_rng(seed)
    t = np.arange(n) / sr
    # -60 dB over rt60_sec => exp(-ln(1000) * t / rt60_sec), ln(1000) ~= 6.91
    envelope = np.exp(-6.91 * t / rt60_sec)
    rir = rng.standard_normal(n).astype(np.float32) * envelope
    rir[0] = 1.0  # direct path dominates early energy
    rir /= (np.max(np.abs(rir)) + 1e-12)
    return rir.astype(np.float32)


def apply_reverb(signal: np.ndarray, rir: np.ndarray) -> np.ndarray:
    """
    Convolve `signal` with `rir`, keeping the output the same length as the
    input (causal, trims the convolution tail) so it stays time-aligned with
    an unconvolved clean reference. Renormalized to the input's own peak so
    reverb changes the signal's character, not its overall level — downstream
    SNR mixing is unaffected by this rescale.
    """
    if len(signal) == 0:
        return signal
    orig_peak = np.max(np.abs(signal))
    wet = fftconvolve(signal, rir, mode="full")[: len(signal)]
    wet_peak = np.max(np.abs(wet))
    if wet_peak > 1e-10 and orig_peak > 1e-10:
        wet = wet * (orig_peak / wet_peak)
    return wet.astype(np.float32)


def apply_clipping(signal: np.ndarray, clip_frac: float) -> np.ndarray:
    """
    Hard-clip `signal` at clip_frac * its own peak amplitude, simulating
    microphone/ADC overload on a loud transient.

    Parameters
    ----------
    signal : np.ndarray
    clip_frac : float
        In (0, 1]. Smaller = more aggressive clipping. 1.0 = no-op.
    """
    if not (0.0 < clip_frac <= 1.0):
        raise ValueError(f"clip_frac must be in (0, 1], got {clip_frac}")
    peak = np.max(np.abs(signal))
    if peak <= 1e-10:
        return signal
    threshold = clip_frac * peak
    return np.clip(signal, -threshold, threshold).astype(np.float32)


def _self_test():
    print("data/augment.py self-test -- start")
    sr = 48000
    rng = np.random.default_rng(0)

    # --- Test 1: RIR generation is finite, correct length, peak-normalized ---
    rir = generate_synthetic_rir(0.3, sr=sr, seed=1)
    assert np.all(np.isfinite(rir)), "RIR contains non-finite values"
    assert rir.shape == (int(0.3 * sr),), f"unexpected RIR length {rir.shape}"
    assert abs(np.max(np.abs(rir)) - 1.0) < 1e-5, "RIR not peak-normalized to 1.0"
    print(f"  [PASS] test 1: generate_synthetic_rir shape={rir.shape}, peak=1.0")

    # --- Test 2: same seed -> identical RIR (reproducibility) ---
    rir_a = generate_synthetic_rir(0.2, sr=sr, seed=42)
    rir_b = generate_synthetic_rir(0.2, sr=sr, seed=42)
    np.testing.assert_array_equal(rir_a, rir_b)
    rir_c = generate_synthetic_rir(0.2, sr=sr, seed=43)
    assert not np.array_equal(rir_a, rir_c), "different seeds produced identical RIRs"
    print("  [PASS] test 2: RIR generation is seed-reproducible and seed-sensitive")

    # --- Test 3: apply_reverb preserves length and peak, stays finite ---
    tone = 0.5 * np.sin(2 * np.pi * 300 * np.arange(sr) / sr).astype(np.float32)
    rir_short = generate_synthetic_rir(0.05, sr=sr, seed=2)
    wet = apply_reverb(tone, rir_short)
    assert wet.shape == tone.shape, f"length changed: {wet.shape} vs {tone.shape}"
    assert np.all(np.isfinite(wet)), "reverb output contains non-finite values"
    assert abs(np.max(np.abs(wet)) - np.max(np.abs(tone))) < 1e-4, "peak not preserved after reverb"
    print(f"  [PASS] test 3: apply_reverb preserves length={wet.shape} and peak")

    # --- Test 4: apply_reverb on silence stays silent (no divide-by-zero) ---
    silence = np.zeros(1000, dtype=np.float32)
    wet_silence = apply_reverb(silence, rir_short)
    assert np.all(wet_silence == 0.0), "reverb of silence should stay silent"
    print("  [PASS] test 4: apply_reverb handles silence without NaN/divide-by-zero")

    # --- Test 5: apply_clipping actually reduces peak and stays in bounds ---
    loud = rng.uniform(-1.0, 1.0, size=4800).astype(np.float32)
    clipped = apply_clipping(loud, clip_frac=0.5)
    orig_peak = np.max(np.abs(loud))
    clip_peak = np.max(np.abs(clipped))
    assert clip_peak <= orig_peak * 0.5 + 1e-6, "clipping did not reduce peak as expected"
    assert np.all(np.abs(clipped) <= orig_peak * 0.5 + 1e-6), "clipped samples exceed threshold"
    assert clipped.shape == loud.shape
    print(f"  [PASS] test 5: apply_clipping peak {orig_peak:.4f} -> {clip_peak:.4f} (clip_frac=0.5)")

    # --- Test 6: apply_clipping with clip_frac=1.0 is a no-op ---
    unclipped = apply_clipping(loud, clip_frac=1.0)
    np.testing.assert_allclose(unclipped, loud, atol=1e-6)
    print("  [PASS] test 6: apply_clipping(clip_frac=1.0) is a no-op")

    # --- Test 7: apply_clipping on silence doesn't crash ---
    clipped_silence = apply_clipping(silence, clip_frac=0.5)
    assert np.all(clipped_silence == 0.0)
    print("  [PASS] test 7: apply_clipping handles silence without divide-by-zero")

    # --- Test 8: invalid inputs raise, don't silently misbehave ---
    try:
        generate_synthetic_rir(0.0)
        assert False, "expected ValueError for rt60_sec=0"
    except ValueError:
        pass
    try:
        apply_clipping(loud, clip_frac=1.5)
        assert False, "expected ValueError for clip_frac > 1"
    except ValueError:
        pass
    print("  [PASS] test 8: invalid parameters raise ValueError instead of misbehaving")

    print("data/augment.py self-test -- ALL PASSED")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RIR/clipping augmentation utilities")
    parser.add_argument("--self-test", action="store_true", help="Run offline self-test and exit")
    args = parser.parse_args()
    if args.self_test:
        _self_test()
    else:
        parser.print_help()
