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
from mediamind.store.db import open_library_db
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
    conn = open_library_db(data_dir.parent)

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
    # Only Alice's file is planned — the other person is unnamed and organize
    # only ever routes named people (F10), so blue.jpg stays in place.
    assert body["planned"] == 1
    assert "moves" in body
    assert len(body["moves"]) == 1

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
    # Organize only routes named people (F10) — name one so there's a plan
    # to dry-run at all; this test is about dry_run not touching disk, not
    # about the named-people-only routing rule.
    _seed_persons_db(lib_dir, name_alice=True)
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


def test_undo_twice_returns_404_second_time(client, tmp_path):
    """An undo action must not itself be undoable -- otherwise a second call
    re-applies the original organize instead of reporting nothing to undo.
    """
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir, name_alice=True)
    lib_id = _add_library(client, lib_dir)

    client.post(f"/v1/libraries/{lib_id}/organize/execute", json={"dry_run": False})
    res = client.post(f"/v1/libraries/{lib_id}/organize/undo")
    assert res.status_code == 200
    assert (lib_dir / "red.jpg").exists()

    res2 = client.post(f"/v1/libraries/{lib_id}/organize/undo")
    assert res2.status_code == 404
    # And the file must not have been moved back into People/Alice again.
    assert (lib_dir / "red.jpg").exists()
    assert not (lib_dir / "People" / "Alice" / "red.jpg").exists()


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
    conn = open_library_db(data_dir.parent)

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
    conn = open_library_db(data_dir.parent)
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
    conn = open_library_db(data_dir.parent)

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

    conn = open_library_db(data_dir.parent)
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
    conn = open_library_db(data_dir.parent)
    pid = conn.execute("SELECT id FROM persons WHERE provider_id = ? ORDER BY id LIMIT 1", (PROVIDER,)).fetchone()["id"]
    face_id = conn.execute("SELECT id FROM faces WHERE person_id = ? LIMIT 1", (pid,)).fetchone()["id"]
    conn.execute("INSERT INTO pending_matches (face_id, person_id, confidence) VALUES (?, ?, ?)", (face_id, pid, 0.9))
    conn.commit()
    conn.close()

    res = client.get(f"/v1/libraries/{lib_id}/persons")
    assert res.status_code == 200
    assert res.json()["pending_count"] == 1


# ---------------------------------------------------------------------------
# Person primary folder (per-person "primary folder" feature)
# ---------------------------------------------------------------------------

def test_set_primary_folder_roundtrip(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir, name_alice=True)
    lib_id = _add_library(client, lib_dir)

    data_dir = library_data_dir(lib_dir)
    conn = open_library_db(data_dir.parent)
    pid = conn.execute(
        "SELECT id FROM persons WHERE provider_id = ? AND name = 'Alice'", (PROVIDER,)
    ).fetchone()["id"]
    conn.close()

    res = client.put(
        f"/v1/libraries/{lib_id}/persons/{pid}/primary-folder", json={"path": "Family/Alice"}
    )
    assert res.status_code == 200
    assert res.json() == {"ok": True, "primary_folder_path": "Family/Alice"}

    persons_res = client.get(f"/v1/libraries/{lib_id}/persons")
    alice = next(p for p in persons_res.json()["persons"] if p["id"] == pid)
    assert alice["primary_folder_path"] == "Family/Alice"

    # Clear it
    res2 = client.put(f"/v1/libraries/{lib_id}/persons/{pid}/primary-folder", json={"path": None})
    assert res2.status_code == 200
    assert res2.json()["primary_folder_path"] is None


