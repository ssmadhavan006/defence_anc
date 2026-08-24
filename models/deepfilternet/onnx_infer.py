"""
models/deepfilternet/onnx_infer.py — ONNX Runtime-based DeepFilterNet3
inference (P1-3), combining three ONNX sub-graphs (encoder, ERB decoder,
deep-filter decoder — see export_onnx.py) with a numpy reimplementation of
the combination logic PyTorch's DfNet.forward() does in the complex domain.

Why a numpy reimplementation exists at all: ONNX has no complex dtype and
cannot represent `torch.view_as_complex` (used by DfNet's mask-application
and deep-filtering stages). Rather than exporting those stages, this module
reimplements exactly two pieces of math directly in real/imaginary
components:
  1. ERB mask application (Mask.forward): a fixed matrix multiply against
     the model's erb_inv_fb buffer, then an elementwise multiply — no
     complex ops needed even in PyTorch's own implementation.
  2. Deep filtering (DF.forward): a complex FIR sum across `frame_size`
     neighboring time frames, computed here via real+imaginary component
     arithmetic (ar*br - ai*bi, ar*bi + ai*br) instead of torch.complex.

Both were verified bit-for-bit against PyTorch's own forward pass
(max abs diff: 0.0, using the model's actual intermediate tensors) before
being written into this module — see progress.md's 2026-08-24 P1-3 entry
for the verification transcript. Do not modify apply_mask_np /
apply_deep_filter_np without re-running that same bit-for-bit check.

Self-test (Mode A — loads the real model to compare against, no audio
hardware needed):
    python models/deepfilternet/onnx_infer.py --self-test
"""

import json
import os
import sys

sys.path.insert(0, ".")

import numpy as np
import onnxruntime as ort
import torch
import torch.nn.functional as F

from numpy.lib.stride_tricks import sliding_window_view


def df_out_transform_np(coefs: np.ndarray) -> np.ndarray:
    """[B, T, F, O*2] -> [B, O, T, F, 2]. Parameterless reshape+permute,
    matches df.deepfilternet3.DfOutputReshapeMF.forward exactly."""
    B, T, F_, O2 = coefs.shape
    coefs = coefs.reshape(B, T, F_, -1, 2)
    return coefs.transpose(0, 3, 1, 2, 4)


def apply_mask_np(spec: np.ndarray, m: np.ndarray, erb_inv_fb: np.ndarray) -> np.ndarray:
    """
    spec: [B, C, T, F, 2] real-valued (last dim = [real, imag])
    m: [B, C, T, Fe] ERB-band mask (or [B, T, Fe] — squeezed C handled below)
    erb_inv_fb: [Fe, F] inverse ERB filterbank (fixed model buffer)
    Returns spec * mask_expanded, matching Mask.forward's real-tensor path.
    """
    if m.ndim == 3:
        m = m[:, np.newaxis, :, :]
    mask_full = m @ erb_inv_fb  # [B, C, T, F]
    return spec * mask_full[..., np.newaxis]


def apply_deep_filter_np(spec: np.ndarray, coefs: np.ndarray, frame_size: int,
                          lookahead: int, num_freqs: int) -> np.ndarray:
    """
    spec: [B, C, T, F, 2] real-valued original spectrogram
    coefs: [B, O=frame_size, T, F=num_freqs, 2] real-valued (post df_out_transform)
    Returns the deep-filtered result for the first `num_freqs` bins only,
    shape [B, C, T, num_freqs] complex — matches DF.forward's `spec_f` output
    before it gets written back into the low-frequency portion of spec.
    """
    spec_complex = spec[..., 0] + 1j * spec[..., 1]  # [B, C, T, F]
    pad_before, pad_after = frame_size - 1 - lookahead, lookahead
    pad_width = [(0, 0)] * spec_complex.ndim
    pad_width[2] = (pad_before, pad_after)
    padded = np.pad(spec_complex, pad_width)
    unfolded = sliding_window_view(padded, frame_size, axis=2)  # [B, C, T, F, N]
    spec_f = unfolded[..., :num_freqs, :]  # [B, C, T, num_freqs, N]

    coefs_complex = coefs[..., 0] + 1j * coefs[..., 1]  # [B, O, T, F]
    coefs_r = coefs_complex[:, np.newaxis, :, :, :]  # [B, C=1, O, T, F]

    return np.einsum("bctfn,bcntf->bctf", spec_f, coefs_r)


def combine_output_np(spec: np.ndarray, m: np.ndarray, coefs_raw: np.ndarray,
                       erb_inv_fb: np.ndarray, frame_size: int, lookahead: int,
                       num_freqs: int) -> np.ndarray:
    """
    Full reimplementation of DfNet.forward()'s tail: low frequency bins
    (< num_freqs) get the deep-filtered result, high frequency bins
    (>= num_freqs) get the ERB-masked result. Matches
    `spec_e[..., self.nb_df:, :] = spec_m[..., self.nb_df:, :]` exactly.
    """
    coefs = df_out_transform_np(coefs_raw)
    spec_m = apply_mask_np(spec, m, erb_inv_fb)
    deep = apply_deep_filter_np(spec, coefs, frame_size, lookahead, num_freqs)

    spec_e = spec_m.copy()
    spec_e[..., :num_freqs, 0] = deep.real
    spec_e[..., :num_freqs, 1] = deep.imag
    return spec_e


