"""Unit tests for the on-disk thumbnail cache's size-cap LRU eviction."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from mediamind.core import thumbnails


@pytest.fixture
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "thumb_cache"
    d.mkdir()
    monkeypatch.setattr(thumbnails, "thumbnail_cache_dir", lambda: d)
    return d


def _write_fake_tile(cache_dir: Path, name: str, nbytes: int, age_seconds: float) -> Path:
    shard = cache_dir / name[:2]
    shard.mkdir(parents=True, exist_ok=True)
    p = shard / f"{name}.jpg"
    p.write_bytes(b"x" * nbytes)
    mtime = time.time() - age_seconds
    os.utime(p, (mtime, mtime))
    return p


def test_no_eviction_under_cap(cache_dir):
    _write_fake_tile(cache_dir, "aa111", 100, age_seconds=1000)
    thumbnails._evict_disk_cache_if_over_cap()
    assert (cache_dir / "aa" / "aa111.jpg").exists()


def test_evicts_oldest_first_until_under_target(cache_dir, monkeypatch):
    monkeypatch.setattr(thumbnails, "_DISK_CACHE_MAX_BYTES", 250)
    monkeypatch.setattr(thumbnails, "_DISK_CACHE_EVICT_TARGET", 200)

    oldest = _write_fake_tile(cache_dir, "aa001", 100, age_seconds=3000)
    middle = _write_fake_tile(cache_dir, "bb002", 100, age_seconds=2000)
    newest = _write_fake_tile(cache_dir, "cc003", 100, age_seconds=1000)
    assert 100 + 100 + 100 > 250  # over cap

    thumbnails._evict_disk_cache_if_over_cap()

    assert not oldest.exists(), "oldest-mtime entry must be evicted first"
    assert middle.exists()
    assert newest.exists()


def test_disk_get_touches_mtime_to_protect_recently_read_entries(cache_dir, monkeypatch, tmp_path):
    monkeypatch.setattr(thumbnails, "_DISK_CACHE_MAX_BYTES", 150)
    monkeypatch.setattr(thumbnails, "_DISK_CACHE_EVICT_TARGET", 100)

    old_but_read = _write_fake_tile(cache_dir, "aa111", 100, age_seconds=5000)
    never_read = _write_fake_tile(cache_dir, "bb222", 100, age_seconds=10)

    # Reading the old entry through the real key-based path bumps its mtime,
    # so eviction should now prefer the never-read (but nominally newer) file.
    key = ("some/path.jpg", "photo", 256, 1, 2)
    monkeypatch.setattr(thumbnails, "_disk_path", lambda k: old_but_read)
    assert thumbnails._disk_get(key) == b"x" * 100

    thumbnails._evict_disk_cache_if_over_cap()

    assert old_but_read.exists(), "recently-read entry must survive eviction"
    assert not never_read.exists()
