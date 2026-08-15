"""Tests for core/ingest.py's immediate face-matching (Performance & Ingest
V4 Phase 4) — the named-person review gate must survive the incremental
path exactly as it does in the full scan (store/persons.py's
persist_face_scan). Model-free (FakeColorProvider).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mediamind.core.ingest import ingest_file
from mediamind.core.scanner import ScannedFile, kind_of
from mediamind.providers.fake import FakeColorProvider
from mediamind.store.db import open_db

PROVIDER = "fake-color"


@pytest.fixture
def conn(tmp_path: Path):
    c = open_db(tmp_path / ".mediamind" / "index.db")
    yield c
    c.close()


def _scanned(root: Path, rel: str) -> ScannedFile:
    path = root / rel
    stat = path.stat()
    return ScannedFile(path=path, kind=kind_of(path), size=stat.st_size, mtime=stat.st_mtime)


def _make_person(conn, embedding: np.ndarray, name: str | None) -> int:
    centroid = (embedding / np.linalg.norm(embedding)).astype(np.float32)
    cur = conn.execute(
        "INSERT INTO persons (auto_label, name, provider_id, centroid) VALUES (?, ?, ?, ?)",
        ("Person_001", name, PROVIDER, centroid.tobytes()),
    )
    conn.commit()
    return cur.lastrowid


# FakeColorProvider embeds the frame's mean color as loaded by
# core.loaders.load_image, which decodes to BGR (cv2 convention) — a PIL RGB
# (255, 0, 0) red image therefore embeds as BGR [0, 0, 255] normalized, not
# [1, 0, 0]. Named for the PIL RGB tuple used to create the fixture, valued
# for the BGR embedding FakeColorProvider actually produces.
RED = np.array([0.0, 0.0, 1.0], dtype=np.float32)
BLUE = np.array([1.0, 0.0, 0.0], dtype=np.float32)


def test_match_to_named_person_creates_pending_not_auto_filed(tmp_path: Path, conn):
    pid = _make_person(conn, RED, name="Alice")
    Image.new("RGB", (64, 64), (255, 0, 0)).save(tmp_path / "red.jpg")

    outcome = ingest_file(
        conn, tmp_path, _scanned(tmp_path, "red.jpg"),
        provider=FakeColorProvider(), provider_id=PROVIDER, warm_thumbnail=False,
    )
    assert outcome.new_faces == 1
    assert outcome.pending_faces == 1

    face = conn.execute("SELECT id, person_id FROM faces").fetchone()
    assert face["person_id"] is None, "a named-person match must never be auto-filed"

    pending = conn.execute("SELECT * FROM pending_matches WHERE decision IS NULL").fetchall()
    assert len(pending) == 1
    assert pending[0]["person_id"] == pid
    assert pending[0]["face_id"] == face["id"]


def test_match_to_unnamed_person_auto_attaches_and_records_assignment(tmp_path: Path, conn):
    pid = _make_person(conn, BLUE, name=None)
    Image.new("RGB", (64, 64), (0, 0, 255)).save(tmp_path / "blue.jpg")

    outcome = ingest_file(
        conn, tmp_path, _scanned(tmp_path, "blue.jpg"),
        provider=FakeColorProvider(), provider_id=PROVIDER, warm_thumbnail=False,
    )
    assert outcome.new_faces == 1
    assert outcome.pending_faces == 0

    face = conn.execute("SELECT person_id FROM faces").fetchone()
    assert face["person_id"] == pid, "an unnamed-person match auto-attaches, matching today's behavior"

    assignments = conn.execute(
        "SELECT * FROM face_assignments WHERE person_id = ? AND source = 'cluster'", (pid,)
    ).fetchall()
    assert len(assignments) == 1, "auto-attach must durably record the assignment"

    assert conn.execute("SELECT * FROM pending_matches").fetchall() == []


def test_match_to_nobody_stores_person_id_null(tmp_path: Path, conn):
    _make_person(conn, RED, name="Alice")  # unrelated color, must not match
    Image.new("RGB", (64, 64), (0, 255, 0)).save(tmp_path / "green.jpg")  # green: far from red

    outcome = ingest_file(
        conn, tmp_path, _scanned(tmp_path, "green.jpg"),
        provider=FakeColorProvider(), provider_id=PROVIDER, warm_thumbnail=False,
    )
    assert outcome.new_faces == 1
    assert outcome.pending_faces == 0

    face = conn.execute("SELECT person_id FROM faces").fetchone()
    assert face["person_id"] is None
    assert conn.execute("SELECT * FROM pending_matches").fetchall() == []


def test_rejected_match_not_restaged_for_same_content_at_new_path(tmp_path: Path, conn):
    """A face-content+person pair a user already rejected (via the pending
    review flow) must not be re-proposed just because the identical image
    bytes show up again at a different path."""
    pid = _make_person(conn, RED, name="Alice")

    img = Image.new("RGB", (64, 64), (255, 0, 0))
    img.save(tmp_path / "red_a.jpg")
    img.save(tmp_path / "red_b.jpg")  # byte-identical -> same content_hash

    ingest_file(
        conn, tmp_path, _scanned(tmp_path, "red_a.jpg"),
        provider=FakeColorProvider(), provider_id=PROVIDER, warm_thumbnail=False,
    )
    pending = conn.execute("SELECT * FROM pending_matches WHERE decision IS NULL").fetchall()
    assert len(pending) == 1
    conn.execute("UPDATE pending_matches SET decision = 'rejected' WHERE id = ?", (pending[0]["id"],))
    conn.commit()

    outcome = ingest_file(
        conn, tmp_path, _scanned(tmp_path, "red_b.jpg"),
        provider=FakeColorProvider(), provider_id=PROVIDER, warm_thumbnail=False,
    )
    assert outcome.new_faces == 1
    assert outcome.pending_faces == 0, "a previously-rejected match must not be re-staged"

    face_b = conn.execute(
        "SELECT f.person_id FROM faces f JOIN files fi ON fi.id = f.file_id WHERE fi.path = ?", ("red_b.jpg",)
    ).fetchone()
    assert face_b["person_id"] is None

    still_only_one_pending_ever = conn.execute("SELECT COUNT(*) FROM pending_matches").fetchone()[0]
    assert still_only_one_pending_ever == 1


def test_reingesting_same_file_does_not_duplicate_faces_rows(tmp_path: Path, conn):
    """Idempotency guard: a file that already has faces rows for this
    provider (e.g. re-enqueued by the watcher, or already handled by a full
    scan) must not get matched/inserted again."""
    _make_person(conn, BLUE, name=None)
    Image.new("RGB", (64, 64), (0, 0, 255)).save(tmp_path / "blue.jpg")
    scanned = _scanned(tmp_path, "blue.jpg")

    outcome1 = ingest_file(conn, tmp_path, scanned, provider=FakeColorProvider(), provider_id=PROVIDER, warm_thumbnail=False)
    assert outcome1.new_faces == 1

    outcome2 = ingest_file(conn, tmp_path, scanned, provider=FakeColorProvider(), provider_id=PROVIDER, warm_thumbnail=False)
    assert outcome2.new_faces == 0
    assert outcome2.was_cached is True

    assert conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0] == 1


def test_no_faces_in_image_does_not_touch_persons(tmp_path: Path, conn):
    Image.new("RGB", (64, 64), (0, 0, 0)).save(tmp_path / "black.jpg")
    outcome = ingest_file(
        conn, tmp_path, _scanned(tmp_path, "black.jpg"),
        provider=FakeColorProvider(), provider_id=PROVIDER, warm_thumbnail=False,
    )
    assert outcome.new_faces == 0
    assert conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0] == 0