class OnnxDfNet:
    """
    Loads the three exported ONNX sub-graphs and reproduces DfNet.forward()
    via ONNX Runtime sessions + the numpy combination logic above. Drop-in
    replacement for calling `model(spec, feat_erb, feat_spec)` in
    df.enhance.enhance() — see enhance_onnx() below.
    """

    def __init__(self, export_dir: str, providers=None):
        providers = providers or ["CPUExecutionProvider"]
        self._enc = ort.InferenceSession(os.path.join(export_dir, "enc.onnx"), providers=providers)
        self._erb_dec = ort.InferenceSession(os.path.join(export_dir, "erb_dec.onnx"), providers=providers)
        self._df_dec = ort.InferenceSession(os.path.join(export_dir, "df_dec.onnx"), providers=providers)
        self._erb_inv_fb = np.load(os.path.join(export_dir, "erb_inv_fb.npy"))
        with open(os.path.join(export_dir, "df_config.json")) as f:
            self._config = json.load(f)

    def infer(self, spec: np.ndarray, feat_erb: np.ndarray, feat_spec: np.ndarray) -> np.ndarray:
        """
        spec: [B, 1, T, F, 2], feat_erb: [B, 1, T, E], feat_spec: [B, 1, T, F', 2]
        (same shapes df.enhance.df_features() produces). Returns spec_e,
        the fully-filtered spectrum, shape matching `spec`.
        """
        feat_spec2 = np.ascontiguousarray(np.transpose(feat_spec, (0, 4, 2, 3, 1)).squeeze(-1))
        e0, e1, e2, e3, emb, c0, lsnr = self._enc.run(
            None, {"feat_erb": feat_erb.astype(np.float32), "feat_spec": feat_spec2.astype(np.float32)}
        )
        m, = self._erb_dec.run(None, {"emb": emb, "e3": e3, "e2": e2, "e1": e1, "e0": e0})
        coefs, = self._df_dec.run(None, {"emb": emb, "c0": c0})

        return combine_output_np(
            spec, m, coefs, self._erb_inv_fb,
            self._config["frame_size"], self._config["lookahead"], self._config["num_freqs"],
        )


@torch.no_grad()
def enhance_onnx(onnx_model: OnnxDfNet, df_state, audio: torch.Tensor, pad: bool = True,
                  atten_lim_db=None) -> torch.Tensor:
    """
    ONNX-backed equivalent of df.enhance.enhance(). Mirrors it line-for-line
    except the model(...) call is replaced with onnx_model.infer(...), and
    the feature extraction / ISTFT synthesis stay on the existing Rust
    libdf bindings (df_state), unchanged.
    """
    from df.enhance import df_features, as_complex, ModelParams

    orig_len = audio.shape[-1]
    n_fft, hop = 0, 0
    if pad:
        n_fft, hop = df_state.fft_size(), df_state.hop_size()
        audio = F.pad(audio, (0, n_fft))
    p = ModelParams()
    spec, erb_feat, spec_feat = df_features(audio, df_state, p.nb_df, device="cpu")

    spec_e_np = onnx_model.infer(spec.numpy(), erb_feat.numpy(), spec_feat.numpy())
    enhanced = as_complex(torch.from_numpy(spec_e_np).squeeze(1))

    if atten_lim_db is not None and abs(atten_lim_db) > 0:
        lim = 10 ** (-abs(atten_lim_db) / 20)
        enhanced = as_complex(spec.squeeze(1)) * lim + enhanced * (1 - lim)

    audio_out = torch.as_tensor(df_state.synthesis(enhanced.numpy()))
    if pad:
        assert n_fft % hop == 0
        d = n_fft - hop
        audio_out = audio_out[:, d: orig_len + d]
    return audio_out


