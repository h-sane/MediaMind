"""Unit tests for store/bindings.py — suggestion cache, accept/dismiss, release."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest

from mediamind.store import bindings as bindings_store
from mediamind.store.bindings import BindingConflictError
from mediamind.store.db import open_db
from mediamind.store.embeddings import CachedFace
from mediamind.store.persons import FileFaces, persist_face_scan, upsert_file

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


def _seed_person_folder(conn, folder: str, n_files: int = 6) -> int:
    """Scan n_files, all one person, all living directly in `folder`. Returns person_id."""
    file_faces = []
    for i in range(n_files):
        rel = f"{folder}/img{i}.jpg"
        fid = upsert_file(conn, rel, "photo", 100, 0.0, f"h{i}", True)
        file_faces.append(FileFaces(file_id=fid, content_hash=f"h{i}", decoded_ok=True, faces=[_face(1, 0, 0)]))
    conn.commit()

    persist_face_scan(
        conn,
        scan_id="s1",
        provider_id=PROVIDER,
        file_faces=file_faces,
        labels=np.array([0] * n_files, dtype=int),
        owners=list(range(n_files)),
        started_at=time.time() - 1,
        finished_at=time.time(),
        params={"provider_id": PROVIDER},
        summary={"files": n_files, "faces": n_files, "people": 1},
    )
    pid = conn.execute("SELECT id FROM persons WHERE provider_id = ?", (PROVIDER,)).fetchone()["id"]
    return pid


def _seed_person_folder_with_outlier(conn, folder: str, n_files: int = 6) -> tuple[int, int]:
    """n_files - 1 files of one person plus one outlier file of a second
    person, all living directly in `folder`. Returns (main_person_id,
    outlier_file_id). Coverage lands at (n_files - 1) / n_files — still a
    person-folder per the lenient-outlier rule tested in test_folder_patterns.py."""
    file_faces = []
    for i in range(n_files):
        rel = f"{folder}/img{i}.jpg"
        fid = upsert_file(conn, rel, "photo", 100, 0.0, f"h{i}", True)
        face = _face(1, 0, 0) if i < n_files - 1 else _face(0, 1, 0)
        file_faces.append(FileFaces(file_id=fid, content_hash=f"h{i}", decoded_ok=True, faces=[face]))
    conn.commit()

    labels = np.array([0] * (n_files - 1) + [1], dtype=int)
    persist_face_scan(
        conn,
        scan_id="s1",
        provider_id=PROVIDER,
        file_faces=file_faces,
        labels=labels,
        owners=list(range(n_files)),
        started_at=time.time() - 1,
        finished_at=time.time(),
        params={"provider_id": PROVIDER},
        summary={"files": n_files, "faces": n_files, "people": 2},
    )
    main_pid = conn.execute(
        "SELECT id FROM persons WHERE provider_id = ? ORDER BY id LIMIT 1", (PROVIDER,)
    ).fetchone()["id"]
    return main_pid, file_faces[-1].file_id


# ---------------------------------------------------------------------------
# refresh_suggestions
# ---------------------------------------------------------------------------

def test_refresh_creates_pending_suggestion(conn):
    _seed_person_folder(conn, "Family/Alice")
    result = bindings_store.refresh_suggestions(conn, PROVIDER)
    assert result["suggested"] == 1

    suggestions = bindings_store.list_suggestions(conn, PROVIDER, status="pending")
    assert len(suggestions) == 1
    assert suggestions[0].folder_rel == "Family/Alice"
    assert suggestions[0].kind == "person"


def test_refresh_does_not_resuggest_bound_folder(conn):
    _seed_person_folder(conn, "Family/Alice")
    bindings_store.refresh_suggestions(conn, PROVIDER)
    suggestion = bindings_store.list_suggestions(conn, PROVIDER)[0]
    bindings_store.accept_suggestion(conn, suggestion.id)

    result = bindings_store.refresh_suggestions(conn, PROVIDER)
    assert result["suggested"] == 0
    assert bindings_store.list_suggestions(conn, PROVIDER, status="pending") == []


def test_refresh_removes_stale_pending_suggestion(conn):
    _seed_person_folder(conn, "Family/Alice")
    bindings_store.refresh_suggestions(conn, PROVIDER)
    assert len(bindings_store.list_suggestions(conn, PROVIDER)) == 1

    # Simulate the folder no longer qualifying (e.g. files moved away): delete
    # the faces backing it, so the next detection pass finds nothing there.
    conn.execute("DELETE FROM faces")
    conn.commit()

    result = bindings_store.refresh_suggestions(conn, PROVIDER)
    assert result["removed_stale"] == 1
    assert bindings_store.list_suggestions(conn, PROVIDER) == []


def test_refresh_leaves_dismissed_suggestion_dismissed(conn):
    _seed_person_folder(conn, "Family/Alice")
    bindings_store.refresh_suggestions(conn, PROVIDER)
    suggestion = bindings_store.list_suggestions(conn, PROVIDER)[0]
    bindings_store.dismiss_suggestion(conn, suggestion.id)

    bindings_store.refresh_suggestions(conn, PROVIDER)
    assert bindings_store.list_suggestions(conn, PROVIDER, status="pending") == []
    dismissed = bindings_store.list_suggestions(conn, PROVIDER, status="dismissed")
    assert len(dismissed) == 1
    assert dismissed[0].id == suggestion.id


# ---------------------------------------------------------------------------
# accept_suggestion
# ---------------------------------------------------------------------------

def test_accept_person_suggestion_creates_binding_and_names_person(conn):
    pid = _seed_person_folder(conn, "Family/Alice")
    bindings_store.refresh_suggestions(conn, PROVIDER)
    suggestion = bindings_store.list_suggestions(conn, PROVIDER)[0]

    binding = bindings_store.accept_suggestion(conn, suggestion.id)
    assert binding.folder_rel == "Family/Alice"
    assert binding.kind == "person"
    assert binding.person_ids == [pid]

    person_name = conn.execute("SELECT name FROM persons WHERE id = ?", (pid,)).fetchone()["name"]
    assert person_name == "Alice"

    # suggestion moved to accepted
    accepted = bindings_store.list_suggestions(conn, PROVIDER, status="accepted")
    assert len(accepted) == 1


def test_accept_does_not_override_existing_name(conn):
    pid = _seed_person_folder(conn, "Family/Bob")
    conn.execute("UPDATE persons SET name = 'RealBob' WHERE id = ?", (pid,))
    conn.commit()

    bindings_store.refresh_suggestions(conn, PROVIDER)
    suggestion = bindings_store.list_suggestions(conn, PROVIDER)[0]
    bindings_store.accept_suggestion(conn, suggestion.id)

    name = conn.execute("SELECT name FROM persons WHERE id = ?", (pid,)).fetchone()["name"]
    assert name == "RealBob"


def test_accept_already_accepted_raises(conn):
    _seed_person_folder(conn, "Family/Alice")
    bindings_store.refresh_suggestions(conn, PROVIDER)
    suggestion = bindings_store.list_suggestions(conn, PROVIDER)[0]
    bindings_store.accept_suggestion(conn, suggestion.id)

    with pytest.raises(ValueError):
        bindings_store.accept_suggestion(conn, suggestion.id)


def test_accept_conflicting_person_raises_and_rolls_back(conn):
    """A person already bound to one folder can't be bound to a second."""
    pid = _seed_person_folder(conn, "Family/Alice")
    bindings_store.refresh_suggestions(conn, PROVIDER)
    suggestion = bindings_store.list_suggestions(conn, PROVIDER)[0]
    bindings_store.accept_suggestion(conn, suggestion.id)

    # Manually craft a second pending suggestion for the same person in a
    # different folder (simulates two folders detected before either was
    # accepted) and confirm accept fails cleanly rather than half-inserting.
    conn.execute(
        """
        INSERT INTO binding_suggestions
          (folder_rel, kind, provider_id, file_count, coverage, person_ids, outlier_file_ids, status, created_at)
        VALUES ('Family/AliceAgain', 'person', ?, 6, 1.0, ?, '[]', 'pending', ?)
        """,
        (PROVIDER, json.dumps([pid]), time.time()),
    )
    conn.commit()
    dupe = conn.execute(
        "SELECT id FROM binding_suggestions WHERE folder_rel = 'Family/AliceAgain'"
    ).fetchone()

    with pytest.raises(BindingConflictError):
        bindings_store.accept_suggestion(conn, dupe["id"])

    # No orphaned binding row left behind from the failed insert.
    bindings = bindings_store.list_bindings(conn, PROVIDER)
    assert len(bindings) == 1
    assert bindings[0].folder_rel == "Family/Alice"


