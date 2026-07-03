"""Unit tests for store/persons.py — model-free, in-memory DB."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from mediamind.store.db import open_db
from mediamind.store.embeddings import CachedFace
from mediamind.store.persons import (
    FileFaces,
    list_person_summaries,
    merge_persons,
    next_auto_label,
    persist_face_scan,
    rename_person,
    upsert_file,
)

PROVIDER = "fake-color"


@pytest.fixture
def conn(tmp_path: Path):
    db = open_db(tmp_path / ".mediamind" / "index.db")
    yield db
    db.close()


def _embedding(r: float, g: float, b: float) -> np.ndarray:
    v = np.array([r, g, b], dtype=np.float32)
    return v / np.linalg.norm(v)


def _fake_face(r: float, g: float, b: float) -> CachedFace:
    return CachedFace(frame_no=0, bbox=(0.0, 0.0, 64.0, 64.0), embedding=_embedding(r, g, b))


def _do_scan(conn, file_faces: list[FileFaces], labels: list[int]) -> dict:
    import time
    return persist_face_scan(
        conn,
        scan_id="test-scan",
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
# next_auto_label
# ---------------------------------------------------------------------------

def test_auto_label_starts_at_001(conn):
    assert next_auto_label(conn, PROVIDER) == "Person_001"


def test_auto_label_increments(conn):
    fid = upsert_file(conn, "a.jpg", "photo", 1000, 0.0, "hash_a", True)
    conn.execute(
        "INSERT INTO persons (auto_label, name, provider_id) VALUES (?, NULL, ?)",
        ("Person_003", PROVIDER),
    )
    conn.commit()
    assert next_auto_label(conn, PROVIDER) == "Person_004"


# ---------------------------------------------------------------------------
# persist_face_scan — basic reconciliation
# ---------------------------------------------------------------------------

def test_scan_creates_two_persons(conn):
    fid_red = upsert_file(conn, "red.jpg", "photo", 100, 0.0, "hash_r", True)
    fid_blue = upsert_file(conn, "blue.jpg", "photo", 100, 0.0, "hash_b", True)
    conn.commit()

    file_faces = [
        FileFaces(file_id=fid_red, content_hash="hash_r", decoded_ok=True, faces=[_fake_face(1, 0, 0)]),
        FileFaces(file_id=fid_blue, content_hash="hash_b", decoded_ok=True, faces=[_fake_face(0, 0, 1)]),
    ]
    _do_scan(conn, file_faces, labels=[0, 1])

    summaries = list_person_summaries(conn, PROVIDER)
    assert len(summaries) == 2
    assert all(s.face_count == 1 for s in summaries)


def test_noise_faces_not_assigned(conn):
    fid = upsert_file(conn, "noise.jpg", "photo", 100, 0.0, "hash_n", True)
    conn.commit()
    file_faces = [
        FileFaces(file_id=fid, content_hash="hash_n", decoded_ok=True, faces=[_fake_face(0.5, 0.5, 0.5)]),
    ]
    _do_scan(conn, file_faces, labels=[-1])  # noise

    unassigned = conn.execute("SELECT COUNT(*) FROM faces WHERE person_id IS NULL").fetchone()[0]
    assert unassigned == 1
    persons = conn.execute("SELECT * FROM persons WHERE provider_id = ?", (PROVIDER,)).fetchall()
    assert len(persons) == 0


def test_rescan_preserves_named_person(conn):
    fid = upsert_file(conn, "red.jpg", "photo", 100, 0.0, "hash_r", True)
    conn.commit()
    file_faces = [FileFaces(file_id=fid, content_hash="hash_r", decoded_ok=True, faces=[_fake_face(1, 0, 0)])]
    _do_scan(conn, file_faces, labels=[0])

    # Name the person
    pid = conn.execute("SELECT id FROM persons WHERE provider_id = ?", (PROVIDER,)).fetchone()["id"]
    rename_person(conn, pid, "Alice")

    # Re-scan (same embedding → same cluster → same person)
    conn.execute("DELETE FROM scans")
    conn.commit()
    _do_scan(conn, file_faces, labels=[0])

    persons = list_person_summaries(conn, PROVIDER)
    assert any(p.name == "Alice" for p in persons)


def test_unnamed_person_removed_when_unmatched(conn):
    fid = upsert_file(conn, "red.jpg", "photo", 100, 0.0, "hash_r", True)
    fid2 = upsert_file(conn, "blue.jpg", "photo", 100, 0.0, "hash_b", True)
    conn.commit()
    file_faces = [
        FileFaces(file_id=fid, content_hash="hash_r", decoded_ok=True, faces=[_fake_face(1, 0, 0)]),
    ]
    _do_scan(conn, file_faces, labels=[0])
    assert len(list_person_summaries(conn, PROVIDER)) == 1

    # Re-scan with only blue — the red person (unnamed) should be removed
    conn.execute("DELETE FROM scans")
    conn.commit()
    file_faces2 = [
        FileFaces(file_id=fid2, content_hash="hash_b", decoded_ok=True, faces=[_fake_face(0, 0, 1)]),
    ]
    _do_scan(conn, file_faces2, labels=[0])
    persons = list_person_summaries(conn, PROVIDER)
    assert len(persons) == 1  # only blue person


# ---------------------------------------------------------------------------
# rename_person / merge_persons
# ---------------------------------------------------------------------------

def test_rename_person(conn):
    fid = upsert_file(conn, "r.jpg", "photo", 100, 0.0, "h_r", True)
    conn.commit()
    file_faces = [FileFaces(file_id=fid, content_hash="h_r", decoded_ok=True, faces=[_fake_face(1, 0, 0)])]
    _do_scan(conn, file_faces, labels=[0])

    pid = conn.execute("SELECT id FROM persons WHERE provider_id = ?", (PROVIDER,)).fetchone()["id"]
    ok = rename_person(conn, pid, "Bob")
    assert ok is True
    row = conn.execute("SELECT name FROM persons WHERE id = ?", (pid,)).fetchone()
    assert row["name"] == "Bob"


def test_rename_person_clears_with_none(conn):
    fid = upsert_file(conn, "r.jpg", "photo", 100, 0.0, "h_r", True)
    conn.commit()
    file_faces = [FileFaces(file_id=fid, content_hash="h_r", decoded_ok=True, faces=[_fake_face(1, 0, 0)])]
    _do_scan(conn, file_faces, labels=[0])

    pid = conn.execute("SELECT id FROM persons WHERE provider_id = ?", (PROVIDER,)).fetchone()["id"]
    rename_person(conn, pid, "Temp")
    rename_person(conn, pid, None)
    row = conn.execute("SELECT name FROM persons WHERE id = ?", (pid,)).fetchone()
    assert row["name"] is None


def test_merge_persons_moves_faces(conn):
    fid1 = upsert_file(conn, "r.jpg", "photo", 100, 0.0, "h_r", True)
    fid2 = upsert_file(conn, "b.jpg", "photo", 100, 0.0, "h_b", True)
    conn.commit()
    file_faces = [
        FileFaces(file_id=fid1, content_hash="h_r", decoded_ok=True, faces=[_fake_face(1, 0, 0)]),
        FileFaces(file_id=fid2, content_hash="h_b", decoded_ok=True, faces=[_fake_face(0.9, 0.1, 0)]),
    ]
    _do_scan(conn, file_faces, labels=[0, 1])

    ids = [row["id"] for row in conn.execute("SELECT id FROM persons WHERE provider_id = ? ORDER BY id", (PROVIDER,)).fetchall()]
    assert len(ids) == 2

    ok = merge_persons(conn, ids[0], ids[1])
    assert ok is True

    remaining = conn.execute("SELECT * FROM persons WHERE provider_id = ?", (PROVIDER,)).fetchall()
    assert len(remaining) == 1
    assert remaining[0]["id"] == ids[1]

    face_count = conn.execute("SELECT COUNT(*) FROM faces WHERE person_id = ?", (ids[1],)).fetchone()[0]
    assert face_count == 2


def test_merge_same_person_returns_false(conn):
    fid = upsert_file(conn, "r.jpg", "photo", 100, 0.0, "h", True)
    conn.commit()
    file_faces = [FileFaces(file_id=fid, content_hash="h", decoded_ok=True, faces=[_fake_face(1, 0, 0)])]
    _do_scan(conn, file_faces, labels=[0])

    pid = conn.execute("SELECT id FROM persons WHERE provider_id = ?", (PROVIDER,)).fetchone()["id"]
    assert merge_persons(conn, pid, pid) is False


# ---------------------------------------------------------------------------
# pending_for_named
# ---------------------------------------------------------------------------

def test_pending_match_created_for_named_person(conn):
    fid = upsert_file(conn, "r.jpg", "photo", 100, 0.0, "h_r", True)
    conn.commit()
    file_faces = [FileFaces(file_id=fid, content_hash="h_r", decoded_ok=True, faces=[_fake_face(1, 0, 0)])]
    _do_scan(conn, file_faces, labels=[0])

    # Name the person
    pid = conn.execute("SELECT id FROM persons WHERE provider_id = ?", (PROVIDER,)).fetchone()["id"]
    rename_person(conn, pid, "Carol")

    # New file with same person → should create pending match
    fid2 = upsert_file(conn, "r2.jpg", "photo", 100, 0.0, "h_r2", True)
    conn.execute("DELETE FROM scans")
    conn.commit()

    import time
    file_faces2 = [
        FileFaces(file_id=fid, content_hash="h_r", decoded_ok=True, faces=[_fake_face(1, 0, 0)]),
        FileFaces(file_id=fid2, content_hash="h_r2", decoded_ok=True, faces=[_fake_face(0.99, 0.01, 0)]),
    ]
    persist_face_scan(
        conn,
        scan_id="test-scan-2",
        provider_id=PROVIDER,
        file_faces=file_faces2,
        labels=np.array([0, 0]),
        owners=[0, 1],
        started_at=time.time() - 1,
        finished_at=time.time(),
        params={"provider_id": PROVIDER},
        summary={"files": 2, "faces": 2, "people": 1},
        pending_for_named=True,
        new_file_ids={fid2},
    )

    pending = conn.execute("SELECT * FROM pending_matches WHERE decision IS NULL").fetchall()
    assert len(pending) == 1
    assert pending[0]["person_id"] == pid
