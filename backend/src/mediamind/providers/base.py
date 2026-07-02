"""The face-recognition provider interface.

A provider turns a frame into detected faces with embeddings. Everything
above this interface (frame sampling, clustering, identities, review) is
provider-agnostic, so models are swappable plugins.

Design note: detection and embedding are one call (`get_faces`) rather than
separate detect/embed steps because every real backend (InsightFace included)
computes both in a single pass; splitting the interface would force providers
to cache intermediate state for no benefit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True)
class DetectedFace:
    """One face in one frame."""

    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2 (pixels)
    embedding: np.ndarray  # L2-normalized, provider.embedding_dim floats

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]


@runtime_checkable
class FaceProvider(Protocol):
    """Implemented by every face-recognition plugin."""

    id: str
    embedding_dim: int

    def prepare(self) -> None:
        """Load model weights. Called once before the first get_faces()."""
        ...

    def get_faces(self, frame_bgr: np.ndarray) -> list[DetectedFace]:
        """Detect faces and compute their embeddings for one BGR frame."""
        ...
