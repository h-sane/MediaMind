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


def reject_face(conn: sqlite3.Connection, face_id: int) -> RejectedFaceResult | None:
    """Record this face's region as "not a face" and remove it immediately.

    Returns the affected file_id/person_id (for cache invalidation upstream),
    or None if the face doesn't exist.
    """
    row = conn.execute(
        """
        SELECT f.file_id, f.person_id, f.provider_id,
               f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, fi.content_hash
        FROM faces f JOIN files fi ON fi.id = f.file_id
        WHERE f.id = ?
        """,
        (face_id,),
    ).fetchone()
    if row is None:
        return None

    content_hash = row["content_hash"]
    if content_hash:
        conn.execute(
            """
            INSERT INTO rejected_face_regions
              (content_hash, provider_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                content_hash, row["provider_id"],
                row["bbox_x1"], row["bbox_y1"], row["bbox_x2"], row["bbox_y2"],
                time.time(),
            ),
        )

    conn.execute("DELETE FROM faces WHERE id = ?", (face_id,))
    conn.commit()
    return RejectedFaceResult(file_id=row["file_id"], person_id=row["person_id"])
