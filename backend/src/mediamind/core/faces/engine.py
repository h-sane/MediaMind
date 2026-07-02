"""Face extraction over mixed media (ported from V0's analyze loop).

For each file: decode frames (1 for an image, N sampled for GIF/video), run
the provider on every frame, keep faces above the minimum size. Per-file
fault isolation is preserved — one bad file can never crash a scan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterator

import numpy as np

from mediamind.core import loaders
from mediamind.core.scanner import KIND_GIF, KIND_IMAGE, KIND_VIDEO, ScannedFile
from mediamind.providers.base import FaceProvider

DEFAULT_VIDEO_FRAMES = 15
DEFAULT_GIF_FRAMES = 8
DEFAULT_MIN_FACE_SIZE = 40


@dataclass
class MediaFaces:
    """Face-extraction result for one media file."""

    file: ScannedFile
    decoded_ok: bool
    embeddings: list[np.ndarray] = field(default_factory=list)


def _frames_for(file: ScannedFile, video_frames: int, gif_frames: int) -> Iterator[np.ndarray]:
    if file.kind == KIND_IMAGE:
        img = loaders.load_image(file.path)
        if img is not None:
            yield img
    elif file.kind == KIND_GIF:
        yield from loaders.sample_gif_frames(file.path, gif_frames)
    elif file.kind == KIND_VIDEO:
        yield from loaders.sample_video_frames(file.path, video_frames)


def extract_faces(
    files: list[ScannedFile],
    provider: FaceProvider,
    *,
    video_frames: int = DEFAULT_VIDEO_FRAMES,
    gif_frames: int = DEFAULT_GIF_FRAMES,
    min_face_size: int = DEFAULT_MIN_FACE_SIZE,
    progress: Callable[[int, int, ScannedFile], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[MediaFaces]:
    provider.prepare()
    results: list[MediaFaces] = []
    total = len(files)

    for i, file in enumerate(files, 1):
        result = MediaFaces(file=file, decoded_ok=False)
        try:
            for frame in _frames_for(file, video_frames, gif_frames):
                if frame is None:
                    continue
                result.decoded_ok = True
                for face in provider.get_faces(frame):
                    if face.width < min_face_size or face.height < min_face_size:
                        continue
                    result.embeddings.append(np.asarray(face.embedding, dtype=np.float32))
        except Exception:
            # Fault isolation: an undecodable/corrupt file is recorded as
            # not-decoded and the scan continues.
            result.decoded_ok = False
            result.embeddings.clear()
        results.append(result)
        if progress is not None:
            progress(i, total, file)
        if should_cancel is not None and should_cancel():
            break
    return results