# ---------------------------------------------------------------------------
# dismiss / release / outliers
# ---------------------------------------------------------------------------

def test_dismiss_pending_suggestion(conn):
    _seed_person_folder(conn, "Family/Alice")
    bindings_store.refresh_suggestions(conn, PROVIDER)
    suggestion = bindings_store.list_suggestions(conn, PROVIDER)[0]

    assert bindings_store.dismiss_suggestion(conn, suggestion.id) is True
    assert bindings_store.list_suggestions(conn, PROVIDER, status="pending") == []


def test_dismiss_nonexistent_returns_false(conn):
    assert bindings_store.dismiss_suggestion(conn, 999) is False


def test_release_binding_unfreezes_folder(conn):
    _seed_person_folder(conn, "Family/Alice")
    bindings_store.refresh_suggestions(conn, PROVIDER)
    suggestion = bindings_store.list_suggestions(conn, PROVIDER)[0]
    binding = bindings_store.accept_suggestion(conn, suggestion.id)

    assert bindings_store.release_binding(conn, binding.id) is True
    assert bindings_store.list_bindings(conn, PROVIDER) == []
    # member row cascades away too
    members = conn.execute("SELECT * FROM folder_binding_members").fetchall()
    assert members == []


def test_set_accepted_outliers(conn):
    _seed_person_folder(conn, "Family/Alice")
    bindings_store.refresh_suggestions(conn, PROVIDER)
    suggestion = bindings_store.list_suggestions(conn, PROVIDER)[0]
    binding = bindings_store.accept_suggestion(conn, suggestion.id)

    updated = bindings_store.set_accepted_outliers(conn, binding.id, [42, 7])
    assert updated.accepted_outlier_file_ids == [7, 42]


