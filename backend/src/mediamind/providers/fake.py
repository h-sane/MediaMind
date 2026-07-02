"""Deterministic fake provider so the whole pipeline is testable model-free.

It "recognizes" the dominant color of a frame: any sufficiently bright frame
contains one face whose embedding is the L2-normalized mean BGR color. Test
fixtures made of solid-color images therefore cluster by color — red images
become one person, blue another — while near-black frames have no face.
"""

from __future__ import annotations

import numpy as np

from mediamind.providers.base import DetectedFace


class FakeColorProvider:
    id = "fake-color"
    embedding_dim = 3

    def __init__(self, brightness_threshold: float = 20.0):
        self._threshold = brightness_threshold

    def prepare(self) -> None:  # nothing to load
        pass

    def get_faces(self, frame_bgr: np.ndarray) -> list[DetectedFace]:
        mean = frame_bgr.reshape(-1, frame_bgr.shape[-1]).mean(axis=0).astype(np.float32)
        if float(mean.sum()) < self._threshold:
            return []  # "no face" — near-black frame
        h, w = frame_bgr.shape[:2]
        embedding = mean / (np.linalg.norm(mean) or 1.0)
        return [DetectedFace(bbox=(0.0, 0.0, float(w), float(h)), embedding=embedding)]
