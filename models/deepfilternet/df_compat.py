"""
Universal compatibility module for DeepFilterNet across PyTorch / torchaudio versions.
Completely replaces torchaudio file I/O with soundfile to bypass torchcodec/backend deprecations
on PyTorch 2.6+ / Python 3.13 on Raspberry Pi 5 and Linux/Windows environments.
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

def _soundfile_info(file: str, **kwargs) -> AudioMetaData:
    info = sf.info(file)
    return AudioMetaData(
        sample_rate=info.samplerate,
        num_frames=info.frames,
        num_channels=info.channels
    )

def _soundfile_load(file: str, **kwargs):
    data, sr = sf.read(file, dtype="float32")
    if data.ndim == 1:
        tensor = torch.from_numpy(data).unsqueeze(0)
    else:
        tensor = torch.from_numpy(data.T)
    return tensor, sr

def _soundfile_save(filepath: str, tensor: torch.Tensor, sr: int, **kwargs):
    data = tensor.cpu().detach().numpy()
    if data.ndim == 2:
        data = data.T
    sf.write(filepath, data, sr)

# Inject soundfile-backed I/O into torchaudio namespace
ta.info = _soundfile_info
ta.load = _soundfile_load
ta.save = _soundfile_save

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

# Now import df modules
import df.io
from df.enhance import init_df, enhance

def load_audio(file: str, sr=None, verbose=True, **kwargs):
    """
    Robust soundfile-backed load_audio replacing df.io.load_audio.
    """
    data, orig_sr = sf.read(file, dtype="float32")
    if data.ndim == 1:
        audio = torch.from_numpy(data).unsqueeze(0)
    else:
        audio = torch.from_numpy(data.T)
    info = AudioMetaData(orig_sr, audio.shape[-1], audio.shape[0])
    if sr is not None and orig_sr != sr:
        audio = df.io.resample(audio, orig_sr, sr)
    return audio.contiguous(), info

def save_audio(file: str, audio, sr: int, **kwargs):
    """
    Robust soundfile-backed save_audio replacing df.io.save_audio.
    """
    data = torch.as_tensor(audio).cpu().detach().numpy()
    if data.ndim == 2:
        data = data.T
    sf.write(file, data, sr)

# Monkey-patch df.io functions directly for complete isolation
df.io.load_audio = load_audio
df.io.save_audio = save_audio

__all__ = ["init_df", "enhance", "load_audio", "save_audio", "resample"]
def resample(audio: torch.Tensor, orig_sr: int, new_sr: int, method: str = "sinc_fast"):
    return df.io.resample(audio, orig_sr, new_sr, method=method)
