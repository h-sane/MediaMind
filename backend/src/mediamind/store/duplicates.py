"""Persistence helpers for duplicate scan results and user resolutions."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StoredMember:
    id: int
    path: str  # relative to library root, forward-slash separated
    size: int
    mtime: float
    kind: str
    width: int
    height: int
    suggested_keep: bool
    resolution: str | None  # None | "keep" | "trash" | "trashed"
    content_hash: str  # stable cross-scan identity, see core.dedupe.DuplicateFile.identity


@dataclass
class StoredGroup:
    id: int
    match: str  # "exact" | "near"
    files: list[StoredMember]


@dataclass
class StoredScan:
    id: str
    scanned_at: float | None
    summary: dict
    groups: list[StoredGroup]


def persist_scan(
    conn: sqlite3.Connection,
    scan_id: str,
    groups: list,  # list[DuplicateGroup] — avoid circular import
    library_root: Path,
    started_at: float,
    finished_at: float,
    params: dict,
    summary: dict,
) -> None:
    """Replace previous dedupe results with this scan (single-active-result model).

    Cascade delete removes old groups and members via the FK relationship.
    """
    old_ids = [
        r["id"]
        for r in conn.execute("SELECT id FROM scans WHERE type = 'dedupe'").fetchall()
    ]
    for old_id in old_ids:
        # Explicit delete; FK cascade handles members via group FK.
        conn.execute("DELETE FROM duplicate_groups WHERE scan_id = ?", (old_id,))
    if old_ids:
        placeholders = ",".join("?" * len(old_ids))
        conn.execute(f"DELETE FROM scans WHERE id IN ({placeholders})", old_ids)

    conn.execute(
        """INSERT INTO scans (id, type, state, params, started_at, finished_at, summary)
           VALUES (?, 'dedupe', 'succeeded', ?, ?, ?, ?)""",
        (scan_id, json.dumps(params), started_at, finished_at, json.dumps(summary)),
    )

    for group in groups:
        cursor = conn.execute(
            "INSERT INTO duplicate_groups (scan_id, match) VALUES (?, ?)",
            (scan_id, group.match),
        )
        group_id = cursor.lastrowid
        for f in group.files:
            rel = Path(f.path).relative_to(library_root)
            rel_str = rel.as_posix()  # always forward-slash for cross-platform consistency
            conn.execute(
                """INSERT INTO duplicate_members
                   (group_id, path, size, mtime, kind, width, height, suggested_keep, content_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (group_id, rel_str, f.size, f.mtime, f.kind, f.width, f.height, int(f.is_best), f.identity),
            )

    conn.commit()


