"""Unit tests for core/organize_plan.py — no ML, pure DB logic."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from mediamind.core.organize_plan import PlannedMove, build_organize_plan, safe_folder_name
from mediamind.store.db import open_db
from mediamind.store.persons import FileFaces, persist_face_scan, upsert_file
from mediamind.store.embeddings import CachedFace

PROVIDER = "fake-color"


@pytest.fixture
def conn(tmp_path: Path):
    db = open_db(tmp_path / ".mediamind" / "index.db")
    yield db
    db.close()


def _emb(r: float, g: float, b: float) -> np.ndarray:
    v = np.array([r, g, b], dtype=np.float32)
    return v / (np.linalg.norm(v) or 1.0)


def _face(r: float, g: float, b: float) -> CachedFace:
    return CachedFace(frame_no=0, bbox=(0.0, 0.0, 64.0, 64.0), embedding=_emb(r, g, b))


def _do_scan(conn, file_faces, labels):
    persist_face_scan(
        conn,
        scan_id="s1",
        provider_id=PROVIDER,
        file_faces=file_faces,
        labels=np.array(labels, dtype=int),
        owners=[i for i, ff in enumerate(file_faces) for _ in ff.faces],
        started_at=time.time() - 1,
        finished_at=time.time(),
        params={"provider_id": PROVIDER},
        summary={"files": len(file_faces), "faces": sum(len(ff.faces) for ff in file_faces), "people": len(set(l for l in labels if l != -1))},
    )


# ---------------------------------------------------------------------------
# safe_folder_name
# ---------------------------------------------------------------------------

def test_safe_folder_name_basic():
    assert safe_folder_name("Alice") == "Alice"


def test_safe_folder_name_strips_illegal_chars():
    assert safe_folder_name("Bob/Smith") == "Bob_Smith"
    assert safe_folder_name("A:B*C") == "A_B_C"


def test_safe_folder_name_truncates():
    long_name = "x" * 200
    assert len(safe_folder_name(long_name)) <= 100


def test_safe_folder_name_empty_fallback():
    assert safe_folder_name("") == "_unnamed"
    assert safe_folder_name("   ") == "_unnamed"


# ---------------------------------------------------------------------------
# build_organize_plan
# ---------------------------------------------------------------------------

def test_plan_routes_named_person_correctly(conn):
    fid = upsert_file(conn, "alice.jpg", "photo", 100, 0.0, "h_a", True)
    conn.commit()

    ff = [FileFaces(file_id=fid, content_hash="h_a", decoded_ok=True, faces=[_face(1, 0, 0)])]
    _do_scan(conn, ff, [0])

    pid = conn.execute("SELECT id FROM persons WHERE provider_id = ?", (PROVIDER,)).fetchone()["id"]
    conn.execute("UPDATE persons SET name = 'Alice' WHERE id = ?", (pid,))
    conn.commit()

    moves = build_organize_plan(conn, PROVIDER)
    assert len(moves) == 1
    assert moves[0].dest_folder_rel == "People/Alice"
    assert moves[0].person_name == "Alice"
    assert moves[0].source_rel == "alice.jpg"


def test_plan_routes_noise_to_noise_folder(conn):
    fid = upsert_file(conn, "noise.jpg", "photo", 100, 0.0, "h_n", True)
    conn.commit()

    ff = [FileFaces(file_id=fid, content_hash="h_n", decoded_ok=True, faces=[_face(0.5, 0.5, 0.5)])]
    _do_scan(conn, ff, [-1])

    moves = build_organize_plan(conn, PROVIDER)
    assert len(moves) == 1
    assert "_noise" in moves[0].dest_folder_rel


def test_plan_omits_files_with_no_face_records(conn):
    # File exists in `files` table but has NO faces entry — stays in place
    fid = upsert_file(conn, "no_face.jpg", "photo", 100, 0.0, "h_nf", True)
    conn.commit()
    # Don't add any faces — the file should not appear in the plan

    # Add a dummy scan row so _require_provider_id works
    conn.execute(
        "INSERT INTO scans (id, type, state, params, started_at, finished_at, summary) VALUES (?, 'faces', 'succeeded', ?, ?, ?, ?)",
        ("s-dummy", '{"provider_id": "fake-color"}', time.time() - 1, time.time(), '{}'),
    )
    conn.commit()

    moves = build_organize_plan(conn, PROVIDER)
    assert all(m.source_rel != "no_face.jpg" for m in moves)


def test_plan_multi_person_picks_dominant(conn):
    fid = upsert_file(conn, "both.jpg", "photo", 100, 0.0, "h_b", True)
    conn.commit()

    # 2 faces in same file: person 0 appears twice, person 1 once
    ff = [FileFaces(
        file_id=fid,
        content_hash="h_b",
        decoded_ok=True,
        faces=[_face(1, 0, 0), _face(1, 0, 0.1), _face(0, 0, 1)],
    )]
    _do_scan(conn, ff, [0, 0, 1])

    # Scan assigns labels but persons may not be named yet; get their IDs
    person_rows = conn.execute("SELECT id FROM persons WHERE provider_id = ? ORDER BY id", (PROVIDER,)).fetchall()
    assert len(person_rows) == 2

    moves = build_organize_plan(conn, PROVIDER)
    assert len(moves) == 1
    # The dominant person (2 faces) should be picked
    pid_0 = person_rows[0]["id"]
    assert moves[0].person_id == pid_0


def test_plan_unreadable_file_goes_to_unsorted(conn):
    fid = upsert_file(conn, "bad.jpg", "photo", 100, 0.0, "h_bad", False)
    conn.commit()

    ff = [FileFaces(file_id=fid, content_hash="h_bad", decoded_ok=False, faces=[])]
    # Even with no faces, decoded_ok=False → _unsorted
    persist_face_scan(
        conn,
        scan_id="s_bad",
        provider_id=PROVIDER,
        file_faces=ff,
        labels=np.array([], dtype=int),
        owners=[],
        started_at=time.time() - 1,
        finished_at=time.time(),
        params={"provider_id": PROVIDER},
        summary={"files": 1, "faces": 0, "people": 0},
    )

    # Manually insert a face row with decoded_ok=False to trigger the unsorted path
    conn.execute(
        "INSERT INTO faces (file_id, provider_id, frame_no, bbox_x1, bbox_y1, bbox_x2, bbox_y2, embedding, person_id, confidence) VALUES (?, ?, 0, 0, 0, 1, 1, ?, NULL, 0.0)",
        (fid, PROVIDER, np.zeros(3, dtype=np.float32).tobytes()),
    )
    conn.commit()

    moves = build_organize_plan(conn, PROVIDER)
    assert any("_unsorted" in m.dest_folder_rel for m in moves)


def test_plan_custom_target_rel(conn):
    fid = upsert_file(conn, "r.jpg", "photo", 100, 0.0, "h_r", True)
    conn.commit()

    ff = [FileFaces(file_id=fid, content_hash="h_r", decoded_ok=True, faces=[_face(1, 0, 0)])]
    _do_scan(conn, ff, [0])

    pid = conn.execute("SELECT id FROM persons WHERE provider_id = ?", (PROVIDER,)).fetchone()["id"]
    conn.execute("UPDATE persons SET name = 'Dave' WHERE id = ?", (pid,))
    conn.commit()

    moves = build_organize_plan(conn, PROVIDER, target_rel="Sorted")
    assert moves[0].dest_folder_rel.startswith("Sorted/")
