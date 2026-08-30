"""ADR-0010: a file inside a person's bound folder needs no Suggestions review.

`placement_confirmed_pending_ids` drops pending matches for a bound folder's
*own* person, while leaving co-appearing others and out-of-folder matches alone.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from mediamind.store.bindings import placement_confirmed_pending_ids
from mediamind.store.db import open_db
from mediamind.store.persons import upsert_file

PROVIDER = "fake-color"


@pytest.fixture
def conn(tmp_path: Path):
    db = open_db(tmp_path / ".mediamind" / "index.db")
    yield db
    db.close()


def _person(conn, name: str | None) -> int:
    cur = conn.execute(
        "INSERT INTO persons (auto_label, provider_id, name) VALUES (?, ?, ?)",
        (name or "Person_x", PROVIDER, name),
    )
    return cur.lastrowid


def _face(conn, file_id: int) -> int:
    cur = conn.execute(
        "INSERT INTO faces (file_id, provider_id, frame_no, bbox_x1, bbox_y1, bbox_x2, bbox_y2, embedding) "
        "VALUES (?, ?, 0, 0, 0, 1, 1, X'00')",
        (file_id, PROVIDER),
    )
    return cur.lastrowid


def _pending(conn, face_id: int, person_id: int) -> int:
    cur = conn.execute(
        "INSERT INTO pending_matches (face_id, person_id, confidence) VALUES (?, ?, 0.7)",
        (face_id, person_id),
    )
    return cur.lastrowid


def _bind(conn, folder_rel: str, person_id: int) -> None:
    cur = conn.execute(
        "INSERT INTO folder_bindings (folder_rel, kind, provider_id, created_at) VALUES (?, 'person', ?, ?)",
        (folder_rel, PROVIDER, time.time()),
    )
    conn.execute(
        "INSERT INTO folder_binding_members (binding_id, person_id) VALUES (?, ?)",
        (cur.lastrowid, person_id),
    )


def test_own_person_inside_bound_folder_is_suppressed(conn):
    dad = _person(conn, "Dad")
    _bind(conn, "People/Dad", dad)
    # weak match to Dad on a file living in Dad's folder (and a subfolder)
    inside = _pending(conn, _face(conn, upsert_file(conn, "People/Dad/vid.mp4", "video", 1, 0.0, "h1", True)), dad)
    sub = _pending(conn, _face(conn, upsert_file(conn, "People/Dad/2021/x.jpg", "photo", 1, 0.0, "h2", True)), dad)
    conn.commit()
    assert placement_confirmed_pending_ids(conn) == {inside, sub}


def test_other_person_and_outside_folder_survive(conn):
    dad = _person(conn, "Dad")
    mom = _person(conn, "Mom")
    _bind(conn, "People/Dad", dad)
    # Mom co-appearing in Dad's folder — still reviewable (surface the other)
    _pending(conn, _face(conn, upsert_file(conn, "People/Dad/group.jpg", "photo", 1, 0.0, "h3", True)), mom)
    # Dad matched on a file OUTSIDE his folder — placement can't confirm it
    _pending(conn, _face(conn, upsert_file(conn, "Camera/roll.jpg", "photo", 1, 0.0, "h4", True)), dad)
    conn.commit()
    assert placement_confirmed_pending_ids(conn) == set()


def test_no_bindings_returns_empty(conn):
    dad = _person(conn, "Dad")
    _pending(conn, _face(conn, upsert_file(conn, "People/Dad/x.jpg", "photo", 1, 0.0, "h5", True)), dad)
    conn.commit()
    assert placement_confirmed_pending_ids(conn) == set()
