"""
Compatibility module for DeepFilterNet across PyTorch / torchaudio versions.
Fixes 'ModuleNotFoundError: No module named torchaudio.backend' on PyTorch 2.6+ / Python 3.13.
"""
import sys
import types
import torchaudio

# Polyfill torchaudio.backend.common for PyTorch/torchaudio 2.6+ where backend.common was removed
if not hasattr(torchaudio, "backend"):
    backend = types.ModuleType("backend")
    common = types.ModuleType("common")
    common.AudioMetaData = getattr(torchaudio, "AudioMetaData", None)
    backend.common = common
    sys.modules["torchaudio.backend"] = backend
    sys.modules["torchaudio.backend.common"] = common
    torchaudio.backend = backend
elif not hasattr(torchaudio.backend, "common"):
    common = types.ModuleType("common")
    common.AudioMetaData = getattr(torchaudio, "AudioMetaData", None)
    sys.modules["torchaudio.backend.common"] = common
    torchaudio.backend.common = common

from df.enhance import init_df, enhance
from df.io import load_audio, save_audio, resample

__all__ = ["init_df", "enhance", "load_audio", "save_audio", "resample"]
