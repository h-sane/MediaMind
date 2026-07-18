"""API tests for materializing a not-yet-foldered person into a brand-new
sibling folder: preview, commit (with exclude/reassign), and the
already-bound guard. Uses FakeColorProvider so no real model is needed.
"""

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


def _seed_scattered_person(library_root: Path, n_files: int = 4) -> int:
    """n_files loose photos of one person scattered across two folders, no
    pre-existing folder-binding. Returns the person id."""
    (library_root / "Unsorted").mkdir(parents=True, exist_ok=True)
    (library_root / "Other").mkdir(parents=True, exist_ok=True)
    data_dir = library_data_dir(library_root)
    conn = open_db(library_db_path(data_dir))

    file_faces = []
    for i in range(n_files):
        folder = "Unsorted" if i % 2 == 0 else "Other"
        rel = f"{folder}/img{i}.jpg"
        Image.new("RGB", (64, 64), (255, 0, 0)).save(library_root / rel)
        fid = upsert_file(conn, rel, "photo", 100, 0.0, f"h{i}", True)
        emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        file_faces.append(FileFaces(
            file_id=fid, content_hash=f"h{i}", decoded_ok=True,
            faces=[CachedFace(frame_no=0, bbox=(0, 0, 64, 64), embedding=emb)],
        ))
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
    person_id = conn.execute("SELECT id FROM persons WHERE provider_id = ?", (PROVIDER,)).fetchone()["id"]
    conn.close()
    return person_id


def test_preview_lists_all_scattered_photos(tmp_path: Path, client):
    library_root = tmp_path / "lib"
    library_root.mkdir()
    person_id = _seed_scattered_person(library_root, n_files=4)
    lib_id = _add_library(client, library_root)

    res = client.get(f"/v1/libraries/{lib_id}/persons/{person_id}/materialize/preview")
    assert res.status_code == 200
    body = res.json()
    assert body["person_id"] == person_id
    assert len(body["candidates"]) == 4


def test_materialize_creates_sibling_folder_and_names_person(tmp_path: Path, client):
    library_root = tmp_path / "lib"
    library_root.mkdir()
    person_id = _seed_scattered_person(library_root, n_files=4)
    lib_id = _add_library(client, library_root)

    res = client.post(
        f"/v1/libraries/{lib_id}/persons/{person_id}/materialize",
        json={"name": "Dave", "dry_run": False},
    )
    assert res.status_code == 200
    report = res.json()
    assert report["ok"] is True
    assert report["handled"] == 4

    assert (library_root / "Dave").is_dir()
    assert len(list((library_root / "Dave").glob("*.jpg"))) == 4

    persons = client.get(f"/v1/libraries/{lib_id}/persons").json()["persons"]
    assert next(p for p in persons if p["id"] == person_id)["name"] == "Dave"

    bindings = client.get(f"/v1/libraries/{lib_id}/bindings").json()["bindings"]
    assert any(b["folder_rel"] == "Dave" and person_id in b["person_ids"] for b in bindings)


def test_materialize_respects_exclusions_and_reassignments(tmp_path: Path, client):
    library_root = tmp_path / "lib"
    library_root.mkdir()
    person_id = _seed_scattered_person(library_root, n_files=4)
    lib_id = _add_library(client, library_root)

    preview = client.get(f"/v1/libraries/{lib_id}/persons/{person_id}/materialize/preview").json()
    candidates = preview["candidates"]
    excluded_id = candidates[0]["file_id"]
    reassigned_id = candidates[1]["file_id"]

    (library_root / "Elsewhere").mkdir()
    res = client.post(
        f"/v1/libraries/{lib_id}/persons/{person_id}/materialize",
        json={
            "name": "Dave",
            "excluded_file_ids": [excluded_id],
            "reassignments": [{"file_id": reassigned_id, "dest_folder_rel": "Elsewhere"}],
        },
    )
    assert res.status_code == 200
    report = res.json()
    assert report["handled"] == 3  # 4 candidates - 1 excluded = 3 moves (1 reassigned + 2 into Dave/)

    # excluded file stays exactly where it was
    excluded_path = next(c["path"] for c in candidates if c["file_id"] == excluded_id)
    assert (library_root / excluded_path).exists()

    # reassigned file lands in Elsewhere/, not Dave/
    reassigned_name = Path(next(c["path"] for c in candidates if c["file_id"] == reassigned_id)).name
    assert (library_root / "Elsewhere" / reassigned_name).exists()

    # the remaining two land in the new Dave/ folder
    assert len(list((library_root / "Dave").glob("*.jpg"))) == 2


def test_materialize_rejects_already_bound_person(tmp_path: Path, client):
    library_root = tmp_path / "lib"
    library_root.mkdir()
    person_id = _seed_scattered_person(library_root, n_files=4)
    lib_id = _add_library(client, library_root)

    first = client.post(
        f"/v1/libraries/{lib_id}/persons/{person_id}/materialize",
        json={"name": "Dave"},
    )
    assert first.status_code == 200

    again = client.get(f"/v1/libraries/{lib_id}/persons/{person_id}/materialize/preview")
    assert again.status_code == 409
