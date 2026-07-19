"""Durable per-face person assignments — survive the wholesale faces-row
rebuild every rescan does, so a confirmed face can never be un-named by
re-clustering (see `persist_face_scan` in store/persons.py).

Keyed by content_hash + provider_id + bbox (matched by IOU, not exact
equality, since re-detection rarely reproduces byte-identical coordinates)
— same instinct as rejected_face_regions/rejected_person_files.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from mediamind.store.rejected_faces import _iou

BBox = tuple[float, float, float, float]

# Stricter than IOU_REJECT_THRESHOLD (0.3) — a wrong "same face" match here
# would misattach a different face's identity, not just miss a rejection.
ASSIGNMENT_IOU_THRESHOLD = 0.5


@dataclass(frozen=True)
class Assignment:
    id: int
    person_id: int
    bbox: BBox
    source: str  # 'cluster' | 'user'


def assignments_for(conn: sqlite3.Connection, content_hash: str, provider_id: str) -> list[Assignment]:
    """All durable assignments recorded for one file's content, for one provider."""
    rows = conn.execute(
        """
        SELECT id, person_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, source
        FROM face_assignments WHERE content_hash = ? AND provider_id = ?
        """,
        (content_hash, provider_id),
    ).fetchall()
    return [
        Assignment(
            id=r["id"],
            person_id=r["person_id"],
            bbox=(r["bbox_x1"], r["bbox_y1"], r["bbox_x2"], r["bbox_y2"]),
            source=r["source"],
        )
        for r in rows
    ]


def find_assignment(assignments: list[Assignment], bbox: BBox) -> Assignment | None:
    """Best IOU match for this bbox among a file's existing assignments, if any clears the bar."""
    best: Assignment | None = None
    best_iou = ASSIGNMENT_IOU_THRESHOLD
    for a in assignments:
        score = _iou(a.bbox, bbox)
        if score >= best_iou:
            best_iou = score
            best = a
    return best


def record_assignment(
    conn: sqlite3.Connection,
    content_hash: str,
    provider_id: str,
    bbox: BBox,
    person_id: int,
    source: str,
    existing: list[Assignment] | None = None,
) -> None:
    """Durably record that this face region belongs to this person.

    Replaces any prior assignment for the same face region (by IOU), so a
    face can be reassigned (e.g. a later merge or "not this person" action)
    without leaving stale duplicate rows behind.
    """
    existing = existing if existing is not None else assignments_for(conn, content_hash, provider_id)
    prior = find_assignment(existing, bbox)
    if prior is not None:
        conn.execute("DELETE FROM face_assignments WHERE id = ?", (prior.id,))
    conn.execute(
        """
        INSERT INTO face_assignments
          (content_hash, provider_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, person_id, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (content_hash, provider_id, *bbox, person_id, source, time.time()),
    )


def clear_for_person(conn: sqlite3.Connection, content_hash: str, provider_id: str, person_id: int) -> None:
    """Undo a durable assignment to this person for this file's content —
    used when a user explicitly says a file isn't this person after all
    (see rejected_persons.reject_person_files)."""
    conn.execute(
        "DELETE FROM face_assignments WHERE content_hash = ? AND provider_id = ? AND person_id = ?",
        (content_hash, provider_id, person_id),
    )


def repoint_person(conn: sqlite3.Connection, source_person_id: int, target_person_id: int) -> None:
    """Move a person's assignments to another person (used by merge_persons,
    called before the source person row is deleted — its ON DELETE CASCADE
    would otherwise silently drop these along with it)."""
    conn.execute(
        "UPDATE face_assignments SET person_id = ? WHERE person_id = ?",
        (target_person_id, source_person_id),
    )


def person_is_referenced(conn: sqlite3.Connection, person_id: int) -> bool:
    """True if a folder binding, a route choice, or an explicit user action
    depends on this person surviving. persist_face_scan must never delete a
    person these point to, even if it's unnamed and no cluster matched it
    this particular rescan.

    Deliberately excludes plain `source='cluster'` assignments: those are
    automatic bookkeeping, not something a human did — an unnamed person
    whose photos simply vanish from later scans should still be garbage
    collected, or every stray auto-detected face would pin a "Person_NNN"
    ghost in the database forever.
    """
    if conn.execute(
        "SELECT 1 FROM face_assignments WHERE person_id = ? AND source = 'user' LIMIT 1", (person_id,)
    ).fetchone():
        return True
    for table in ("folder_binding_members", "route_choices"):
        if conn.execute(f"SELECT 1 FROM {table} WHERE person_id = ? LIMIT 1", (person_id,)).fetchone():
            return True
    return False
