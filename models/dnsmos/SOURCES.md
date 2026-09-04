# SOURCES.md — models/dnsmos/

## Model: DNSMOS P.835 — `sig_bak_ovr.onnx`

| Field | Value |
|---|---|
| **Name** | DNSMOS P.835 (non-intrusive perceptual objective speech quality metric) |
| **Version / Commit** | DNS-Challenge GitHub, commit `5e8a990` (2022-05-10) |
| **Source URL** | https://github.com/microsoft/DNS-Challenge/tree/master/DNSMOS/DNSMOS |
| **Direct download** | `python models/dnsmos/download_model.py` |
| **Licence** | MIT — see https://github.com/microsoft/DNS-Challenge/blob/master/LICENSE |
| **Citation** | Reddy, C. K. A., Gopal, V., & Cutler, R. (2022). DNSMOS P.835: A non-intrusive perceptual objective speech quality metric to evaluate noise suppressors. *ICASSP 2022*. |
| **Model size** | ~4.8 MB (ONNX FP32) |
| **Downloaded** | (fill in date and SHA-256 when model is obtained) |
| **SHA-256** | (fill in after download) |

## What it does

The `sig_bak_ovr.onnx` model produces three perceptual quality scores:

| Score | Name | What it measures | Range |
|---|---|---|---|
| **SIG** | Signal quality | Speech clarity / distortion | 1–5 |
| **BAK** | Background noise quality | Residual noise level | 1–5 |
| **OVR** | Overall quality | Combined perceptual quality | 1–5 |

Higher is better. A score of **< 2.5** on OVR is used as a warning threshold
(configurable via `dnsmos.warn_threshold` in `config/audio_config.yaml`).

## Inputs

| Field | Value |
|---|---|
| **Expected sample rate** | 16 kHz (pipeline resamples from 48 kHz) |
| **Window length** | 9.01 seconds (144,160 samples at 16 kHz) |
| **Preprocessing** | Log-mel spectrogram: n_mels=120, frame_size=320, hop_length=160 |
| **ONNX input name** | `input_1` |
| **ONNX input shape** | `(1, 1, ~901, 120)` — (batch, channel, frames, mels) |

## What it does NOT do

- Does not evaluate speaker intelligibility (STOI) or signal-to-noise ratio (SI-SNR).
- Has not been validated on defence noise categories specifically; it was trained on
  general speech enhancement benchmarks.
- Is not a substitute for a full PESQ/STOI evaluation (which requires a clean reference).
- OVR < 2.5 is a warning trigger, not a proof of failure — it may fire on quiet segments.

## Licence compliance

The MIT licence permits use, modification, and redistribution with attribution.
The model weights are included only if downloaded via `download_model.py`; they are
not committed to this repository. Attribution: Microsoft Corporation, DNS-Challenge 2022.
