"""JPEG thumbnails generated directly from media files on disk.

Built on `core.loaders` — the same unicode-path-safe, fault-isolated decode
chain used by scans. A file that cannot be decoded yields None; it is NEVER
an exception that escapes to the caller (V0 invariant: one bad file must not
crash a request or a run).
"""

from __future__ import annotations

import hashlib
import os
import random
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path
from typing import NamedTuple

from mediamind.config import thumbnail_cache_dir
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


def _mem_store(key: tuple, data: bytes) -> None:
    global _cache_bytes
    with _cache_lock:
        if key in _cache:
            return
        _cache[key] = data
        _cache.move_to_end(key)
        _cache_bytes += len(data)
        while _cache_bytes > _CACHE_MAX_BYTES and _cache:
            _, evicted = _cache.popitem(last=False)
            _cache_bytes -= len(evicted)


# Persistent on-disk L2 cache: survives app relaunch, so the *second* time a
# folder is opened its thumbnails load from disk instead of re-decoding every
# original. Keyed by the same (path, kind, size, mtime, filesize) identity as
# the in-memory L1 — a changed file gets a new filename, so a stale thumbnail
# is never served. Size-capped with LRU eviction (below) so the cache dir
# never grows unbounded.

_DISK_CACHE_MAX_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB; tiles are ~5-15 KB, previews larger
_DISK_CACHE_EVICT_TARGET = int(_DISK_CACHE_MAX_BYTES * 0.9)  # hysteresis: don't re-trigger next write
_DISK_EVICT_CHECK_PROBABILITY = 1 / 500  # amortize the full-tree walk instead of walking every write


def _disk_path(key: tuple) -> Path:
    digest = hashlib.sha1(repr(key).encode("utf-8")).hexdigest()
    return thumbnail_cache_dir() / digest[:2] / f"{digest}.jpg"


def _disk_get(key: tuple) -> bytes | None:
    p = _disk_path(key)
    try:
        data = p.read_bytes()
    except OSError:
        return None
    try:
        os.utime(p, None)  # mark as recently used for LRU eviction
    except OSError:
        pass
    return data


def _disk_put(key: tuple, data: bytes) -> None:
    p = _disk_path(key)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: a crash mid-write never leaves a truncated JPEG that
        # would later be served as a corrupt thumbnail.
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, p)
    except OSError:
        return  # best-effort cache; a write failure just costs a re-decode later
    if random.random() < _DISK_EVICT_CHECK_PROBABILITY:
        _evict_disk_cache_if_over_cap()


def _evict_disk_cache_if_over_cap() -> None:
    """Walk the on-disk cache and delete oldest-mtime entries until back under
    the cap. A full-tree walk is not cheap at scale, so `_disk_put` only calls
    this probabilistically rather than on every write."""
    entries: list[tuple[int, int, Path]] = []  # (mtime_ns, size, path)
    total = 0
    for entry in thumbnail_cache_dir().rglob("*.jpg"):
        try:
            st = entry.stat()
        except OSError:
            continue
        entries.append((st.st_mtime_ns, st.st_size, entry))
        total += st.st_size
    if total <= _DISK_CACHE_MAX_BYTES:
        return
    entries.sort(key=lambda e: e[0])  # least-recently-used first
    for _, size, path in entries:
        if total <= _DISK_CACHE_EVICT_TARGET:
            break
        try:
            path.unlink()
            total -= size
        except OSError:
            pass


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
    key = _cache_key(path, kind, size)
    if key is not None:
        with _cache_lock:
            cached = _cache.get(key)
            if cached is not None:
                _cache.move_to_end(key)
                return cached
        disk = _disk_get(key)
        if disk is not None:
            _mem_store(key, disk)  # promote L2 -> L1
            return disk

    data = _generate_thumbnail_jpeg(path, kind, size)

    if key is not None and data is not None:
        _mem_store(key, data)
        _disk_put(key, data)

    return data


def _draft_decode_bgr(path: Path, size: int):
    """Decode a still image *small* via PIL `Image.draft`, returning a BGR
    ndarray, or None to fall back to the full cv2/PIL chain.

    `draft` asks libjpeg to DCT-scale a JPEG during decode to the nearest
    1/2/4/8 >= the requested box, so we never materialise the full-resolution
    pixels just to shrink them — 4-16x faster on large photos, which is the
    Phase-1 win. It only *decodes* small; the existing cv2 resize+encode below
    still runs (cv2's INTER_AREA + imencode is faster than PIL's for the final
    step, so we keep it). A no-op scale on non-JPEG formats, which still decode
    correctly. Orientation is applied via EXIF to match cv2.imread's default
    auto-rotate. Any failure returns None -> unicode-safe cv2/PIL fallback
    (which also registers HEIC)."""
    try:
        import numpy as np
        from PIL import Image, ImageOps

        with Image.open(str(path)) as im:
            im.draft("RGB", (size, size))
            im = ImageOps.exif_transpose(im)
            rgb = np.asarray(im.convert("RGB"))
        if rgb.ndim != 3 or rgb.shape[2] != 3:
            return None
        return np.ascontiguousarray(rgb[:, :, ::-1])  # BGR, like loaders
    except Exception:
        return None


def _generate_thumbnail_jpeg(path: Path, kind: str, size: int) -> bytes | None:
    try:
        frame = None
        if kind == KIND_IMAGE:
            frame = _draft_decode_bgr(path, size)
        if frame is None:
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
