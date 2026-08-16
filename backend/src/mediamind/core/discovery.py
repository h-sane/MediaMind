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


def mark_registered(conn: sqlite3.Connection, folder: str) -> None:
    conn.execute("UPDATE folder_tally SET registered = 1 WHERE folder = ?", (folder,))
    conn.commit()


def mark_dismissed(conn: sqlite3.Connection, folder: str) -> None:
    conn.execute("UPDATE folder_tally SET dismissed = 1 WHERE folder = ?", (folder,))
    conn.commit()


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
