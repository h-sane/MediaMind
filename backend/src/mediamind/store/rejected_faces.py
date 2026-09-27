"""Manual "not a face" rejection — a safety valve for detector false positives
(backgrounds, objects, patterns) that cluster together into a fake "person".

Rejections are keyed by content_hash + provider_id + bbox rather than a
faces.id, because `persist_face_scan` deletes and recreates every faces row
on each rescan — a rejection has to survive that to be worth anything.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

BBox = tuple[float, float, float, float]

IOU_REJECT_THRESHOLD = 0.3


@dataclass(frozen=True)
class RejectedFaceResult:
    file_id: int
    person_id: int | None
    face_ids: tuple[int, ...]  # the face asked for, then the same face in the file's other frames


def _iou(a: BBox, b: BBox) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def regions_for(conn: sqlite3.Connection, content_hash: str, provider_id: str) -> list[BBox]:
    """All rejected regions for one file's content, for one provider."""
    rows = conn.execute(
        """
        SELECT bbox_x1, bbox_y1, bbox_x2, bbox_y2
        FROM rejected_face_regions WHERE content_hash = ? AND provider_id = ?
        """,
        (content_hash, provider_id),
    ).fetchall()
    return [(r["bbox_x1"], r["bbox_y1"], r["bbox_x2"], r["bbox_y2"]) for r in rows]


def is_rejected(regions: list[BBox], bbox: BBox) -> bool:
    return any(_iou(r, bbox) >= IOU_REJECT_THRESHOLD for r in regions)


_FACE_ROW = """
    SELECT f.id, f.file_id, f.person_id, f.provider_id, f.embedding,
           f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, fi.content_hash
    FROM faces f JOIN files fi ON fi.id = f.file_id
"""


def _same_face_in_file(conn: sqlite3.Connection, row: sqlite3.Row) -> list[sqlite3.Row]:
    """The same individual in the file's other frames (a video samples several), except faces the
    user put on a person themselves: ignoring one frame of a face ignores it in the whole video."""
    import numpy as np

    from mediamind.store import face_assignments
    from mediamind.store.pending_repeats import SAME_FACE_SIM, _unit  # imports this module

    others = conn.execute(_FACE_ROW + " WHERE f.file_id = ? AND f.provider_id = ? AND f.id != ?",
                          (row["file_id"], row["provider_id"], row["id"])).fetchall()
    if not others or row["embedding"] is None:
        return []
    user = [a for a in face_assignments.assignments_for(conn, row["content_hash"], row["provider_id"])
            if a.source == "user"] if row["content_hash"] else []
    v = _unit(row["embedding"])
    out = []
    for o in others:
        if o["embedding"] is None or float(v @ _unit(o["embedding"])) < SAME_FACE_SIM:
            continue
        m = face_assignments.find_assignment(user, (o["bbox_x1"], o["bbox_y1"], o["bbox_x2"], o["bbox_y2"]))
        if m is not None and m.person_id == o["person_id"]:
            continue
        out.append(o)
    return out


def _reject_one(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    content_hash = row["content_hash"]
    if content_hash:
        # Ignoring a face that review asked about also answers that question for the whole
        # file: the next frame of the same video is not asked for the same person.
        from mediamind.store import rejected_matches  # imports this module

        bbox = (row["bbox_x1"], row["bbox_y1"], row["bbox_x2"], row["bbox_y2"])
        for p in conn.execute(
            "SELECT DISTINCT person_id FROM pending_matches WHERE face_id = ? AND decision IS NULL", (row["id"],)
        ).fetchall():
            rejected_matches.record(conn, content_hash, row["provider_id"], bbox, p["person_id"])
        conn.execute(
            """
            INSERT INTO rejected_face_regions
              (content_hash, provider_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (content_hash, row["provider_id"], *bbox, time.time()),
        )
    conn.execute("DELETE FROM faces WHERE id = ?", (row["id"],))


def reject_face(conn: sqlite3.Connection, face_id: int) -> RejectedFaceResult | None:
    """Record this face's region as "not a face" and remove it immediately, together with the
    same face in the file's other frames.

    Returns the affected file_id/person_id (for cache invalidation upstream) and every removed
    face id, or None if the face doesn't exist.
    """
    row = conn.execute(_FACE_ROW + " WHERE f.id = ?", (face_id,)).fetchone()
    if row is None:
        return None
    rows = [row, *_same_face_in_file(conn, row)]
    for r in rows:
        _reject_one(conn, r)
    conn.commit()
    return RejectedFaceResult(file_id=row["file_id"], person_id=row["person_id"],
                              face_ids=tuple(r["id"] for r in rows))
