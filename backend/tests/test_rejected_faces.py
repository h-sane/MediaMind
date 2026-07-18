"""Core-level tests for the manual "not a face" rejection safety valve:
IoU matching and that reject_face persists a region and removes the face row.
"""

from __future__ import annotations

from pathlib import Path

from mediamind.store.db import library_db_path, open_db
from mediamind.store.persons import upsert_file
from mediamind.store.rejected_faces import _iou, is_rejected, reject_face, regions_for


def test_iou_identical_boxes_is_one():
    box = (0.0, 0.0, 10.0, 10.0)
    assert _iou(box, box) == 1.0


def test_iou_disjoint_boxes_is_zero():
    assert _iou((0.0, 0.0, 10.0, 10.0), (20.0, 20.0, 30.0, 30.0)) == 0.0


def test_is_rejected_uses_overlap_threshold():
    regions = [(0.0, 0.0, 10.0, 10.0)]
    assert is_rejected(regions, (0.0, 0.0, 10.0, 10.0)) is True
    assert is_rejected(regions, (100.0, 100.0, 110.0, 110.0)) is False


def test_reject_face_persists_region_and_deletes_face_row(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    fid = upsert_file(conn, "a.jpg", "photo", 100, 0.0, "hash-a", True)
    cur = conn.execute(
        """
        INSERT INTO faces (file_id, provider_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, embedding, person_id)
        VALUES (?, 'fake', 5, 5, 15, 15, ?, NULL)
        """,
        (fid, b"\x00" * 12),
    )
    conn.commit()
    face_id = cur.lastrowid

    result = reject_face(conn, face_id)
    assert result is not None
    assert result.file_id == fid

    assert conn.execute("SELECT 1 FROM faces WHERE id = ?", (face_id,)).fetchone() is None
    regions = regions_for(conn, "hash-a", "fake")
    assert regions == [(5.0, 5.0, 15.0, 15.0)]


def test_reject_face_unknown_id_returns_none(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    assert reject_face(conn, 999) is None
