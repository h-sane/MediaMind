"""Durable "No" answers from review: this face (in this file's content) is not this person.

Keyed by content hash + provider + bbox, matched by IoU like face_assignments, because a
rescan recreates every faces row and a decision stored against a faces.id is lost with it.
"""

from __future__ import annotations

import sqlite3
import time

from mediamind.store.face_assignments import ASSIGNMENT_IOU_THRESHOLD, BBox
from mediamind.store.rejected_faces import _iou


def record(conn: sqlite3.Connection, content_hash: str, provider_id: str, bbox: BBox, person_id: int) -> None:
    conn.execute(
        """INSERT INTO rejected_matches
             (content_hash, provider_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, person_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (content_hash, provider_id, *bbox, person_id, time.time()),
    )


def load(conn: sqlite3.Connection, provider_id: str) -> dict[str, list[tuple[BBox, int]]]:
    """Every durable No for a provider, by content hash: [(bbox, person_id)]."""
    out: dict[str, list[tuple[BBox, int]]] = {}
    for r in conn.execute(
        "SELECT content_hash, bbox_x1, bbox_y1, bbox_x2, bbox_y2, person_id FROM rejected_matches WHERE provider_id = ?",
        (provider_id,),
    ):
        out.setdefault(r["content_hash"], []).append(((r["bbox_x1"], r["bbox_y1"], r["bbox_x2"], r["bbox_y2"]), r["person_id"]))
    return out


def is_rejected(loaded: dict[str, list[tuple[BBox, int]]], content_hash: str | None, bbox: BBox, person_id: int) -> bool:
    return bool(content_hash) and any(
        pid == person_id and _iou(b, bbox) >= ASSIGNMENT_IOU_THRESHOLD for b, pid in loaded.get(content_hash, [])
    )
