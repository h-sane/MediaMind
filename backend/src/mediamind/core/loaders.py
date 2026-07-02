"""Robust media decoding: images (incl. HEIC/AVIF), GIFs, and videos.

Ported from V0 `sort_media.py`. Guarantees preserved:
- unicode-path-safe (cv2 -> np.fromfile+imdecode -> PIL fallback chain)
- a file that cannot be decoded yields no frames; it is NEVER an exception
  that escapes to the caller and never a lost file (callers route it to a
  visible holding area).

cv2/PIL are imported lazily so that importing this module stays cheap and
model-free test runs don't pay OpenCV startup costs until needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import numpy as np

_HEIF_REGISTERED = False

# Cap for videos that don't report a frame count (V0 behavior).
_MAX_SEQUENTIAL_FRAMES = 6000


def _register_heif() -> None:
    global _HEIF_REGISTERED
    if _HEIF_REGISTERED:
        return
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:
        pass  # HEIC just won't decode; those files stay safe, just unprocessed.
    _HEIF_REGISTERED = True


def load_image(path: Path) -> np.ndarray | None:
    """Return a BGR ndarray, or None if the file can't be decoded."""
    import cv2

    img = cv2.imread(str(path))
    if img is None:
        try:
            data = np.fromfile(str(path), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        except Exception:
            img = None
    if img is None:
        _register_heif()
        try:
            from PIL import Image

            with Image.open(str(path)) as im:
                img = np.ascontiguousarray(np.array(im.convert("RGB"))[:, :, ::-1])
        except Exception:
            img = None
    return img


def sample_gif_frames(path: Path, n: int) -> Iterator[np.ndarray]:
    """Yield up to `n` evenly spaced BGR frames from a GIF."""
    try:
        from PIL import Image, ImageSequence

        with Image.open(str(path)) as im:
            frames = [f.convert("RGB") for f in ImageSequence.Iterator(im)]
    except Exception:
        return
    if not frames:
        return
    idxs = sorted(set(np.linspace(0, len(frames) - 1, min(n, len(frames))).astype(int).tolist()))
    for i in idxs:
        yield np.ascontiguousarray(np.array(frames[i])[:, :, ::-1])


def sample_video_frames(path: Path, n: int) -> Iterator[np.ndarray]:
    """Yield up to `n` evenly spaced BGR frames from a video."""
    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap.release()
        return
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total > 0:
            idxs = sorted(set(np.linspace(0, total - 1, min(n, total)).astype(int).tolist()))
            for idx in idxs:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ok, frame = cap.read()
                if ok and frame is not None:
                    yield frame
        else:
            # Unknown length: read sequentially with a hard cap on the work.
            frames: list[np.ndarray] = []
            ok, frame = cap.read()
            while ok and len(frames) < _MAX_SEQUENTIAL_FRAMES:
                frames.append(frame)
                ok, frame = cap.read()
            if frames:
                idxs = sorted(
                    set(np.linspace(0, len(frames) - 1, min(n, len(frames))).astype(int).tolist())
                )
                for i in idxs:
                    yield frames[i]
    finally:
        cap.release()
