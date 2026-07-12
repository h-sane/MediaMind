"""Lazy, self-invalidating cache of recursive item-count + total-bytes for a
folder — the aggregate facts a multi-select "Properties" panel needs (Phase G)
without recomputing a full recursive walk on every open.

Architecturally identical to `media_index.py`'s has-media cache (same lazy /
background-walk / mtime+TTL invalidation strategy) but answers a different
question, so it's a separate cache rather than overloading that one's schema.
Counts and sums only media files (images/gifs/videos/audio) — this project's
browse surface is media-only, so a folder's "size" for a Properties panel
means the size of the media it actually shows, not every file in the tree.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple

from mediamind.core.explorer_media import EXPLORER_KINDS, explorer_kind_of
from mediamind.core.media_index import is_noise_dir

CACHE_TTL_SECONDS = 15 * 60

_SCHEMA = """
CREATE TABLE IF NOT EXISTS folder_stats (
    path TEXT PRIMARY KEY,
    item_count INTEGER NOT NULL,
    total_bytes INTEGER NOT NULL,
    dir_mtime_ns INTEGER NOT NULL,
    checked_at REAL NOT NULL
);
"""


class FolderStats(NamedTuple):
    item_count: int
    total_bytes: int


def _walk_stats(root: Path) -> FolderStats:
    """Iterative DFS summing every media file's size below `root`. Mirrors
    `media_index._walk_media_status`'s noise-dir skipping and per-entry
    OSError resilience, but never early-exits — it needs the full count."""
    item_count = 0
    total_bytes = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                entries = list(it)
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if not is_noise_dir(entry.name):
                        stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    if explorer_kind_of(Path(entry.path)) in EXPLORER_KINDS:
                        item_count += 1
                        total_bytes += entry.stat().st_size
            except OSError:
                continue
    return FolderStats(item_count=item_count, total_bytes=total_bytes)


class FolderStatsIndex:
    """App-wide, thread-safe cache + background walker for recursive folder
    aggregates. One instance lives on `app.state.folder_stats` for the
    process lifetime — same lifecycle as `MediaIndex`."""

    def __init__(self, db_path: Path, max_workers: int = 4):
        self._db_path = db_path
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="folder-stats"
        )
        self._inflight: set[str] = set()
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def check_full(self, path: Path) -> FolderStats | None:
        """Cached recursive stats for `path`, or None if unknown/stale — in
        which case a background walk is scheduled (deduped: a second call for
        the same path while one is already running is a no-op)."""
        cached = self._lookup(path)
        if cached is not None:
            return cached
        key = str(path)
        with self._lock:
            if key not in self._inflight:
                self._inflight.add(key)
                self._executor.submit(self._walk_and_store, path)
        return None

    def _lookup(self, path: Path) -> FolderStats | None:
        try:
            current_mtime_ns = path.stat().st_mtime_ns
        except OSError:
            return None
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT item_count, total_bytes, dir_mtime_ns, checked_at FROM folder_stats WHERE path = ?",
                (str(path),),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        if row["dir_mtime_ns"] != current_mtime_ns:
            return None
        if time.time() - row["checked_at"] > CACHE_TTL_SECONDS:
            return None
        return FolderStats(item_count=row["item_count"], total_bytes=row["total_bytes"])

    def _walk_and_store(self, path: Path) -> None:
        try:
            stats = _walk_stats(path)
            try:
                mtime_ns = path.stat().st_mtime_ns
            except OSError:
                mtime_ns = 0
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO folder_stats (path, item_count, total_bytes, dir_mtime_ns, checked_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        item_count = excluded.item_count,
                        total_bytes = excluded.total_bytes,
                        dir_mtime_ns = excluded.dir_mtime_ns,
                        checked_at = excluded.checked_at
                    """,
                    (str(path), stats.item_count, stats.total_bytes, mtime_ns, time.time()),
                )
                conn.commit()
            finally:
                conn.close()
        finally:
            with self._lock:
                self._inflight.discard(str(path))