def test_set_primary_folder_unknown_person_404(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    lib_id = _add_library(client, lib_dir)

    res = client.put(f"/v1/libraries/{lib_id}/persons/999/primary-folder", json={"path": "Family/X"})
    assert res.status_code == 404


@pytest.mark.parametrize("bad_path", ["/etc/passwd", "../escape", "Family/../../escape", r"C:\Windows"])
def test_set_primary_folder_rejects_unsafe_paths(client, tmp_path, bad_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir, name_alice=True)
    lib_id = _add_library(client, lib_dir)

    data_dir = library_data_dir(lib_dir)
    conn = open_library_db(data_dir.parent)
    pid = conn.execute(
        "SELECT id FROM persons WHERE provider_id = ? AND name = 'Alice'", (PROVIDER,)
    ).fetchone()["id"]
    conn.close()

    res = client.put(f"/v1/libraries/{lib_id}/persons/{pid}/primary-folder", json={"path": bad_path})
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Person-scoped organize preview/execute
# ---------------------------------------------------------------------------

def test_organize_preview_person_scoped_without_primary_folder_422(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir, name_alice=True)
    lib_id = _add_library(client, lib_dir)

    data_dir = library_data_dir(lib_dir)
    conn = open_library_db(data_dir.parent)
    pid = conn.execute(
        "SELECT id FROM persons WHERE provider_id = ? AND name = 'Alice'", (PROVIDER,)
    ).fetchone()["id"]
    conn.close()

    res = client.post(f"/v1/libraries/{lib_id}/organize/preview?person_id={pid}")
    assert res.status_code == 422


def test_organize_execute_person_scoped_without_primary_folder_422(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir, name_alice=True)
    lib_id = _add_library(client, lib_dir)

    data_dir = library_data_dir(lib_dir)
    conn = open_library_db(data_dir.parent)
    pid = conn.execute(
        "SELECT id FROM persons WHERE provider_id = ? AND name = 'Alice'", (PROVIDER,)
    ).fetchone()["id"]
    conn.close()

    res = client.post(
        f"/v1/libraries/{lib_id}/organize/execute", json={"dry_run": False, "person_id": pid}
    )
    assert res.status_code == 422
    assert "primary folder" in res.json()["detail"].lower()


def test_organize_execute_person_scoped_routes_to_server_resolved_folder(client, tmp_path):
    """Destination is derived from the server-side DB value regardless of
    anything the client sends -- there is no client-suppliable target field
    at all, by design (safety: server-validated destination only)."""
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir, name_alice=True)
    lib_id = _add_library(client, lib_dir)

    data_dir = library_data_dir(lib_dir)
    conn = open_library_db(data_dir.parent)
    pid = conn.execute(
        "SELECT id FROM persons WHERE provider_id = ? AND name = 'Alice'", (PROVIDER,)
    ).fetchone()["id"]
    conn.close()

    set_res = client.put(
        f"/v1/libraries/{lib_id}/persons/{pid}/primary-folder", json={"path": "Family/Alice"}
    )
    assert set_res.status_code == 200

    preview = client.post(f"/v1/libraries/{lib_id}/organize/preview?person_id={pid}")
    assert preview.status_code == 200
    pbody = preview.json()
    assert pbody["planned"] == 1
    assert pbody["moves"][0]["dest_folder_rel"] == "Family/Alice"

    res = client.post(
        f"/v1/libraries/{lib_id}/organize/execute",
        json={
            "dry_run": False,
            "person_id": pid,
            "expected_planned": pbody["planned"],
            "expected_plan_hash": pbody["plan_hash"],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["handled"] == 1

    assert not (lib_dir / "red.jpg").exists()
    assert (lib_dir / "Family" / "Alice" / "red.jpg").exists()

    # A manifest row was recorded and handled == planned.
    audit = client.get(f"/v1/libraries/{lib_id}/organize/audit")
    kinds = {a["kind"]: a for a in audit.json()}
    assert "organize-by-person" in kinds
    assert kinds["organize-by-person"]["handled"] == kinds["organize-by-person"]["planned"]


def test_organize_execute_person_scoped_plan_hash_drift_still_guarded(client, tmp_path):
    """If the primary folder changes between preview and execute, the
    destination changes too -> the plan-hash guard must still fire (409),
    same as any other plan-content drift."""
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir, name_alice=True)
    lib_id = _add_library(client, lib_dir)

    data_dir = library_data_dir(lib_dir)
    conn = open_library_db(data_dir.parent)
    pid = conn.execute(
        "SELECT id FROM persons WHERE provider_id = ? AND name = 'Alice'", (PROVIDER,)
    ).fetchone()["id"]
    conn.close()

    client.put(f"/v1/libraries/{lib_id}/persons/{pid}/primary-folder", json={"path": "Family/Alice"})
    preview = client.post(f"/v1/libraries/{lib_id}/organize/preview?person_id={pid}")
    pbody = preview.json()

    # Primary folder changes after the user confirmed the preview.
    client.put(f"/v1/libraries/{lib_id}/persons/{pid}/primary-folder", json={"path": "Family/Alice2"})

    res = client.post(
        f"/v1/libraries/{lib_id}/organize/execute",
        json={
            "dry_run": False,
            "person_id": pid,
            "expected_planned": pbody["planned"],
            "expected_plan_hash": pbody["plan_hash"],
        },
    )
    assert res.status_code == 409


def _file_with_three_questions(client, tmp_path):
    """One file suggested as Eve three times: a face, the same face in a later frame, and a
    different-looking face. Returns (lib_dir, lib_id, face ids, pending ids by face)."""
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir)
    lib_id = _add_library(client, lib_dir)

    conn = open_library_db(library_data_dir(lib_dir).parent)
    pid = conn.execute("SELECT id FROM persons WHERE provider_id = ? ORDER BY id LIMIT 1", (PROVIDER,)).fetchone()["id"]
    rename_person(conn, pid, "Eve")
    first = conn.execute("SELECT id, file_id FROM faces WHERE person_id = ?", (pid,)).fetchone()
    conn.execute("UPDATE faces SET person_id = NULL WHERE id = ?", (first["id"],))

    def add_face(frame_no: int, emb: list[float], box: float) -> int:
        return conn.execute(
            "INSERT INTO faces (file_id, provider_id, frame_no, bbox_x1, bbox_y1, bbox_x2, bbox_y2, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (first["file_id"], PROVIDER, frame_no, box, box, box + 20, box + 20, np.array(emb, dtype=np.float32).tobytes()),
        ).lastrowid

    faces = {"first": first["id"], "same": add_face(30, [0.99, 0.1, 0.0], 100), "other": add_face(60, [0.0, 1.0, 0.0], 300)}
    ids = {}
    for key, conf in (("first", 0.9), ("same", 0.8), ("other", 0.7)):
        ids[key] = conn.execute(
            "INSERT INTO pending_matches (face_id, person_id, confidence) VALUES (?, ?, ?)", (faces[key], pid, conf),
        ).lastrowid
    conn.commit()
    conn.close()
    return lib_dir, lib_id, faces, ids, pid


