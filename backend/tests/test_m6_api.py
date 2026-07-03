"""API tests for M6 routes: organize (preview/execute/undo/audit) + pending decisions.

Uses FakeColorProvider so no real model is needed.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mediamind.api.app import create_app
from mediamind.providers.catalog import CatalogEntry, LicenseInfo
from mediamind.providers.manager import ProviderManager
from mediamind.store.db import library_db_path, open_db
from mediamind.store.persons import (
    FileFaces,
    persist_face_scan,
    rename_person,
    upsert_file,
)
from mediamind.store.embeddings import CachedFace
from mediamind.config import library_data_dir

PROVIDER = "fake-color"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_pm(tmp_path: Path):
    """ProviderManager with a fake catalog entry (kind='fake' → always installed)."""
    catalog_entry = CatalogEntry(
        id=PROVIDER,
        name="Fake Color",
        description="Test only",
        license=LicenseInfo(name="MIT", url="", commercial_use=True, summary=""),
        downloads=[],
        archive="none",
        extract_subdir="",
        embedding_dim=3,
        cluster_eps=0.5,
        kind="fake",
    )
    pm = ProviderManager(tmp_path / "models", catalog=[catalog_entry])
    return pm


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_pm):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app(provider_manager=fake_pm)) as c:
        yield c


def _add_library(client, path: Path) -> str:
    res = client.post("/v1/libraries", json={"path": str(path)})
    assert res.status_code == 201
    return res.json()["id"]


def _make_library(root: Path) -> None:
    Image.new("RGB", (64, 64), (255, 0, 0)).save(root / "red.jpg")
    Image.new("RGB", (64, 64), (0, 0, 255)).save(root / "blue.jpg")


def _seed_persons_db(library_root: Path, name_alice: bool = False) -> None:
    """Insert a minimal face scan result directly into the DB (bypasses provider)."""
    data_dir = library_data_dir(library_root)
    conn = open_db(library_db_path(data_dir))

    red_emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    blue_emb = np.array([0.0, 0.0, 1.0], dtype=np.float32)

    fid_red = upsert_file(conn, "red.jpg", "photo", 100, 0.0, "h_red", True)
    fid_blue = upsert_file(conn, "blue.jpg", "photo", 100, 0.0, "h_blue", True)
    conn.commit()

    ff = [
        FileFaces(file_id=fid_red, content_hash="h_red", decoded_ok=True,
                  faces=[CachedFace(frame_no=0, bbox=(0, 0, 64, 64), embedding=red_emb)]),
        FileFaces(file_id=fid_blue, content_hash="h_blue", decoded_ok=True,
                  faces=[CachedFace(frame_no=0, bbox=(0, 0, 64, 64), embedding=blue_emb)]),
    ]
    persist_face_scan(
        conn,
        scan_id="s1",
        provider_id=PROVIDER,
        file_faces=ff,
        labels=np.array([0, 1], dtype=int),
        owners=[0, 1],
        started_at=time.time() - 1,
        finished_at=time.time(),
        params={"provider_id": PROVIDER},
        summary={"files": 2, "faces": 2, "people": 2},
    )

    if name_alice:
        pid = conn.execute("SELECT id FROM persons WHERE provider_id = ? ORDER BY id LIMIT 1", (PROVIDER,)).fetchone()["id"]
        rename_person(conn, pid, "Alice")

    conn.close()


# ---------------------------------------------------------------------------
# /organize/preview
# ---------------------------------------------------------------------------

def test_organize_preview_requires_face_scan(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    lib_id = _add_library(client, lib_dir)

    res = client.post(f"/v1/libraries/{lib_id}/organize/preview")
    assert res.status_code == 422


def test_organize_preview_returns_plan(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir, name_alice=True)

    lib_id = _add_library(client, lib_dir)
    res = client.post(f"/v1/libraries/{lib_id}/organize/preview")
    assert res.status_code == 200
    body = res.json()
    assert body["planned"] == 2  # red + blue files
    assert "moves" in body
    assert len(body["moves"]) == 2

    # Alice's file should be routed to People/Alice
    alice_moves = [m for m in body["moves"] if m["person_name"] == "Alice"]
    assert len(alice_moves) == 1
    assert alice_moves[0]["dest_folder_rel"] == "People/Alice"


# ---------------------------------------------------------------------------
# /organize/execute (dry-run)
# ---------------------------------------------------------------------------

def test_organize_dry_run_does_not_move_files(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir)
    lib_id = _add_library(client, lib_dir)

    res = client.post(f"/v1/libraries/{lib_id}/organize/execute", json={"dry_run": True})
    assert res.status_code == 200
    body = res.json()
    assert body["dry_run"] is True
    assert body["planned"] == body["handled"]  # dry-run always handles all

    # Actual files should still be in original locations
    assert (lib_dir / "red.jpg").exists()
    assert (lib_dir / "blue.jpg").exists()


def test_organize_execute_moves_files(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir, name_alice=True)
    lib_id = _add_library(client, lib_dir)

    res = client.post(f"/v1/libraries/{lib_id}/organize/execute", json={"dry_run": False})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True

    # Alice's file moved; original gone
    assert not (lib_dir / "red.jpg").exists()
    assert (lib_dir / "People" / "Alice" / "red.jpg").exists()


# ---------------------------------------------------------------------------
# /organize/undo
# ---------------------------------------------------------------------------

def test_undo_reverses_organize(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir, name_alice=True)
    lib_id = _add_library(client, lib_dir)

    # Execute
    client.post(f"/v1/libraries/{lib_id}/organize/execute", json={"dry_run": False})
    assert (lib_dir / "People" / "Alice" / "red.jpg").exists()

    # Undo
    res = client.post(f"/v1/libraries/{lib_id}/organize/undo")
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert (lib_dir / "red.jpg").exists()


def test_undo_with_no_previous_action_returns_404(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir)
    lib_id = _add_library(client, lib_dir)

    res = client.post(f"/v1/libraries/{lib_id}/organize/undo")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# /organize/audit
# ---------------------------------------------------------------------------

def test_audit_records_execute_and_undo(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir, name_alice=True)
    lib_id = _add_library(client, lib_dir)

    client.post(f"/v1/libraries/{lib_id}/organize/execute", json={"dry_run": False})
    client.post(f"/v1/libraries/{lib_id}/organize/undo")

    res = client.get(f"/v1/libraries/{lib_id}/organize/audit")
    assert res.status_code == 200
    actions = res.json()
    # At least 2 actions: the organize + the undo
    assert len(actions) >= 2
    kinds = {a["kind"] for a in actions}
    assert "organize-by-person" in kinds
    assert "undo" in kinds


# ---------------------------------------------------------------------------
# /pending routes
# ---------------------------------------------------------------------------

def test_pending_list_empty_without_pending_matches(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir)
    lib_id = _add_library(client, lib_dir)

    res = client.get(f"/v1/libraries/{lib_id}/pending")
    assert res.status_code == 200
    assert res.json() == []


def test_pending_decisions_confirm(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir)
    lib_id = _add_library(client, lib_dir)

    data_dir = library_data_dir(lib_dir)
    conn = open_db(library_db_path(data_dir))

    # Create a pending match manually
    pid = conn.execute("SELECT id FROM persons WHERE provider_id = ? ORDER BY id LIMIT 1", (PROVIDER,)).fetchone()["id"]
    rename_person(conn, pid, "Eve")
    face_id = conn.execute("SELECT id FROM faces WHERE person_id = ? LIMIT 1", (pid,)).fetchone()["id"]
    # Set face person_id to NULL (as if pending)
    conn.execute("UPDATE faces SET person_id = NULL WHERE id = ?", (face_id,))
    conn.execute(
        "INSERT INTO pending_matches (face_id, person_id, confidence) VALUES (?, ?, ?)",
        (face_id, pid, 0.92),
    )
    conn.commit()
    pending_id = conn.execute("SELECT id FROM pending_matches WHERE decision IS NULL").fetchone()["id"]
    conn.close()

    # List pending
    res = client.get(f"/v1/libraries/{lib_id}/pending")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["person_name"] == "Eve"

    # Confirm
    res2 = client.post(
        f"/v1/libraries/{lib_id}/pending/decisions",
        json={"decisions": [{"pending_id": pending_id, "decision": "confirmed"}]},
    )
    assert res2.status_code == 200
    assert res2.json()["updated"] == 1

    # Check face now assigned
    conn = open_db(library_db_path(data_dir))
    face = conn.execute("SELECT person_id FROM faces WHERE id = ?", (face_id,)).fetchone()
    assert face["person_id"] == pid
    pm_row = conn.execute("SELECT decision FROM pending_matches WHERE id = ?", (pending_id,)).fetchone()
    assert pm_row["decision"] == "confirmed"
    conn.close()


def test_pending_decisions_reject(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir)
    lib_id = _add_library(client, lib_dir)

    data_dir = library_data_dir(lib_dir)
    conn = open_db(library_db_path(data_dir))

    pid = conn.execute("SELECT id FROM persons WHERE provider_id = ? ORDER BY id LIMIT 1", (PROVIDER,)).fetchone()["id"]
    rename_person(conn, pid, "Frank")
    face_id = conn.execute("SELECT id FROM faces WHERE person_id = ? LIMIT 1", (pid,)).fetchone()["id"]
    conn.execute("UPDATE faces SET person_id = NULL WHERE id = ?", (face_id,))
    conn.execute(
        "INSERT INTO pending_matches (face_id, person_id, confidence) VALUES (?, ?, ?)",
        (face_id, pid, 0.75),
    )
    conn.commit()
    pending_id = conn.execute("SELECT id FROM pending_matches WHERE decision IS NULL").fetchone()["id"]
    conn.close()

    res = client.post(
        f"/v1/libraries/{lib_id}/pending/decisions",
        json={"decisions": [{"pending_id": pending_id, "decision": "rejected"}]},
    )
    assert res.status_code == 200

    conn = open_db(library_db_path(data_dir))
    face = conn.execute("SELECT person_id FROM faces WHERE id = ?", (face_id,)).fetchone()
    assert face["person_id"] is None  # still unassigned
    pm_row = conn.execute("SELECT decision FROM pending_matches WHERE id = ?", (pending_id,)).fetchone()
    assert pm_row["decision"] == "rejected"
    conn.close()


def test_pending_invalid_decision_returns_422(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir)
    lib_id = _add_library(client, lib_dir)

    res = client.post(
        f"/v1/libraries/{lib_id}/pending/decisions",
        json={"decisions": [{"pending_id": 99, "decision": "maybe"}]},
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# persons endpoint — pending_count
# ---------------------------------------------------------------------------

def test_persons_endpoint_includes_pending_count(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir)
    lib_id = _add_library(client, lib_dir)

    data_dir = library_data_dir(lib_dir)
    conn = open_db(library_db_path(data_dir))
    pid = conn.execute("SELECT id FROM persons WHERE provider_id = ? ORDER BY id LIMIT 1", (PROVIDER,)).fetchone()["id"]
    face_id = conn.execute("SELECT id FROM faces WHERE person_id = ? LIMIT 1", (pid,)).fetchone()["id"]
    conn.execute("INSERT INTO pending_matches (face_id, person_id, confidence) VALUES (?, ?, ?)", (face_id, pid, 0.9))
    conn.commit()
    conn.close()

    res = client.get(f"/v1/libraries/{lib_id}/persons")
    assert res.status_code == 200
    assert res.json()["pending_count"] == 1
