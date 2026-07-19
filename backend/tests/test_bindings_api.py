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
from mediamind.store.persons import FileFaces, persist_face_scan, rename_person, upsert_file

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


def _seed_person_folder_with_stray(library_root: Path, folder: str, n_files: int = 6) -> int:
    """n_files in `folder`, all one person, plus one more file of that SAME
    person sitting in an unrelated folder. Returns the stray file's db id."""
    (library_root / folder).mkdir(parents=True, exist_ok=True)
    (library_root / "Random").mkdir(parents=True, exist_ok=True)
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

    stray_rel = "Random/other.jpg"
    Image.new("RGB", (64, 64), (255, 0, 0)).save(library_root / stray_rel)
    stray_fid = upsert_file(conn, stray_rel, "photo", 100, 0.0, "hstray", True)
    file_faces.append(FileFaces(
        file_id=stray_fid, content_hash="hstray", decoded_ok=True,
        faces=[CachedFace(frame_no=0, bbox=(0, 0, 64, 64), embedding=np.array([1.0, 0.0, 0.0], dtype=np.float32))],
    ))
    conn.commit()

    persist_face_scan(
        conn,
        scan_id="s1",
        provider_id=PROVIDER,
        file_faces=file_faces,
        labels=np.array([0] * (n_files + 1), dtype=int),
        owners=list(range(n_files + 1)),
        started_at=time.time() - 1,
        finished_at=time.time(),
        params={"provider_id": PROVIDER},
        summary={"files": n_files + 1, "faces": n_files + 1, "people": 1},
    )
    conn.close()
    return stray_fid


def _seed_person_folder_with_outlier_and_stray(library_root: Path, folder: str, n_files: int = 6) -> tuple[int, int]:
    """n_files - 1 of person A plus one outlier of person B in `folder`, and
    one more file of person A sitting outside the folder. All in a single
    scan (persist_face_scan replaces the whole provider's faces per call).
    Returns (outlier_file_id, stray_file_id)."""
    (library_root / folder).mkdir(parents=True, exist_ok=True)
    (library_root / "Random").mkdir(parents=True, exist_ok=True)
    data_dir = library_data_dir(library_root)
    conn = open_db(library_db_path(data_dir))

    file_faces = []
    for i in range(n_files - 1):
        rel = f"{folder}/img{i}.jpg"
        Image.new("RGB", (64, 64), (255, 0, 0)).save(library_root / rel)
        fid = upsert_file(conn, rel, "photo", 100, 0.0, f"h{i}", True)
        file_faces.append(FileFaces(
            file_id=fid, content_hash=f"h{i}", decoded_ok=True,
            faces=[CachedFace(frame_no=0, bbox=(0, 0, 64, 64), embedding=np.array([1.0, 0.0, 0.0], dtype=np.float32))],
        ))

    outlier_rel = f"{folder}/img_outlier.jpg"
    Image.new("RGB", (64, 64), (0, 255, 0)).save(library_root / outlier_rel)
    outlier_fid = upsert_file(conn, outlier_rel, "photo", 100, 0.0, "houtlier", True)
    file_faces.append(FileFaces(
        file_id=outlier_fid, content_hash="houtlier", decoded_ok=True,
        faces=[CachedFace(frame_no=0, bbox=(0, 0, 64, 64), embedding=np.array([0.0, 1.0, 0.0], dtype=np.float32))],
    ))

    stray_rel = "Random/other.jpg"
    Image.new("RGB", (64, 64), (255, 0, 0)).save(library_root / stray_rel)
    stray_fid = upsert_file(conn, stray_rel, "photo", 100, 0.0, "hstray", True)
    file_faces.append(FileFaces(
        file_id=stray_fid, content_hash="hstray", decoded_ok=True,
        faces=[CachedFace(frame_no=0, bbox=(0, 0, 64, 64), embedding=np.array([1.0, 0.0, 0.0], dtype=np.float32))],
    ))
    conn.commit()

    labels = np.array([0] * (n_files - 1) + [1, 0], dtype=int)  # A...A, B(outlier), A(stray)
    persist_face_scan(
        conn,
        scan_id="s1",
        provider_id=PROVIDER,
        file_faces=file_faces,
        labels=labels,
        owners=list(range(len(file_faces))),
        started_at=time.time() - 1,
        finished_at=time.time(),
        params={"provider_id": PROVIDER},
        summary={"files": len(file_faces), "faces": len(file_faces), "people": 2},
    )
    conn.close()
    return outlier_fid, stray_fid


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

    # Organize only ever routes named people (F10) — the outlier's person
    # was never matched to the folder, so name them directly.
    data_dir = library_data_dir(lib_dir)
    conn = open_db(library_db_path(data_dir))
    outlier_pid = conn.execute(
        "SELECT person_id FROM faces WHERE file_id = ?", (outlier_fid,)
    ).fetchone()["person_id"]
    rename_person(conn, outlier_pid, "Bob")
    conn.close()

    # Only the approved outlier routes; the other 5 stay frozen.
    res = client.post(f"/v1/libraries/{lib_id}/organize/preview")
    assert res.json()["planned"] == 1


