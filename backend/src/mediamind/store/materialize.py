"""Materialize a not-yet-foldered person into a brand-new sibling folder.

Phase B's binding suggestions match a person to an EXISTING folder. This is
the opposite case: a person discovered purely from clustering, with no
folder of their own yet. The user reviews all of that person's photos
(excluding some, redirecting others elsewhere), picks a name, and only then
does a folder get created — nothing moves until that explicit commit.
Reuses folder_bindings/folder_binding_members so the result is immediately
"respected" like any other bound folder, exactly like `bindings.accept_suggestion`
does — just without a source `binding_suggestions` row, since there was no
existing folder to detect against.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from mediamind.core.organize_plan import safe_folder_name


class AlreadyBoundError(Exception):
    """This person already has a folder binding — materialize doesn't apply."""


@dataclass(frozen=True)
class MaterializeCandidate:
    file_id: int
    source_rel: str
    kind: str


def is_bound(conn: sqlite3.Connection, person_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM folder_binding_members WHERE person_id = ?", (person_id,)
    ).fetchone()
    return row is not None


def list_candidates(
    conn: sqlite3.Connection, provider_id: str, person_id: int
) -> list[MaterializeCandidate]:
    """Every current photo of this person, library-wide — read-only."""
    rows = conn.execute(
        """
        SELECT DISTINCT fi.id AS file_id, fi.path AS path, fi.kind AS kind
        FROM files fi
        JOIN faces f ON f.file_id = fi.id
        WHERE f.provider_id = ? AND f.person_id = ?
        ORDER BY fi.path
        """,
        (provider_id, person_id),
    ).fetchall()
    return [
        MaterializeCandidate(file_id=r["file_id"], source_rel=r["path"], kind=r["kind"])
        for r in rows
    ]


def materialize_person_folder(conn: sqlite3.Connection, person_id: int, folder_name: str) -> str:
    """Create the binding and apply the name. Call AFTER the confirmed photos
    have already been moved on disk (mirrors accept_suggestion's binding step).
    Returns the sanitized folder_rel that was bound.
    """
    if is_bound(conn, person_id):
        raise AlreadyBoundError(f"Person {person_id} already has a folder")

    row = conn.execute("SELECT provider_id FROM persons WHERE id = ?", (person_id,)).fetchone()
    if row is None:
        raise ValueError(f"Person {person_id} not found")

    folder_rel = safe_folder_name(folder_name)
    now = time.time()
    cur = conn.execute(
        "INSERT INTO folder_bindings (folder_rel, kind, provider_id, created_at) VALUES (?, 'person', ?, ?)",
        (folder_rel, row["provider_id"], now),
    )
    binding_id = cur.lastrowid
    try:
        conn.execute(
            "INSERT INTO folder_binding_members (binding_id, person_id) VALUES (?, ?)",
            (binding_id, person_id),
        )
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise AlreadyBoundError(f"Person {person_id} already has a folder") from exc

    conn.execute("UPDATE persons SET name = ? WHERE id = ?", (folder_name.strip(), person_id))
    conn.commit()
    return folder_rel