def load_scan(conn: sqlite3.Connection) -> StoredScan | None:
    """Return the most recent dedupe scan with all groups and members, or None."""
    row = conn.execute(
        "SELECT id, started_at, summary FROM scans WHERE type = 'dedupe' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None

    scan_id = row["id"]
    summary = json.loads(row["summary"] or "{}")

    group_rows = conn.execute(
        "SELECT id, match FROM duplicate_groups WHERE scan_id = ? AND ignored_at IS NULL ORDER BY id",
        (scan_id,),
    ).fetchall()

    groups: list[StoredGroup] = []
    for gr in group_rows:
        member_rows = conn.execute(
            """SELECT id, path, size, mtime, kind, width, height, suggested_keep, resolution, content_hash
               FROM duplicate_members WHERE group_id = ? ORDER BY suggested_keep DESC, id""",
            (gr["id"],),
        ).fetchall()
        members = [
            StoredMember(
                id=m["id"],
                path=m["path"],
                size=m["size"] or 0,
                mtime=m["mtime"] or 0.0,
                kind=m["kind"] or "",
                width=m["width"] or 0,
                height=m["height"] or 0,
                suggested_keep=bool(m["suggested_keep"]),
                resolution=m["resolution"],
                content_hash=m["content_hash"] or "",
            )
            for m in member_rows
        ]
        groups.append(StoredGroup(id=gr["id"], match=gr["match"], files=members))

    return StoredScan(id=scan_id, scanned_at=row["started_at"], summary=summary, groups=groups)


def upsert_resolution(conn: sqlite3.Connection, file_id: int, action: str) -> bool:
    """Set resolution for a duplicate_members row. Returns False if row not found."""
    cur = conn.execute(
        "UPDATE duplicate_members SET resolution = ? WHERE id = ?",
        (action, file_id),
    )
    conn.commit()
    return cur.rowcount > 0


def get_trash_set(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """Return (member_id, relative_path) for all members resolved as 'trash'."""
    rows = conn.execute(
        "SELECT id, path FROM duplicate_members WHERE resolution = 'trash'"
    ).fetchall()
    return [(r["id"], r["path"]) for r in rows]


def mark_members_trashed(conn: sqlite3.Connection, member_ids: list[int]) -> None:
    """After a successful trash operation, record the final state."""
    if not member_ids:
        return
    placeholders = ",".join("?" * len(member_ids))
    conn.execute(
        f"UPDATE duplicate_members SET resolution = 'trashed' WHERE id IN ({placeholders})",
        member_ids,
    )
    conn.commit()


def validate_no_empty_groups(conn: sqlite3.Connection) -> list[int]:
    """Return group IDs where every member is marked 'trash' (no keeper remains)."""
    bad: list[int] = []
    for gr in conn.execute("SELECT id FROM duplicate_groups").fetchall():
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM duplicate_members WHERE group_id = ? AND (resolution IS NULL OR resolution != 'trash')",
            (gr["id"],),
        ).fetchone()["c"]
        if count == 0:
            bad.append(gr["id"])
    return bad


def get_dismissed_signatures(conn: sqlite3.Connection) -> set[str]:
    """All group signatures the user has already reviewed and confirmed via
    /duplicates/confirm — a fresh scan filters these out (see
    routes/scans.py's dedupe runner)."""
    rows = conn.execute("SELECT signature FROM dedupe_dismissals").fetchall()
    return {r["signature"] for r in rows}


def add_dismissals(conn: sqlite3.Connection, rows: list[tuple[str, str, int]]) -> None:
    """Record confirmed group signatures. `rows` is (signature, match, file_count)."""
    if not rows:
        return
    now = time.time()
    conn.executemany(
        """INSERT OR IGNORE INTO dedupe_dismissals (signature, match, file_count, dismissed_at)
           VALUES (?, ?, ?, ?)""",
        [(sig, match, count, now) for sig, match, count in rows],
    )
    conn.commit()


def mark_groups_ignored(conn: sqlite3.Connection, group_ids: list[int]) -> None:
    """Hide confirmed groups from the current scan's live view without
    deleting them — keeps the historical record of what the scan found."""
    if not group_ids:
        return
    now = time.time()
    placeholders = ",".join("?" * len(group_ids))
    conn.execute(
        f"UPDATE duplicate_groups SET ignored_at = ? WHERE id IN ({placeholders})",
        [now, *group_ids],
    )
    conn.commit()


def clear_dismissals(conn: sqlite3.Connection) -> int:
    """Delete every recorded dismissal signature — the inverse of
    add_dismissals(). Used by "Reset configuration" so a user who confirmed
    the wrong groups (or just wants a clean slate) can undo every prior
    "Save configuration" for this library at once."""
    cur = conn.execute("DELETE FROM dedupe_dismissals")
    conn.commit()
    return cur.rowcount


def unignore_all_groups(conn: sqlite3.Connection) -> int:
    """Un-hide every group hidden by a prior confirm, without waiting for a
    rescan. Pairs with clear_dismissals() so "Reset configuration" takes
    effect immediately in the current review list."""
    cur = conn.execute("UPDATE duplicate_groups SET ignored_at = NULL WHERE ignored_at IS NOT NULL")
    conn.commit()
    return cur.rowcount
