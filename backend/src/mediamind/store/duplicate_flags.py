"""Incremental duplicate-flag persistence (schema v10, Performance & Ingest
V4 Phase 3) — advisory notices raised by `core.ingest`'s per-file dedupe
check (exact content-hash / near phash match against an existing files row),
surfaced without running the full Dedupe tool scan.

Flags are advisory only: nothing is trashed here. Resolution happens through
the existing manifest-audited dedupe-execute path once a user opens the
Dedupe tool from a flag's deep link.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DuplicateFlag:
    id: int
    path: str
    match_path: str
    match_type: str  # "exact" | "near"
    content_hash: str | None
    flagged_at: float


def flag_duplicate(
    conn: sqlite3.Connection,
    path: str,
    match_path: str,
    match_type: str,
    content_hash: str | None,
) -> None:
    """Record `path` as a duplicate of `match_path`. Idempotent — the unique
    index on (path, match_path) makes a repeat flag (e.g. the same unchanged
    file getting re-ingested) a no-op rather than a duplicate row."""
    conn.execute(
        """
        INSERT OR IGNORE INTO duplicate_flags (path, match_path, match_type, content_hash, flagged_at, dismissed)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (path, match_path, match_type, content_hash, time.time()),
    )
    conn.commit()


def list_flags(
    conn: sqlite3.Connection, library_root: Path, include_dismissed: bool = False
) -> list[DuplicateFlag]:
    """Live-checked list: a flag whose path or match_path no longer exists on
    disk (hand-deleted, moved outside the app) is dropped rather than shown —
    the filesystem is the source of truth, same doctrine every other
    live-checked listing in this codebase follows."""
    query = "SELECT id, path, match_path, match_type, content_hash, flagged_at FROM duplicate_flags"
    if not include_dismissed:
        query += " WHERE dismissed = 0"
    query += " ORDER BY flagged_at DESC"

    out: list[DuplicateFlag] = []
    for r in conn.execute(query):
        if not (library_root / r["path"]).is_file():
            continue
        if not (library_root / r["match_path"]).is_file():
            continue
        out.append(
            DuplicateFlag(
                id=r["id"],
                path=r["path"],
                match_path=r["match_path"],
                match_type=r["match_type"],
                content_hash=r["content_hash"],
                flagged_at=r["flagged_at"],
            )
        )
    return out


def dismiss_flag(conn: sqlite3.Connection, flag_id: int) -> bool:
    cur = conn.execute("UPDATE duplicate_flags SET dismissed = 1 WHERE id = ?", (flag_id,))
    conn.commit()
    return cur.rowcount > 0