def test_suggestion_merge_preview_finds_stray_file(client, tmp_path):
    """coverage only measures folder->person; the merge preview must surface
    the reverse direction — this person's photo sitting outside the folder."""
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    stray_fid = _seed_person_folder_with_stray(lib_dir, "Family/Alice")
    lib_id = _add_library(client, lib_dir)

    client.post(f"/v1/libraries/{lib_id}/bindings/refresh")
    sid = client.get(f"/v1/libraries/{lib_id}/bindings/suggestions").json()["suggestions"][0]["id"]

    res = client.get(f"/v1/libraries/{lib_id}/bindings/suggestions/{sid}/merge/preview")
    assert res.status_code == 200
    preview = res.json()
    assert preview["folder_rel"] == "Family/Alice"
    assert preview["leaf_name"] == "Alice"
    assert preview["move_count"] == 1
    assert preview["moves"][0]["file_id"] == stray_fid
    assert preview["moves"][0]["source_rel"] == "Random/other.jpg"
    assert preview["moves"][0]["dest_folder_rel"] == "Family/Alice"
    assert preview["moves"][0]["kind"] == "photo"


def test_suggestion_merge_moves_files_and_renames_person(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    stray_fid = _seed_person_folder_with_stray(lib_dir, "Family/Alice")
    lib_id = _add_library(client, lib_dir)

    client.post(f"/v1/libraries/{lib_id}/bindings/refresh")
    sid = client.get(f"/v1/libraries/{lib_id}/bindings/suggestions").json()["suggestions"][0]["id"]

    res = client.post(f"/v1/libraries/{lib_id}/bindings/suggestions/{sid}/merge", json={})
    assert res.status_code == 200
    report = res.json()
    assert report["planned"] == 1
    assert report["handled"] == 1
    assert report["ok"] is True

    assert not (lib_dir / "Random" / "other.jpg").exists()
    assert (lib_dir / "Family" / "Alice" / "other.jpg").exists()

    # Suggestion is gone (accepted) and the binding now owns a renamed person.
    res = client.get(f"/v1/libraries/{lib_id}/bindings/suggestions")
    assert res.json()["suggestions"] == []

    res = client.get(f"/v1/libraries/{lib_id}/bindings")
    binding = res.json()["bindings"][0]
    assert binding["person_names"] == ["Alice"]

    res = client.get(f"/v1/libraries/{lib_id}/persons")
    person = res.json()["persons"][0]
    assert person["name"] == "Alice"

    # files.path was rewritten for the moved file.
    res = client.get(f"/v1/libraries/{lib_id}/persons/{person['id']}/media")
    paths = {m["path"] for m in res.json()}
    assert "Family/Alice/other.jpg" in paths
    assert stray_fid in {m["file_id"] for m in res.json()}


def test_suggestion_merge_respects_manual_rename(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _seed_person_folder_with_stray(lib_dir, "Family/Alice")
    lib_id = _add_library(client, lib_dir)

    client.post(f"/v1/libraries/{lib_id}/bindings/refresh")
    sid_res = client.get(f"/v1/libraries/{lib_id}/bindings/suggestions").json()["suggestions"][0]
    sid = sid_res["id"]
    person_id = sid_res["person_ids"][0]

    client.patch(f"/v1/libraries/{lib_id}/persons/{person_id}", json={"name": "Not Alice"})

    res = client.post(f"/v1/libraries/{lib_id}/bindings/suggestions/{sid}/merge", json={})
    assert res.status_code == 200

    res = client.get(f"/v1/libraries/{lib_id}/persons")
    assert res.json()["persons"][0]["name"] == "Not Alice"


def test_suggestion_merge_dry_run_changes_nothing(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    _seed_person_folder_with_stray(lib_dir, "Family/Alice")
    lib_id = _add_library(client, lib_dir)

    client.post(f"/v1/libraries/{lib_id}/bindings/refresh")
    sid = client.get(f"/v1/libraries/{lib_id}/bindings/suggestions").json()["suggestions"][0]["id"]

    res = client.post(f"/v1/libraries/{lib_id}/bindings/suggestions/{sid}/merge", json={"dry_run": True})
    assert res.status_code == 200
    assert res.json()["dry_run"] is True

    assert (lib_dir / "Random" / "other.jpg").exists()
    assert not (lib_dir / "Family" / "Alice" / "other.jpg").exists()

    # Suggestion is still pending — dry-run must not accept it.
    res = client.get(f"/v1/libraries/{lib_id}/bindings/suggestions")
    assert len(res.json()["suggestions"]) == 1


def test_suggestion_merge_excludes_and_reassigns(client, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    outlier_fid, stray_fid = _seed_person_folder_with_outlier_and_stray(lib_dir, "Family/Alice")
    lib_id = _add_library(client, lib_dir)
    (lib_dir / "Elsewhere").mkdir()

    client.post(f"/v1/libraries/{lib_id}/bindings/refresh")
    sid = client.get(f"/v1/libraries/{lib_id}/bindings/suggestions").json()["suggestions"][0]["id"]

    preview = client.get(f"/v1/libraries/{lib_id}/bindings/suggestions/{sid}/merge/preview").json()
    assert preview["move_count"] == 1  # only the stray file; the outlier belongs to a different person

    res = client.post(
        f"/v1/libraries/{lib_id}/bindings/suggestions/{sid}/merge",
        json={
            "excluded_file_ids": [stray_fid],
            "reassignments": [{"file_id": outlier_fid, "dest_folder_rel": "Elsewhere"}],
        },
    )
    assert res.status_code == 200
    report = res.json()
    assert report["planned"] == 1  # the reassignment, not the excluded stray move
    assert report["ok"] is True

    # Stray file was excluded from the move -> stays put.
    assert (lib_dir / "Random" / "other.jpg").exists()
    # Outlier was reassigned to an arbitrary folder, not the bound folder.
    assert (lib_dir / "Elsewhere" / "img_outlier.jpg").exists()

    # "Not this person" was recorded durably (not just skipped for this one
    # merge) for both the excluded stray and the redirected outlier.
    data_dir = library_data_dir(lib_dir)
    conn = open_db(library_db_path(data_dir))
    rejected_pids = {
        r["person_id"]
        for r in conn.execute(
            "SELECT person_id FROM rejected_person_files WHERE content_hash IN ('hstray', 'houtlier')"
        )
    }
    conn.close()
    assert len(rejected_pids) == 1  # both rows recorded, both against Alice

    # And a later generic Organize run must not sweep the excluded stray back
    # into Alice's bound folder (the routing-gap fix's other half).
    preview = client.post(f"/v1/libraries/{lib_id}/organize/preview").json()
    dests = {m["source_rel"]: m["dest_folder_rel"] for m in preview["moves"]}
    assert "Random/other.jpg" not in dests
