"""ADR-0004: a content-hash-keyed thumbnail keeps serving after the original
goes offline (drive unmounted), because the cache key needs no live stat()."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from mediamind.core import thumbnails


@pytest.fixture
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "thumb_cache"
    d.mkdir()
    monkeypatch.setattr(thumbnails, "thumbnail_cache_dir", lambda: d)
    thumbnails._cache.clear()  # isolate from any in-memory cache carried across tests
    return d


def _make_image(path: Path) -> None:
    import cv2

    cv2.imwrite(str(path), np.full((64, 64, 3), 128, dtype=np.uint8))


def test_content_hash_thumbnail_survives_offline_original(cache_dir, tmp_path):
    img = tmp_path / "photo.jpg"
    _make_image(img)

    warm = thumbnails.media_thumbnail_jpeg(img, "image", 48, content_hash="deadbeef")
    assert warm is not None

    thumbnails._cache.clear()  # force a disk-cache (L2) lookup, not the in-memory hit
    img.unlink()  # simulate the drive unmounting: original is now unreachable

    offline = thumbnails.media_thumbnail_jpeg(img, "image", 48, content_hash="deadbeef")
    assert offline == warm, "cached preview must still render when the original is offline"


def test_without_hash_offline_original_returns_none(cache_dir, tmp_path):
    img = tmp_path / "photo.jpg"
    _make_image(img)
    assert thumbnails.media_thumbnail_jpeg(img, "image", 48) is not None

    thumbnails._cache.clear()
    img.unlink()

    # No content_hash → stat-based key can't be computed offline → no cache hit,
    # regeneration fails on the missing file → None (unchanged legacy behaviour).
    assert thumbnails.media_thumbnail_jpeg(img, "image", 48) is None
