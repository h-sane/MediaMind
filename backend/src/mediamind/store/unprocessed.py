"""Files a scan could not process, and the hand labels the user gives them.

A file that times out or cannot be decoded is never dropped silently: it is kept
here with the reason, shown to the user in the folder view, and can be tagged to a
person by hand. Everything keys on the library-relative path because a file that
never finished hashing has no `files` row.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Unprocessed:
    path: str
    kind: str
    size: int
    reason: str
    message: str
    attempts: int
    failed_at: float
    person_ids: list[int]


def replace_unprocessed(
    conn: sqlite3.Connection,
    failures: list[tuple[str, str, int, str, str]],
    scan_id: str,
) -> None:
    """Make the table match this scan's outcome. `failures` is
    (rel_path, kind, size, reason, message). A file that failed before keeps
    counting its attempts; a file that succeeded this time disappears from the list
    (its hand labels stay in `manual_tags`)."""
    previous = {r["path"]: r["attempts"] for r in conn.execute("SELECT path, attempts FROM unprocessed_files")}
    now = time.time()
    conn.execute("DELETE FROM unprocessed_files")
    conn.executemany(
        "INSERT INTO unprocessed_files (path, kind, size, reason, message, attempts, last_scan_id, failed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(p, k, sz, reason, msg, previous.get(p, 0) + 1, scan_id, now) for p, k, sz, reason, msg in failures],
    )
    conn.commit()


def list_unprocessed(conn: sqlite3.Connection, under: str | None = None) -> list[Unprocessed]:
    """Unprocessed files, optionally only those inside a library-relative folder."""
    sql = "SELECT path, kind, size, reason, message, attempts, failed_at FROM unprocessed_files"
    args: tuple = ()
    if under:
        sql += " WHERE path LIKE ?"
        args = (under.strip("/") + "/%",)
    rows = conn.execute(sql + " ORDER BY path", args).fetchall()
    tags: dict[str, list[int]] = {}
    for t in conn.execute("SELECT path, person_id FROM manual_tags ORDER BY tagged_at"):
        tags.setdefault(t["path"], []).append(t["person_id"])
    return [
        Unprocessed(r["path"], r["kind"], r["size"], r["reason"], r["message"], r["attempts"], r["failed_at"], tags.get(r["path"], []))
        for r in rows
    ]


def tag_file(conn: sqlite3.Connection, path: str, person_id: int) -> bool:
    """Label a file with a person by hand. False if the person does not exist."""
    if conn.execute("SELECT 1 FROM persons WHERE id = ?", (person_id,)).fetchone() is None:
        return False
    conn.execute(
        "INSERT OR REPLACE INTO manual_tags (path, person_id, tagged_at) VALUES (?, ?, ?)",
        (path, person_id, time.time()),
    )
    conn.commit()
    return True


def untag_file(conn: sqlite3.Connection, path: str, person_id: int) -> None:
    conn.execute("DELETE FROM manual_tags WHERE path = ? AND person_id = ?", (path, person_id))
    conn.commit()


def manual_tagged_paths(conn: sqlite3.Connection, person_id: int) -> list[tuple[str, str, int | None]]:
    """(path, kind, file_id) for every file hand-labelled with this person."""
    return [
        (r["path"], r["kind"] or "image", r["file_id"])
        for r in conn.execute(
            """
            SELECT t.path AS path,
                   COALESCE(f.kind, u.kind) AS kind,
                   f.id AS file_id
            FROM manual_tags t
            LEFT JOIN files f ON f.path = t.path
            LEFT JOIN unprocessed_files u ON u.path = t.path
            WHERE t.person_id = ?
            ORDER BY t.path
            """,
            (person_id,),
        )
    ]