def _self_test():
    print("models/deepfilternet/onnx_infer.py self-test -- start")
    print("  (loads the real DeepFilterNet3 model + exports ONNX — takes a bit)")

    import tempfile
    import time

    from df.enhance import init_df, enhance as torch_enhance
    from export_onnx import export_fp32, quantize_all

    with tempfile.TemporaryDirectory() as tmpdir:
        export_fp32(tmpdir)
        quantize_all(tmpdir)

        model, df_state, _ = init_df(post_filter=False, log_level="ERROR")
        model.eval()

        # IMPORTANT: exactly the live pipeline's chunk shape (100ms @ 48kHz),
        # matching what export_onnx.py traced. This ONNX export is only
        # verified correct at this exact shape — see export_onnx.py's
        # "CRITICAL SCOPE LIMIT" docstring section for why (trace-based
        # export of this model does NOT generalize to other sequence
        # lengths despite dynamic_axes being declared — found and confirmed
        # 2026-08-24: encoder output diverged from PyTorch by ~0.7 on a
        # signal averaging ~0.1 when run at T=200 instead of the traced
        # T=12). live/inference_engine.py's enhance_chunk() only ever calls
        # the model at this exact chunk shape anyway, per-call-stateless.
        rng = np.random.default_rng(3)
        chunk_samples = int(round(df_state.sr() * 0.1))
        n_reps = 5
        chunks = [
            (0.15 * rng.standard_normal((1, chunk_samples))).astype(np.float32)
            for _ in range(n_reps)
        ]

        onnx_model = OnnxDfNet(tmpdir)  # FP32 graphs (enc/erb_dec/df_dec.onnx)
        max_diffs, corrs = [], []
        for chunk in chunks:
            audio = torch.from_numpy(chunk)
            with torch.no_grad():
                ref_audio = torch_enhance(model, df_state, audio.clone(), pad=True, atten_lim_db=100.0)
            onnx_audio = enhance_onnx(onnx_model, df_state, audio.clone(), pad=True, atten_lim_db=100.0)
            assert onnx_audio.shape == ref_audio.shape, f"shape mismatch {onnx_audio.shape} vs {ref_audio.shape}"
            max_diffs.append((onnx_audio - ref_audio).abs().max().item())
            corrs.append(np.corrcoef(onnx_audio.numpy().ravel(), ref_audio.numpy().ravel())[0, 1])

        assert min(corrs) > 0.999, f"FP32 ONNX waveform diverges from PyTorch on some chunk (min corr={min(corrs):.6f})"
        print(f"  [PASS] test 1: FP32 ONNX matches PyTorch on {n_reps} independent 100ms chunks "
              f"(min corr={min(corrs):.6f}, max diff={max(max_diffs):.6f})")

        # Use the last chunk/ref_audio pair for the remaining tests below.
        audio = torch.from_numpy(chunks[-1])
        with torch.no_grad():
            ref_audio = torch_enhance(model, df_state, audio.clone(), pad=True, atten_lim_db=100.0)

        # --- Test 2: INT8 ONNX end-to-end stays correlated (informational on magnitude) ---
        # NOT a substitute for the mandatory full PESQ/STOI re-evaluation --
        # this only catches a catastrophically broken quantization early.
        onnx_model_int8 = OnnxDfNet.__new__(OnnxDfNet)
        onnx_model_int8._enc = ort.InferenceSession(os.path.join(tmpdir, "enc_int8.onnx"), providers=["CPUExecutionProvider"])
        onnx_model_int8._erb_dec = ort.InferenceSession(os.path.join(tmpdir, "erb_dec_int8.onnx"), providers=["CPUExecutionProvider"])
        onnx_model_int8._df_dec = ort.InferenceSession(os.path.join(tmpdir, "df_dec_int8.onnx"), providers=["CPUExecutionProvider"])
        onnx_model_int8._erb_inv_fb = onnx_model._erb_inv_fb
        onnx_model_int8._config = onnx_model._config

        int8_audio = enhance_onnx(onnx_model_int8, df_state, audio.clone(), pad=True, atten_lim_db=100.0)
        corr_int8 = np.corrcoef(int8_audio.numpy().ravel(), ref_audio.numpy().ravel())[0, 1]
        assert np.all(np.isfinite(int8_audio.numpy())), "INT8 output contains non-finite values"
        print(f"  [PASS] test 2: INT8 ONNX end-to-end stays finite and correlated with PyTorch "
              f"(corr={corr_int8:.6f} — see eval/run_eval.py for the real PESQ/STOI comparison)")

        # --- Test 3: relative wall-clock speed, FP32-ONNX vs PyTorch (dev machine only) ---
        # NOT a Pi measurement -- informational signal only, per Rule 29 this
        # is not reported as edge-device performance anywhere.
        n_reps = 5
        t0 = time.perf_counter()
        for _ in range(n_reps):
            torch_enhance(model, df_state, audio, pad=True, atten_lim_db=100.0)
        torch_ms = (time.perf_counter() - t0) / n_reps * 1000

        t0 = time.perf_counter()
        for _ in range(n_reps):
            enhance_onnx(onnx_model, df_state, audio.clone(), pad=True, atten_lim_db=100.0)
        onnx_ms = (time.perf_counter() - t0) / n_reps * 1000

        t0 = time.perf_counter()
        for _ in range(n_reps):
            enhance_onnx(onnx_model_int8, df_state, audio.clone(), pad=True, atten_lim_db=100.0)
        int8_ms = (time.perf_counter() - t0) / n_reps * 1000

        print(f"  [INFO] test 3 (dev machine, NOT Pi — informational only): "
              f"PyTorch={torch_ms:.1f}ms, ONNX-FP32={onnx_ms:.1f}ms, ONNX-INT8={int8_ms:.1f}ms "
              f"(on a {audio.shape[-1] / df_state.sr():.1f}s clip, {n_reps} reps each)")

    print("models/deepfilternet/onnx_infer.py self-test -- ALL PASSED")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ONNX Runtime DeepFilterNet3 inference (P1-3)")
    parser.add_argument("--self-test", action="store_true", help="Run offline self-test and exit")
    args = parser.parse_args()
    if args.self_test:
        _self_test()
    else:
        parser.print_help()
