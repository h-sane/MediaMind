"""Tier-3 "system" auto-scan: a lightweight tally of unregistered folders that
have new media, so the Suggestions tab can prompt "register this folder as a
library?" without ever running the full hash/dedupe/face-match pipeline on
folders the user hasn't opted into. Not a content index — no per-file rows,
no hashing, just a per-folder counter. Fully rebuildable/disposable: safe to
delete this file at any time, it just resets the tally to zero.
"""

from __future__ import annotations

import ctypes
import sqlite3
import sys
import time
from pathlib import Path

_DRIVE_FIXED = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS folder_tally (
    folder TEXT PRIMARY KEY,
    media_count INTEGER NOT NULL DEFAULT 0,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    dismissed INTEGER NOT NULL DEFAULT 0,
    registered INTEGER NOT NULL DEFAULT 0
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def record(conn: sqlite3.Connection, folder: str) -> None:
    now = time.time()
    conn.execute(
        """
        INSERT INTO folder_tally (folder, media_count, first_seen, last_seen)
        VALUES (?, 1, ?, ?)
        ON CONFLICT(folder) DO UPDATE SET
            media_count = media_count + 1,
            last_seen = excluded.last_seen
        """,
        (folder, now, now),
    )
    conn.commit()


def list_suggestions(conn: sqlite3.Connection, threshold: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT folder, media_count, first_seen, last_seen FROM folder_tally "
        "WHERE media_count >= ? AND dismissed = 0 AND registered = 0",
        (threshold,),
    ).fetchall()
    return [
        {"folder": r["folder"], "media_count": r["media_count"], "first_seen": r["first_seen"], "last_seen": r["last_seen"]}
        for r in rows
        if Path(r["folder"]).is_dir()  # filesystem is the source of truth — never suggest a folder that's gone
    ]


# Well-known "inbox" folders where new media typically lands. Suggested
# proactively (ADR-0009 effortless setup) — the moment one exists and holds
# media, without waiting for the whole-drive tally to reach threshold. Home-
# relative so they resolve per-user and cross-platform; existence and content
# are checked at query time (the filesystem is the source of truth).
_INBOX_SUBPATHS: tuple[tuple[str, ...], ...] = (
    ("Downloads",),
    ("Downloads", "Telegram Desktop"),
    ("Pictures",),
    ("Videos",),
)


def known_inbox_folders() -> list[Path]:
    home = Path.home()
    return [home.joinpath(*parts) for parts in _INBOX_SUBPATHS]


def _shallow_media_count(folder: Path, cap: int = 50) -> int:
    """Count media files directly in `folder` (non-recursive), capped — enough
    to show "N photos/videos" without walking a deep Downloads tree."""
    from mediamind.core.scanner import MEDIA_KINDS, kind_of

    n = 0
    try:
        for entry in folder.iterdir():
            if entry.is_file() and kind_of(entry) in MEDIA_KINDS:
                n += 1
                if n >= cap:
                    break
    except OSError:
        return 0
    return n


def list_inbox_suggestions(conn: sqlite3.Connection) -> list[dict]:
    """Known inbox folders worth suggesting: they exist, hold media, and the
    user hasn't already dismissed or registered them. Dismiss/registered state
    is reused from `folder_tally` so a dismissed inbox stays gone."""
    state = {
        r["folder"]: r
        for r in conn.execute("SELECT folder, dismissed, registered FROM folder_tally").fetchall()
    }
    now = time.time()
    out: list[dict] = []
    for folder in known_inbox_folders():
        key = str(folder)
        st = state.get(key)
        if st is not None and (st["dismissed"] or st["registered"]):
            continue
        if not folder.is_dir():
            continue
        count = _shallow_media_count(folder)
        if count == 0:
            continue
        out.append({"folder": key, "media_count": count, "first_seen": now, "last_seen": now})
    return out


def _set_flag(conn: sqlite3.Connection, folder: str, column: str) -> None:
    # Upsert, not a bare UPDATE: a proactively-suggested inbox (ADR-0009) may
    # have no tally row yet, and its dismissed/registered state must still
    # persist so it stops being suggested.
    now = time.time()
    conn.execute(
        f"INSERT INTO folder_tally (folder, media_count, first_seen, last_seen, {column}) "
        f"VALUES (?, 0, ?, ?, 1) ON CONFLICT(folder) DO UPDATE SET {column} = 1",
        (folder, now, now),
    )
    conn.commit()


def mark_registered(conn: sqlite3.Connection, folder: str) -> None:
    _set_flag(conn, folder, "registered")


def mark_dismissed(conn: sqlite3.Connection, folder: str) -> None:
    _set_flag(conn, folder, "dismissed")


def fixed_drive_roots() -> list[str]:
    """Local fixed drives only (`DRIVE_FIXED`) — excludes removable (USB),
    network/mapped, CD-ROM, and unknown drive types, so Tier-3 never crawls a
    network share or a thumb drive. Windows-only for now."""
    if sys.platform != "win32":
        return []
    get_drive_type = ctypes.windll.kernel32.GetDriveTypeW  # type: ignore[attr-defined]
    get_drive_type.argtypes = [ctypes.c_wchar_p]
    get_drive_type.restype = ctypes.c_uint
    roots = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        root = f"{letter}:\\"
        try:
            if get_drive_type(root) == _DRIVE_FIXED:
                roots.append(root)
        except OSError:
            continue
    return roots
