"""
models/noise_classifier/model.py — Small PyTorch log-mel CNN for 3-class noise classification.

Classes: STATIONARY (0) / NON_STATIONARY (1) / IMPULSIVE (2)
Input:   log-mel spectrogram, shape (batch, 1, n_mels, n_frames)
Output:  logits, shape (batch, 3)

Architecture: two conv blocks + global average pooling + FC head.
No new heavy dependency: torch is already in the environment.
"""

import torch
import torch.nn as nn

# Mel parameters must match classify_chunk.py preprocessing
N_MELS = 64
N_FRAMES = 64    # number of time frames per chunk (~667ms at 48kHz/hop512)
_N_FFT = 1024    # FFT size for mel spectrogram (must match train.py and classify_chunk.py)

CLASSES = ["STATIONARY", "NON_STATIONARY", "IMPULSIVE"]


class NoiseClassifierCNN(nn.Module):
    def __init__(self, n_classes: int = 3):
        super().__init__()
        self.features = nn.Sequential(
            # Block 1
            nn.Conv2d(1, 32, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),   # → (32, n_mels//2, n_frames//2)

            # Block 2
            nn.Conv2d(32, 64, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),   # → (64, n_mels//4, n_frames//4)

            # Block 3
            nn.Conv2d(64, 128, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d(1),  # → (128, 1, 1) — global average pool
        )
        self.classifier = nn.Linear(128, n_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = x.view(x.size(0), -1)
        return self.classifier(x)


def build_model(n_classes: int = 3) -> NoiseClassifierCNN:
    return NoiseClassifierCNN(n_classes=n_classes)
