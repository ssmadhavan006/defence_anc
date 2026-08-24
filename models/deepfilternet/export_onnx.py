"""
models/deepfilternet/export_onnx.py — Export DeepFilterNet3's neural
submodules (encoder, ERB decoder, deep-filter decoder) to ONNX, and
INT8-quantize them (P1-3).

Why 3 separate graphs, not one unified graph: DfNet.forward() combines the
neural network output with the original spectrogram using PyTorch's native
complex-tensor ops (`torch.view_as_complex`, inside `df_op` — the deep
filtering stage — and used transitively elsewhere). ONNX has no native
complex dtype and opset 14 cannot represent `view_as_complex` at all;
torch's newer dynamo-based exporter gets past that specific op but hits an
unrelated internal batchnorm-lowering bug in this torch/onnxscript version
combination. Both were tried directly against this model on 2026-08-24
before choosing this approach — see progress.md for the full trail.

The submodules exported here (encoder, ERB decoder, deep-filter-coefficient
decoder) are pure conv/RNN/linear layers with NO complex-tensor ops, so they
export cleanly. The remaining combination logic — ERB mask application and
the deep-filtering complex FIR sum — is a small, well-defined piece of math
that models/deepfilternet/onnx_infer.py reimplements directly in numpy using
real/imaginary components instead of torch's complex dtype, and which is
verified bit-for-bit (max abs diff: 0.0, 2026-08-24) against PyTorch's own
DF.forward()/Mask.forward() on real intermediate tensors before being
trusted for anything downstream. Read onnx_infer.py before touching this.

Also note: df.scripts.export.export()'s own encoder/erb_dec export path
calls `torch.jit.script()` before `torch.onnx.export()`, which raises
`RuntimeError: Unsupported value kind: Tensor` on this torch version (a
TorchScript scripting-compiler issue unrelated to this model). Worked
around by calling `export_impl(..., jit=False)` directly for all three
submodules — tracing instead of scripting.

CRITICAL SCOPE LIMIT, found the hard way (2026-08-24) — read before using
this for anything beyond live/inference_engine.py's exact call pattern:
tracing bakes in behavior specific to the traced sequence length T, DESPITE
`dynamic_axes` declaring T as symbolic in the graph's I/O metadata. Traced
once at T=100 (df's own default: a 1-second dummy clip) and validated
against PyTorch at that same T=100, the graphs matched exactly. Run against
a 2-second clip (T=200) instead, the encoder diverged from PyTorch by ~0.7
on a signal whose own values average ~0.1 — not numerical noise, a real
generalization failure (most likely PyTorch's GRU trace-export not
generalizing to a different sequence length despite the declared dynamic
axis). This is why export here uses the LIVE PIPELINE's actual chunk shape
(100ms @ 48kHz, padded exactly as live/inference_engine.py's enhance_chunk()
does) as the trace input, not an arbitrary 1-second dummy — the live
pipeline calls the model fresh, per-call-stateless, on that exact fixed
chunk shape every single time (see enhance_chunk() calling df.enhance's
enhance() per 100ms chunk with no continuity between calls), so tracing at
that exact shape and NEVER running the exported graph at any other T is a
correct, verified-correct way to use it for live inference — but it means
this exported model is NOT safely usable for arbitrary-length whole-file
batch processing without re-chunking the input into the same fixed
100ms-equivalent pieces first. models/deepfilternet/onnx_infer.py's
self-test validates only at this fixed chunk shape, deliberately.

Usage:
    python models/deepfilternet/export_onnx.py --export-dir results/onnx
    python models/deepfilternet/export_onnx.py --export-dir results/onnx --quantize

Self-test (Mode A — loads the real model, no audio hardware needed):
    python models/deepfilternet/export_onnx.py --self-test
"""

import os
import sys
import json
import argparse

sys.path.insert(0, ".")

import torch
import torch.nn as nn

# Import df_compat FIRST, purely for its side effect: it monkeypatches
# torchaudio.backend.common into sys.modules before df.io/df.enhance get
# imported. Needed on platforms (confirmed: the Pi) where the installed
# torchaudio build has already dropped that deprecated compatibility shim
# entirely -- importing `df.enhance` directly there raises
# ModuleNotFoundError: No module named 'torchaudio.backend'. Every other
# module in this project already goes through this shim (see
# live/inference_engine.py); this one didn't, and broke on the Pi as a
# result (found 2026-08-24).
import models.deepfilternet.df_compat  # noqa: F401

from df.enhance import init_df, df_features, ModelParams
from df.scripts.export import export_impl


