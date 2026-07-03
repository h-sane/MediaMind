"""API tests for multi-person review routes and route_choices."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mediamind.api.app import create_app
from mediamind.config import library_data_dir
from mediamind.providers.catalog import CatalogEntry, LicenseInfo
from mediamind.providers.manager import ProviderManager
from mediamind.store.db import library_db_path, open_db
from mediamind.store.embeddings import CachedFace
from mediamind.store.persons import FileFaces, persist_face_scan, upsert_file

PROVIDER = "fake-color"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_pm(tmp_path: Path):
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
    return ProviderManager(tmp_path / "models", catalog=[catalog_entry])


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_pm):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app(provider_manager=fake_pm)) as c:
        yield c


def _add_library(client, path: Path) -> str:
    res = client.post("/v1/libraries", json={"path": str(path)})
    assert res.status_code == 201
    return res.json()["id"]


def _seed_multi_person_db(library_root: Path) -> tuple[int, int, int]:
    """
    Seed a DB with one file that contains faces from two distinct persons.
    Returns (file_id, person1_id, person2_id).
    """
    Image.new("RGB", (64, 64), (255, 0, 0)).save(library_root / "group.jpg")
    Image.new("RGB", (64, 64), (0, 0, 255)).save(library_root / "solo.jpg")

    data_dir = library_data_dir(library_root)
    conn = open_db(library_db_path(data_dir))

    emb_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    emb_b = np.array([0.0, 0.0, 1.0], dtype=np.float32)

    fid_group = upsert_file(conn, "group.jpg", "photo", 100, 0.0, "h_group", True)
    fid_solo = upsert_file(conn, "solo.jpg", "photo", 100, 0.0, "h_solo", True)
    conn.commit()

    # group.jpg has two face detections (one per person)
    ff = [
        FileFaces(
            file_id=fid_group,
            content_hash="h_group",
            decoded_ok=True,
            faces=[
                CachedFace(frame_no=0, bbox=(0, 0, 30, 64), embedding=emb_a),
                CachedFace(frame_no=0, bbox=(30, 0, 64, 64), embedding=emb_b),
            ],
        ),
        FileFaces(
            file_id=fid_solo,
            content_hash="h_solo",
            decoded_ok=True,
            faces=[CachedFace(frame_no=0, bbox=(0, 0, 64, 64), embedding=emb_a)],
        ),
    ]
    # label 0 → person A, label 1 → person B; owner=0 for both group faces
    persist_face_scan(
        conn,
        scan_id="s1",
        provider_id=PROVIDER,
        file_faces=ff,
        labels=np.array([0, 1, 0], dtype=int),
        owners=[0, 0, 1],  # 2 faces from group.jpg (owners 0,0), 1 from solo.jpg (owner 1)
        started_at=time.time() - 1,
        finished_at=time.time(),
        params={"provider_id": PROVIDER},
        summary={"files": 2, "faces": 3, "people": 2},
    )

    person_ids = [
        int(r["id"])
        for r in conn.execute(
            "SELECT id FROM persons WHERE provider_id = ? ORDER BY id",
            (PROVIDER,),
        ).fetchall()
    ]
    conn.close()

    return fid_group, person_ids[0], person_ids[1]


# ---------------------------------------------------------------------------
# GET /multi-person
# ---------------------------------------------------------------------------

def test_multi_person_requires_face_scan(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    lib_id = _add_library(client, lib_dir)

    res = client.get(f"/v1/libraries/{lib_id}/multi-person")
    assert res.status_code == 422


def test_multi_person_empty_when_no_ambiguous(client, tmp_path):
    """Library with only single-person files → empty list."""
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    Image.new("RGB", (64, 64)).save(lib_dir / "a.jpg")

    data_dir = library_data_dir(lib_dir)
    conn = open_db(library_db_path(data_dir))
    fid = upsert_file(conn, "a.jpg", "photo", 100, 0.0, "ha", True)
    conn.commit()
    emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    ff = [FileFaces(file_id=fid, content_hash="ha", decoded_ok=True,
                    faces=[CachedFace(frame_no=0, bbox=(0, 0, 64, 64), embedding=emb)])]
    persist_face_scan(conn, scan_id="s1", provider_id=PROVIDER, file_faces=ff,
                      labels=np.array([0], dtype=int), owners=[0],
                      started_at=time.time() - 1, finished_at=time.time(),
                      params={"provider_id": PROVIDER}, summary={})
    conn.close()

    lib_id = _add_library(client, lib_dir)
    res = client.get(f"/v1/libraries/{lib_id}/multi-person")
    assert res.status_code == 200
    assert res.json() == []


def test_multi_person_lists_ambiguous_files(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    fid_group, pid_a, pid_b = _seed_multi_person_db(lib_dir)

    lib_id = _add_library(client, lib_dir)
    res = client.get(f"/v1/libraries/{lib_id}/multi-person")
    assert res.status_code == 200
    items = res.json()

    assert len(items) == 1  # only group.jpg has 2 persons; solo.jpg has 1
    item = items[0]
    assert item["file_id"] == fid_group
    assert item["path"] == "group.jpg"
    assert item["kind"] == "photo"
    assert item["current_choice"] is None
    assert len(item["persons"]) == 2
    person_ids_returned = {p["person_id"] for p in item["persons"]}
    assert person_ids_returned == {pid_a, pid_b}
    # Each person option has face_count and sample_face_id
    for p in item["persons"]:
        assert p["face_count"] >= 1
        assert p["sample_face_id"] > 0


def test_multi_person_shows_current_choice(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    fid_group, pid_a, _pid_b = _seed_multi_person_db(lib_dir)
    lib_id = _add_library(client, lib_dir)

    # Set a route choice
    res = client.post(
        f"/v1/libraries/{lib_id}/route-choices",
        json={"choices": [{"file_id": fid_group, "person_id": pid_a}]},
    )
    assert res.status_code == 200
    assert res.json()["updated"] == 1

    # Now multi-person list should reflect the choice
    res = client.get(f"/v1/libraries/{lib_id}/multi-person")
    assert res.status_code == 200
    items = res.json()
    assert items[0]["current_choice"] == pid_a


# ---------------------------------------------------------------------------
# POST /route-choices
# ---------------------------------------------------------------------------

def test_route_choices_empty_body(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    lib_id = _add_library(client, lib_dir)

    res = client.post(f"/v1/libraries/{lib_id}/route-choices", json={"choices": []})
    assert res.status_code == 200
    assert res.json()["updated"] == 0


def test_route_choices_upsert(client, tmp_path):
    """Setting a choice twice updates the person_id, not duplicates the row."""
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    fid_group, pid_a, pid_b = _seed_multi_person_db(lib_dir)
    lib_id = _add_library(client, lib_dir)

    # Set to person A
    client.post(
        f"/v1/libraries/{lib_id}/route-choices",
        json={"choices": [{"file_id": fid_group, "person_id": pid_a}]},
    )
    # Update to person B
    res = client.post(
        f"/v1/libraries/{lib_id}/route-choices",
        json={"choices": [{"file_id": fid_group, "person_id": pid_b}]},
    )
    assert res.status_code == 200

    items = client.get(f"/v1/libraries/{lib_id}/multi-person").json()
    assert items[0]["current_choice"] == pid_b


def test_route_choices_clear(client, tmp_path):
    """person_id=0 clears the choice."""
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    fid_group, pid_a, _pid_b = _seed_multi_person_db(lib_dir)
    lib_id = _add_library(client, lib_dir)

    client.post(
        f"/v1/libraries/{lib_id}/route-choices",
        json={"choices": [{"file_id": fid_group, "person_id": pid_a}]},
    )
    # Clear
    client.post(
        f"/v1/libraries/{lib_id}/route-choices",
        json={"choices": [{"file_id": fid_group, "person_id": 0}]},
    )

    items = client.get(f"/v1/libraries/{lib_id}/multi-person").json()
    assert items[0]["current_choice"] is None


# ---------------------------------------------------------------------------
# multi_person_count in /persons
# ---------------------------------------------------------------------------

def test_persons_includes_multi_person_count(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _seed_multi_person_db(lib_dir)

    lib_id = _add_library(client, lib_dir)
    res = client.get(f"/v1/libraries/{lib_id}/persons")
    assert res.status_code == 200
    body = res.json()
    assert "multi_person_count" in body
    assert body["multi_person_count"] == 1  # group.jpg is the one ambiguous file
