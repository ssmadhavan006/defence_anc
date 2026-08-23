"""
Compatibility module for DeepFilterNet across PyTorch / torchaudio versions.
Fixes:
- 'ModuleNotFoundError: No module named torchaudio.backend'
- 'AttributeError: module torchaudio has no attribute info'
on PyTorch 2.6+ / Python 3.13.
"""
import sys
import types
import soundfile as sf
import torch
import torchaudio as ta

class AudioMetaData:
    def __init__(self, sample_rate: int, num_frames: int, num_channels: int, bits_per_sample: int = 16, encoding: str = "PCM_S"):
        self.sample_rate = sample_rate
        self.num_frames = num_frames
        self.num_channels = num_channels
        self.bits_per_sample = bits_per_sample
        self.encoding = encoding

def _polyfilled_info(file: str, **kwargs) -> AudioMetaData:
    info = sf.info(file)
    return AudioMetaData(
        sample_rate=info.samplerate,
        num_frames=info.frames,
        num_channels=info.channels
    )

def _polyfilled_load(file: str, **kwargs):
    data, sr = sf.read(file, dtype="float32")
    if data.ndim == 1:
        tensor = torch.from_numpy(data).unsqueeze(0)
    else:
        tensor = torch.from_numpy(data.T)
    return tensor, sr

def _polyfilled_save(filepath: str, tensor: torch.Tensor, sr: int, **kwargs):
    data = tensor.cpu().detach().numpy()
    if data.ndim == 2:
        data = data.T
    sf.write(filepath, data, sr)

# Inject soundfile-backed torchaudio functions if missing or deprecated
if not hasattr(ta, "info"):
    ta.info = _polyfilled_info
if not hasattr(ta, "load"):
    ta.load = _polyfilled_load
if not hasattr(ta, "save"):
    ta.save = _polyfilled_save

# Polyfill torchaudio.backend.common
if not hasattr(ta, "backend"):
    backend = types.ModuleType("backend")
    common = types.ModuleType("common")
    common.AudioMetaData = AudioMetaData
    backend.common = common
    sys.modules["torchaudio.backend"] = backend
    sys.modules["torchaudio.backend.common"] = common
    ta.backend = backend
elif not hasattr(ta.backend, "common"):
    common = types.ModuleType("common")
    common.AudioMetaData = AudioMetaData
    sys.modules["torchaudio.backend.common"] = common
    ta.backend.common = common

from df.enhance import init_df, enhance
from df.io import load_audio, save_audio, resample

__all__ = ["init_df", "enhance", "load_audio", "save_audio", "resample"]