def test_one_question_per_file_and_a_yes_settles_the_file(client, tmp_path):
    lib_dir, lib_id, faces, ids, _ = _file_with_three_questions(client, tmp_path)

    listed = client.get(f"/v1/libraries/{lib_id}/pending").json()
    assert [(m["face_id"], m["folded_face_ids"]) for m in listed] == [(faces["first"], [faces["same"]])]

    res = client.post(f"/v1/libraries/{lib_id}/pending/decisions",
                      json={"decisions": [{"pending_id": ids["first"], "decision": "confirmed"}]})
    assert res.json()["updated"] == 2  # the shown face and the same face in the later frame

    conn = open_library_db(library_data_dir(lib_dir).parent)
    decision = {r["id"]: r["decision"] for r in conn.execute("SELECT id, decision FROM pending_matches")}
    conn.close()
    assert decision[ids["same"]] == "confirmed"
    assert decision[ids["other"]] is None  # not taught as Eve: it doesn't look like her
    # ...but the file is settled for Eve, so it is not asked again.
    assert client.get(f"/v1/libraries/{lib_id}/pending").json() == []


def test_a_no_settles_the_file_and_survives_a_rescan(client, tmp_path):
    lib_dir, lib_id, faces, ids, pid = _file_with_three_questions(client, tmp_path)

    client.post(f"/v1/libraries/{lib_id}/pending/decisions",
                json={"decisions": [{"pending_id": ids["first"], "decision": "rejected"}]})
    # One answer per file and person: the other frames of the same video are not asked.
    assert client.get(f"/v1/libraries/{lib_id}/pending").json() == []

    # A rescan recreates faces rows (new ids) and the sort asks about them again.
    conn = open_library_db(library_data_dir(lib_dir).parent)
    old = conn.execute("SELECT * FROM faces WHERE id = ?", (faces["same"],)).fetchone()
    conn.execute("DELETE FROM faces WHERE id IN (?, ?)", (faces["first"], faces["same"]))
    new_face = conn.execute(
        "INSERT INTO faces (file_id, provider_id, frame_no, bbox_x1, bbox_y1, bbox_x2, bbox_y2, embedding) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (old["file_id"], PROVIDER, 30, old["bbox_x1"], old["bbox_y1"], old["bbox_x2"], old["bbox_y2"], old["embedding"]),
    ).lastrowid
    conn.execute("INSERT INTO pending_matches (face_id, person_id, confidence) VALUES (?, ?, ?)", (new_face, pid, 0.95))
    conn.commit()
    conn.close()

    assert client.get(f"/v1/libraries/{lib_id}/pending").json() == []


