"""Lazy, self-invalidating cache of "does this folder contain media anywhere
below it" for the Explorer shell's whole-filesystem browsing.

Folders can be arbitrarily deep, so answering this correctly at listing time
would mean a full recursive walk on every request. Instead: a directory
listing checks the cache and returns cached answers instantly; anything
missing/stale is reported as "unknown" and a background walk is kicked off
to fill it in, so the *next* look is fast. The walk exits early on the first
media file found rather than enumerating a whole subtree.

Cache invalidation is two-pronged: a directory's own mtime changes when a
file is added/removed directly inside it (a fast, precise signal), but a
change several levels deeper does not bump an ancestor's mtime — a plain
change deep in the tree could leave a stale `False` cached above it. A TTL
on top of the mtime check bounds how long that staleness can last.

The walk also tracks whether the subtree contains *any* file at all (media
or not), not just media. A folder with zero files anywhere below it — a
freshly created folder, or one containing only nested empty folders — is
structure the user put there on purpose, not junk, so the Explorer listing
(`api/routes/fs.py`) keeps it visible even though it has no media. Only a
subtree that is confirmed to contain files but none of them media (e.g. a
folder full of `.txt` files) is treated as junk and omitted.
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
from mediamind.core.scanner import is_noise_dir

# Re-checked even if the directory's own mtime hasn't changed, to catch
# additions/removals several levels deeper in the subtree.
CACHE_TTL_SECONDS = 15 * 60

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dir_media (
    path TEXT PRIMARY KEY,
    has_media INTEGER NOT NULL,
    has_any_file INTEGER NOT NULL DEFAULT 1,
    dir_mtime_ns INTEGER NOT NULL,
    checked_at REAL NOT NULL
);
"""


class MediaStatus(NamedTuple):
    has_media: bool
    # False = the subtree contains no files at all below it (pure folder
    # structure only) — see module docstring for why this is tracked
    # separately from has_media.
    has_any_file: bool


def _walk_media_status(root: Path) -> MediaStatus:
    """Iterative DFS, early-exits the instant a media file is found.
    Otherwise walks the whole (non-noise) subtree to also determine whether
    it contains any file at all, media or not."""
    found_any_file = False
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
                    found_any_file = True
                    if explorer_kind_of(Path(entry.path)) in EXPLORER_KINDS:
                        return MediaStatus(has_media=True, has_any_file=True)
            except OSError:
                continue
    return MediaStatus(has_media=False, has_any_file=found_any_file)


class MediaIndex:
    """App-wide, thread-safe cache + background walker. One instance lives
    on `app.state.media_index` for the process lifetime."""

    def __init__(self, db_path: Path, max_workers: int = 4):
        self._db_path = db_path
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="media-index"
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
            # ALTER TABLE is not idempotent — guard the column addition for
            # DBs created before has_any_file existed.
            try:
                conn.execute(
                    "ALTER TABLE dir_media ADD COLUMN has_any_file INTEGER NOT NULL DEFAULT 1"
                )
            except sqlite3.OperationalError:
                pass  # column already exists
            conn.commit()
        finally:
            conn.close()

    def check(self, path: Path) -> bool | None:
        """Cached has-media-below state for `path`, or None if unknown/stale
        — in which case a background walk is scheduled (deduped: a second
        call for the same path while one is already running is a no-op)."""
        status = self.check_full(path)
        return None if status is None else status.has_media

    def check_full(self, path: Path) -> MediaStatus | None:
        """Like `check`, but also reports whether the subtree contains any
        file at all — see module docstring for why the Explorer listing
        needs this in addition to has_media."""
        cached = self._lookup(path)
        if cached is not None:
            return cached
        key = str(path)
        with self._lock:
            if key not in self._inflight:
                self._inflight.add(key)
                self._executor.submit(self._walk_and_store, path)
        return None

    def _lookup(self, path: Path) -> MediaStatus | None:
        try:
            current_mtime_ns = path.stat().st_mtime_ns
        except OSError:
            return None
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT has_media, has_any_file, dir_mtime_ns, checked_at FROM dir_media WHERE path = ?",
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
        return MediaStatus(has_media=bool(row["has_media"]), has_any_file=bool(row["has_any_file"]))

    def _walk_and_store(self, path: Path) -> None:
        try:
            status = _walk_media_status(path)
            try:
                mtime_ns = path.stat().st_mtime_ns
            except OSError:
                mtime_ns = 0
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO dir_media (path, has_media, has_any_file, dir_mtime_ns, checked_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        has_media = excluded.has_media,
                        has_any_file = excluded.has_any_file,
                        dir_mtime_ns = excluded.dir_mtime_ns,
                        checked_at = excluded.checked_at
                    """,
                    (str(path), int(status.has_media), int(status.has_any_file), mtime_ns, time.time()),
                )
                conn.commit()
            finally:
                conn.close()
        finally:
            with self._lock:
                self._inflight.discard(str(path))
