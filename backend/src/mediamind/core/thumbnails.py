"""JPEG thumbnails generated directly from media files on disk.

Built on `core.loaders` — the same unicode-path-safe, fault-isolated decode
chain used by scans. A file that cannot be decoded yields None; it is NEVER
an exception that escapes to the caller (V0 invariant: one bad file must not
crash a request or a run).
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from mediamind.core import loaders
from mediamind.core.scanner import KIND_GIF, KIND_IMAGE, KIND_VIDEO

JPEG_QUALITY = 85


class MediaMetadata(NamedTuple):
    width: int
    height: int
    duration_seconds: float | None  # None for images/GIFs


def _first_frame(path: Path, kind: str):
    """Return the first decodable BGR frame of a media file, or None."""
    if kind == KIND_IMAGE:
        return loaders.load_image(path)
    if kind == KIND_GIF:
        return next(loaders.sample_gif_frames(path, 1), None)
    if kind == KIND_VIDEO:
        return next(loaders.sample_video_frames(path, 1), None)
    return None


def media_thumbnail_jpeg(path: Path, kind: str, size: int) -> bytes | None:
    """Encode a thumbnail of `path` as JPEG bytes (longest edge <= `size`).

    Works for images, GIFs (first frame), and videos (first sampled frame).
    Never upscales. Returns None on any decode/encode failure — callers turn
    that into a placeholder or 4xx, never a 500.
    """
    try:
        frame = _first_frame(path, kind)
        if frame is None:
            return None

        import cv2

        h, w = frame.shape[:2]
        if max(h, w) == 0:
            return None
        scale = size / max(h, w)
        if scale < 1.0:
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        return bytes(buf) if ok else None
    except Exception:
        return None


def media_metadata(path: Path, kind: str) -> MediaMetadata | None:
    """Dimensions (and, for video, duration) for the preview pane.

    Video reads its own dimensions/frame-count/fps directly from
    `cv2.VideoCapture` rather than decoding a frame via `_first_frame` —
    those properties are available without touching pixel data. Images/GIFs
    fall back to decoding the first frame, same as the thumbnail path.
    Never raises: any decode/property failure yields None, same contract as
    `media_thumbnail_jpeg`.
    """
    try:
        import cv2

        if kind == KIND_VIDEO:
            cap = cv2.VideoCapture(str(path))
            try:
                if not cap.isOpened():
                    return None
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                duration = frame_count / fps if fps > 0 and frame_count > 0 else None
            finally:
                cap.release()
            if width <= 0 or height <= 0:
                return None
            return MediaMetadata(width=width, height=height, duration_seconds=duration)

        frame = _first_frame(path, kind)
        if frame is None:
            return None
        height, width = frame.shape[:2]
        if width <= 0 or height <= 0:
            return None
        return MediaMetadata(width=width, height=height, duration_seconds=None)
    except Exception:
        return None