def test_ignoring_a_face_settles_the_file_for_that_person(client, tmp_path):
    lib_dir, lib_id, faces, ids, pid = _file_with_three_questions(client, tmp_path)

    assert client.post(f"/v1/libraries/{lib_id}/faces/{faces['first']}/reject").status_code == 200
    # The different-looking face in the same file is not asked for Eve next.
    assert client.get(f"/v1/libraries/{lib_id}/pending").json() == []


def test_ignoring_a_face_ignores_it_in_every_frame_of_the_file(client, tmp_path):
    lib_dir, lib_id, faces, ids, pid = _file_with_three_questions(client, tmp_path)

    res = client.post(f"/v1/libraries/{lib_id}/faces/{faces['first']}/reject").json()
    assert res["face_ids"] == [faces["first"], faces["same"]]
    conn = open_library_db(library_data_dir(lib_dir).parent)
    left = {r["id"] for r in conn.execute("SELECT id FROM faces WHERE file_id = (SELECT file_id FROM faces WHERE id = ?)",
                                          (faces["other"],))}
    regions = conn.execute("SELECT COUNT(*) FROM rejected_face_regions").fetchone()[0]
    conn.close()
    assert faces["other"] in left and faces["same"] not in left  # a different-looking face stays
    assert regions == 2  # both frames stay ignored after a rescan


def test_forget_missing_drops_deleted_files_and_their_questions(client, tmp_path):
    lib_dir, lib_id, faces, ids, pid = _file_with_three_questions(client, tmp_path)
    conn = open_library_db(library_data_dir(lib_dir).parent)
    total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    path = conn.execute("SELECT fi.path FROM faces f JOIN files fi ON fi.id = f.file_id WHERE f.id = ?", (faces["first"],)).fetchone()[0]
    conn.close()
    (lib_dir / path).unlink()

    assert client.post(f"/v1/libraries/{lib_id}/files/forget-missing").json() == {"removed": 1}
    assert client.get(f"/v1/libraries/{lib_id}/pending").json() == []
    conn = open_library_db(library_data_dir(lib_dir).parent)
    assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == total - 1
    conn.close()
    # Idempotent, and every other file is still indexed.
    assert client.post(f"/v1/libraries/{lib_id}/files/forget-missing").json() == {"removed": 0}


def test_forget_missing_keeps_the_index_of_an_unreachable_library(tmp_path):
    from mediamind.store.missing_files import forget_missing

    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _make_library(lib_dir)
    _seed_persons_db(lib_dir)
    conn = open_library_db(library_data_dir(lib_dir).parent)
    total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    assert forget_missing(conn, tmp_path / "unplugged-drive") == 0
    assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == total
    conn.close()
