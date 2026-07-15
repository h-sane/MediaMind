"""API tests for Phase B folder-binding routes: refresh, suggestions, accept/dismiss,
release, outliers. Uses FakeColorProvider so no real model is needed.
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


def _seed_person_folder(library_root: Path, folder: str, n_files: int = 6) -> None:
    """Create n_files real jpgs under `folder`, all one person's face."""
    (library_root / folder).mkdir(parents=True, exist_ok=True)
    data_dir = library_data_dir(library_root)
    conn = open_db(library_db_path(data_dir))

    file_faces = []
    for i in range(n_files):
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
    conn.close()


def _seed_person_folder_with_outlier(library_root: Path, folder: str, n_files: int = 6) -> int:
    """n_files - 1 real jpgs of one person plus one outlier jpg of a second
    person, all under `folder`. Returns the outlier file's db id."""
    (library_root / folder).mkdir(parents=True, exist_ok=True)
    data_dir = library_data_dir(library_root)
    conn = open_db(library_db_path(data_dir))

    file_faces = []
    for i in range(n_files):
        rel = f"{folder}/img{i}.jpg"
        color = (255, 0, 0) if i < n_files - 1 else (0, 255, 0)
        Image.new("RGB", (64, 64), color).save(library_root / rel)
        fid = upsert_file(conn, rel, "photo", 100, 0.0, f"h{i}", True)
        emb = np.array([1.0, 0.0, 0.0], dtype=np.float32) if i < n_files - 1 else np.array(
            [0.0, 1.0, 0.0], dtype=np.float32
        )
        file_faces.append(FileFaces(
            file_id=fid, content_hash=f"h{i}", decoded_ok=True,
            faces=[CachedFace(frame_no=0, bbox=(0, 0, 64, 64), embedding=emb)],
        ))
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
    conn.close()
    return file_faces[-1].file_id


def test_bindings_requires_face_scan(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    lib_id = _add_library(client, lib_dir)

    res = client.post(f"/v1/libraries/{lib_id}/bindings/refresh")
    assert res.status_code == 422


def test_bindings_full_lifecycle(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _seed_person_folder(lib_dir, "Family/Alice")
    lib_id = _add_library(client, lib_dir)

    # refresh -> one suggestion
    res = client.post(f"/v1/libraries/{lib_id}/bindings/refresh")
    assert res.status_code == 200
    assert res.json()["suggested"] == 1

    res = client.get(f"/v1/libraries/{lib_id}/bindings/suggestions")
    assert res.status_code == 200
    suggestions = res.json()["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["folder_rel"] == "Family/Alice"
    assert suggestions[0]["kind"] == "person"
    sid = suggestions[0]["id"]

    # accept -> binding created, person auto-named "Alice"
    res = client.post(f"/v1/libraries/{lib_id}/bindings/suggestions/{sid}/accept")
    assert res.status_code == 200
    binding = res.json()
    assert binding["folder_rel"] == "Family/Alice"
    assert binding["person_names"] == ["Alice"]
    bid = binding["id"]

    # organize preview must now exclude Family/Alice's files
    res = client.post(f"/v1/libraries/{lib_id}/organize/preview")
    assert res.status_code == 200
    assert res.json()["planned"] == 0

    # release -> folder unfrozen
    res = client.post(f"/v1/libraries/{lib_id}/bindings/{bid}/release")
    assert res.status_code == 200
    assert res.json()["ok"] is True

    res = client.get(f"/v1/libraries/{lib_id}/bindings")
    assert res.json()["bindings"] == []

    res = client.post(f"/v1/libraries/{lib_id}/organize/preview")
    assert res.json()["planned"] == 6


def test_bindings_dismiss(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _seed_person_folder(lib_dir, "Family/Bob")
    lib_id = _add_library(client, lib_dir)

    client.post(f"/v1/libraries/{lib_id}/bindings/refresh")
    sid = client.get(f"/v1/libraries/{lib_id}/bindings/suggestions").json()["suggestions"][0]["id"]

    res = client.post(f"/v1/libraries/{lib_id}/bindings/suggestions/{sid}/dismiss")
    assert res.status_code == 200
    assert res.json()["ok"] is True

    res = client.get(f"/v1/libraries/{lib_id}/bindings/suggestions")
    assert res.json()["suggestions"] == []


def test_bindings_outlier_review_and_approval(client, tmp_path):
    """The outlier-review flow this session added: an accepted binding
    reports its detected-but-unapproved outlier, approving it via the
    outliers route flips it to accepted, and only then does the organize
    preview route that one file while the rest of the folder stays frozen."""
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    outlier_fid = _seed_person_folder_with_outlier(lib_dir, "Family/Alice")
    lib_id = _add_library(client, lib_dir)

    client.post(f"/v1/libraries/{lib_id}/bindings/refresh")
    sid = client.get(f"/v1/libraries/{lib_id}/bindings/suggestions").json()["suggestions"][0]["id"]

    res = client.post(f"/v1/libraries/{lib_id}/bindings/suggestions/{sid}/accept")
    binding = res.json()
    bid = binding["id"]
    assert len(binding["outliers"]) == 1
    assert binding["outliers"][0]["file_id"] == outlier_fid
    assert binding["outliers"][0]["accepted"] is False

    # Frozen: nothing in the bound folder routes yet, including the outlier.
    res = client.post(f"/v1/libraries/{lib_id}/organize/preview")
    assert res.json()["planned"] == 0

    res = client.post(
        f"/v1/libraries/{lib_id}/bindings/{bid}/outliers", json={"file_ids": [outlier_fid]}
    )
    assert res.status_code == 200
    assert res.json()["outliers"][0]["accepted"] is True

    res = client.get(f"/v1/libraries/{lib_id}/bindings")
    assert res.json()["bindings"][0]["outliers"][0]["accepted"] is True

    # Only the approved outlier routes; the other 5 stay frozen.
    res = client.post(f"/v1/libraries/{lib_id}/organize/preview")
    assert res.json()["planned"] == 1