class _PaddedEncoder(nn.Module):
    """
    Wraps model.pad_feat + model.enc as one traced unit.

    Why: model.enc alone expects ALREADY pad_feat()-ed inputs — pad_feat is
    an asymmetric ConstantPad2d((0,0,-2,2)) (crops 2 frames off the start,
    appends 2 zero frames at the end — a lookahead shift, not a straight
    pad) applied by DfNet.forward() *before* calling self.enc(...). Tracing
    model.enc directly bakes that expectation into the graph's declared
    input contract, silently mismatched against feeding it the RAW output
    of df_features() at inference time -- found 2026-08-24 when FP32 ONNX
    output correlated only ~0.82 with PyTorch despite every other piece
    (mask application, deep filtering) already being verified exact.
    Wrapping pad_feat into the traced graph itself means the ONNX input
    contract matches df_features()'s raw output directly, with no separate
    padding step to keep in sync by hand at inference time.
    """

    def __init__(self, pad_feat: nn.Module, enc: nn.Module):
        super().__init__()
        self.pad_feat = pad_feat
        self.enc = enc

    def forward(self, feat_erb, feat_spec):
        return self.enc(self.pad_feat(feat_erb), self.pad_feat(feat_spec))


def export_fp32(export_dir: str) -> dict:
    """
    Export encoder, ERB decoder, and deep-filter decoder to ONNX (traced,
    FP32), using this project's actual production config (post_filter=False
    — matches live/inference_engine.py's init_df() call exactly).

    Returns a dict of {name: path} for the three exported .onnx files, plus
    writes df_config.json (frame_size, lookahead, num_freqs, erb bins, and
    the ERB inverse filterbank matrix) that onnx_infer.py needs to
    reconstruct DfNet.forward()'s combination logic outside of ONNX.
    """
    os.makedirs(export_dir, exist_ok=True)
    model, df_state, suffix = init_df(post_filter=False, log_level="ERROR")
    model.eval()

    paths = {}
    with torch.no_grad():
        p = ModelParams()
        # Trace at the EXACT shape live/inference_engine.py's enhance_chunk()
        # always uses: a 100ms chunk, padded by n_fft samples (pad=True in
        # df.enhance.enhance()). See the module docstring's "CRITICAL SCOPE
        # LIMIT" section for why this must match exactly, not an arbitrary
        # dummy length.
        chunk_samples = int(round(p.sr * 0.1))
        n_fft = df_state.fft_size()
        audio = torch.zeros((1, chunk_samples))
        audio = torch.nn.functional.pad(audio, (0, n_fft))
        spec, feat_erb, feat_spec = df_features(audio, df_state, p.nb_df, device="cpu")
        feat_spec2 = feat_spec.transpose(1, 4).squeeze(4)

        # --- encoder (pad_feat included in the traced graph — see _PaddedEncoder) ---
        padded_enc = _PaddedEncoder(model.pad_feat, model.enc)
        inputs = (feat_erb, feat_spec2)
        e0, e1, e2, e3, emb, c0, lsnr = export_impl(
            os.path.join(export_dir, "enc.onnx"), padded_enc, inputs=inputs,
            input_names=["feat_erb", "feat_spec"],
            output_names=["e0", "e1", "e2", "e3", "emb", "c0", "lsnr"],
            dynamic_axes={"feat_erb": {2: "S"}, "feat_spec": {2: "S"}, "e0": {2: "S"},
                          "e1": {2: "S"}, "e2": {2: "S"}, "e3": {2: "S"}, "emb": {1: "S"},
                          "c0": {2: "S"}, "lsnr": {1: "S"}},
            jit=False, check=True, simplify=False,
        )
        paths["enc"] = os.path.join(export_dir, "enc.onnx")

        # --- ERB decoder ---
        inputs = (emb.clone(), e3, e2, e1, e0)
        export_impl(
            os.path.join(export_dir, "erb_dec.onnx"), model.erb_dec, inputs=inputs,
            input_names=["emb", "e3", "e2", "e1", "e0"], output_names=["m"],
            dynamic_axes={"emb": {1: "S"}, "e3": {2: "S"}, "e2": {2: "S"}, "e1": {2: "S"},
                          "e0": {2: "S"}, "m": {2: "S"}},
            jit=False, check=True, simplify=False,
        )
        paths["erb_dec"] = os.path.join(export_dir, "erb_dec.onnx")

        # --- deep-filter decoder ---
        inputs = (emb.clone(), c0)
        export_impl(
            os.path.join(export_dir, "df_dec.onnx"), model.df_dec, inputs=inputs,
            input_names=["emb", "c0"], output_names=["coefs"],
            dynamic_axes={"emb": {1: "S"}, "c0": {2: "S"}, "coefs": {1: "S"}},
            jit=False, check=True, simplify=False,
        )
        paths["df_dec"] = os.path.join(export_dir, "df_dec.onnx")

    # Everything onnx_infer.py needs to reconstruct DfNet.forward()'s
    # combination logic without loading PyTorch/the checkpoint again.
    config = {
        "frame_size": int(model.df_op.frame_size),
        "lookahead": int(model.df_op.lookahead),
        "num_freqs": int(model.df_op.num_freqs),
        "nb_df": int(model.nb_df),
        "erb_bins": int(model.erb_bins),
        "sample_rate": int(df_state.sr()),
    }
    with open(os.path.join(export_dir, "df_config.json"), "w") as f:
        json.dump(config, f, indent=2)

    import numpy as np
    np.save(os.path.join(export_dir, "erb_inv_fb.npy"), model.mask.erb_inv_fb.numpy())

    paths["config"] = os.path.join(export_dir, "df_config.json")
    paths["erb_inv_fb"] = os.path.join(export_dir, "erb_inv_fb.npy")
    return paths