# ---------------------------------------------------------------------------
# outlier candidates (Phase D — outlier review UI backing data)
# ---------------------------------------------------------------------------

def test_accept_suggestion_reports_detected_outlier_not_yet_accepted(conn):
    _, outlier_fid = _seed_person_folder_with_outlier(conn, "Family/Alice")
    bindings_store.refresh_suggestions(conn, PROVIDER)
    suggestion = bindings_store.list_suggestions(conn, PROVIDER)[0]

    binding = bindings_store.accept_suggestion(conn, suggestion.id)
    assert binding.accepted_outlier_file_ids == []
    assert len(binding.outliers) == 1
    assert binding.outliers[0].file_id == outlier_fid
    assert binding.outliers[0].path == "Family/Alice/img5.jpg"
    assert binding.outliers[0].accepted is False


def test_list_bindings_includes_outlier_candidates(conn):
    _seed_person_folder_with_outlier(conn, "Family/Alice")
    bindings_store.refresh_suggestions(conn, PROVIDER)
    suggestion = bindings_store.list_suggestions(conn, PROVIDER)[0]
    bindings_store.accept_suggestion(conn, suggestion.id)

    bindings = bindings_store.list_bindings(conn, PROVIDER)
    assert len(bindings) == 1
    assert len(bindings[0].outliers) == 1
    assert bindings[0].outliers[0].accepted is False


def test_set_accepted_outliers_flips_accepted_flag_on_candidate(conn):
    _, outlier_fid = _seed_person_folder_with_outlier(conn, "Family/Alice")
    bindings_store.refresh_suggestions(conn, PROVIDER)
    suggestion = bindings_store.list_suggestions(conn, PROVIDER)[0]
    binding = bindings_store.accept_suggestion(conn, suggestion.id)

    updated = bindings_store.set_accepted_outliers(conn, binding.id, [outlier_fid])
    assert len(updated.outliers) == 1
    assert updated.outliers[0].file_id == outlier_fid
    assert updated.outliers[0].accepted is True

    bindings = bindings_store.list_bindings(conn, PROVIDER)
    assert bindings[0].outliers[0].accepted is True


def test_binding_with_no_outliers_reports_empty_list(conn):
    _seed_person_folder(conn, "Family/Alice")
    bindings_store.refresh_suggestions(conn, PROVIDER)
    suggestion = bindings_store.list_suggestions(conn, PROVIDER)[0]
    binding = bindings_store.accept_suggestion(conn, suggestion.id)
    assert binding.outliers == []
