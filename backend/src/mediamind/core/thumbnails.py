"""JPEG thumbnails generated directly from media files on disk.

Built on `core.loaders` — the same unicode-path-safe, fault-isolated decode
chain used by scans. A file that cannot be decoded yields None; it is NEVER
an exception that escapes to the caller (V0 invariant: one bad file must not
crash a request or a run).
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import NamedTuple

from mediamind.core import loaders
from mediamind.core.scanner import KIND_GIF, KIND_IMAGE, KIND_VIDEO

JPEG_QUALITY = 85

# In-memory cache of encoded thumbnails, keyed by (path, kind, size, mtime,
# file size) so a changed file is never served a stale thumbnail. Bounded by
# total bytes rather than entry count since a 1024px preview is far larger
# than a 64px grid tile. Every thumbnail route (duplicates, faces-adjacent
# file browsing, Explorer file grid) funnels through `media_thumbnail_jpeg`,
# so one cache here covers all of them. Single-process backend (see
# `__main__.py`, no uvicorn `workers=`), so a process-wide dict is safe.
_CACHE_MAX_BYTES = 128 * 1024 * 1024
_cache: "OrderedDict[tuple, bytes]" = OrderedDict()
_cache_bytes = 0
_cache_lock = threading.Lock()


def _cache_key(path: Path, kind: str, size: int) -> tuple | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (str(path), kind, size, st.st_mtime_ns, st.st_size)


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
    that into a placeholder or 4xx, never a 500. Cached by path+size+mtime so
    re-opening a review screen or re-scrolling a grid never re-decodes a file
    it has already thumbnailed.
    """
    global _cache_bytes

    key = _cache_key(path, kind, size)
    if key is not None:
        with _cache_lock:
            cached = _cache.get(key)
            if cached is not None:
                _cache.move_to_end(key)
                return cached

    data = _generate_thumbnail_jpeg(path, kind, size)

    if key is not None and data is not None:
        with _cache_lock:
            _cache[key] = data
            _cache.move_to_end(key)
            _cache_bytes += len(data)
            while _cache_bytes > _CACHE_MAX_BYTES and _cache:
                _, evicted = _cache.popitem(last=False)
                _cache_bytes -= len(evicted)

    return data


def _generate_thumbnail_jpeg(path: Path, kind: str, size: int) -> bytes | None:
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