def quantize_all(export_dir: str) -> dict:
    """
    INT8 dynamic-quantize all three exported graphs. See onnx_infer.py's
    module docstring for why dynamic (not static/calibrated) quantization.

    Explicitly includes Conv in op_types_to_quantize: onnxruntime's default
    dynamic-quantization op set targets MatMul/Gemm (linear layers) and
    skips Conv unless asked. DeepFilterNet3's encoder/decoders are
    Conv-heavy (verified 2026-08-24: default settings shrank the model only
    ~1%; with Conv included, aggregate size drops much further — see the
    self-test for the measured number on this checkpoint).
    """
    from onnxruntime.quantization import quantize_dynamic, QuantType

    quant_paths = {}
    for name in ("enc", "erb_dec", "df_dec"):
        src = os.path.join(export_dir, f"{name}.onnx")
        dst = os.path.join(export_dir, f"{name}_int8.onnx")
        quantize_dynamic(
            model_input=src, model_output=dst, weight_type=QuantType.QInt8,
            op_types_to_quantize=["Conv", "MatMul", "Gemm"],
        )
        quant_paths[name] = dst
    return quant_paths


def _self_test():
    print("models/deepfilternet/export_onnx.py self-test -- start")
    print("  (loads the real DeepFilterNet3 model — this will take a few seconds)")

    import tempfile
    import onnx as onnx_pkg

    with tempfile.TemporaryDirectory() as tmpdir:
        paths = export_fp32(tmpdir)

        # --- Test 1: all three files exist and are non-trivially sized ---
        for name in ("enc", "erb_dec", "df_dec"):
            assert os.path.exists(paths[name]), f"{name}.onnx not created"
            size_kb = os.path.getsize(paths[name]) / 1024
            assert size_kb > 1, f"{name}.onnx suspiciously small: {size_kb:.2f} KB"
        print("  [PASS] test 1: all three ONNX files created with plausible sizes")

        # --- Test 2: onnx.checker validates each graph structurally ---
        for name in ("enc", "erb_dec", "df_dec"):
            onnx_pkg.checker.check_model(onnx_pkg.load(paths[name]), full_check=True)
        print("  [PASS] test 2: onnx.checker validates all three exported graphs")

        # --- Test 3: config.json and erb_inv_fb.npy are present and sane ---
        assert os.path.exists(paths["config"])
        assert os.path.exists(paths["erb_inv_fb"])
        with open(paths["config"]) as f:
            cfg = json.load(f)
        assert cfg["frame_size"] > 0 and cfg["num_freqs"] > 0
        print(f"  [PASS] test 3: df_config.json / erb_inv_fb.npy present, config={cfg}")

        # --- Test 4: INT8 quantization runs, aggregate size shrinks ---
        # Checked in aggregate, not per-graph: a small graph's quantization
        # overhead (scale/zero-point tensors) can slightly outweigh its int8
        # savings even when the model overall shrinks substantially — that's
        # an expected artifact of dynamic quantization on tiny graphs, not a
        # correctness problem.
        quant_paths = quantize_all(tmpdir)
        fp32_total_kb = sum(os.path.getsize(paths[n]) for n in ("enc", "erb_dec", "df_dec")) / 1024
        int8_total_kb = sum(os.path.getsize(quant_paths[n]) for n in ("enc", "erb_dec", "df_dec")) / 1024
        assert int8_total_kb < fp32_total_kb, (
            f"aggregate quantized size ({int8_total_kb:.1f}KB) not smaller than "
            f"FP32 ({fp32_total_kb:.1f}KB)"
        )
        print(f"  [PASS] test 4: INT8 quantization applied to all three graphs, "
              f"aggregate {fp32_total_kb:.0f}KB -> {int8_total_kb:.0f}KB "
              f"({100 * (1 - int8_total_kb / fp32_total_kb):.0f}% smaller)")

    print("models/deepfilternet/export_onnx.py self-test -- ALL PASSED")
    print("NOTE: this only checks export mechanics. For full correctness "
          "(FP32-ONNX and INT8-ONNX vs PyTorch, end-to-end through synthesis), "
          "see models/deepfilternet/onnx_infer.py --self-test.")


def main():
    parser = argparse.ArgumentParser(description="Export DeepFilterNet3 submodules to ONNX and optionally quantize (P1-3)")
    parser.add_argument("--export-dir", default="results/onnx", help="Output directory")
    parser.add_argument("--quantize", action="store_true", help="Also produce INT8 dynamic-quantized models")
    parser.add_argument("--self-test", action="store_true", help="Run offline self-test and exit")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    paths = export_fp32(args.export_dir)
    for name in ("enc", "erb_dec", "df_dec"):
        print(f"{name}.onnx: {paths[name]} ({os.path.getsize(paths[name]) / 1024:.0f} KB)")

    if args.quantize:
        quant_paths = quantize_all(args.export_dir)
        for name in ("enc", "erb_dec", "df_dec"):
            print(f"{name}_int8.onnx: {quant_paths[name]} ({os.path.getsize(quant_paths[name]) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
