"""Duplicates inside the people flow: a people scan that finds duplicates first, "not
duplicates" for one group, and removed copies leaving the index."""

from __future__ import annotations

import shutil
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
from mediamind.store.db import open_library_db

PROVIDER = "fake-color"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    entry = CatalogEntry(
        id=PROVIDER, name="Fake Color", description="Test only",
        license=LicenseInfo(name="MIT", url="", commercial_use=True, summary=""),
        downloads=[], archive="none", extract_subdir="", embedding_dim=3, cluster_eps=0.5, kind="fake",
    )
    pm = ProviderManager(tmp_path / "models", catalog=[entry])
    with TestClient(create_app(provider_manager=pm)) as c:
        yield c


def _wait(client, lib_id, job_id, timeout=60.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        snap = client.get(f"/v1/libraries/{lib_id}/scans/{job_id}").json()
        if snap["state"] in ("succeeded", "failed", "cancelled"):
            return snap
        assert time.monotonic() < deadline, snap
        time.sleep(0.05)


def _library_with_two_copy_pairs(root: Path) -> None:
    rng = np.random.default_rng(7)
    for name in ("a", "b"):
        Image.fromarray(rng.integers(0, 256, (96, 96, 3), dtype=np.uint8)).save(root / f"{name}.png")
        shutil.copy(root / f"{name}.png", root / f"{name}_copy.png")


def _scan(client, lib_id, body) -> dict:
    return _wait(client, lib_id, client.post(f"/v1/libraries/{lib_id}/scans", json=body).json()["id"])


def test_people_scan_finds_duplicates_first(client, tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    _library_with_two_copy_pairs(lib)
    lib_id = client.post("/v1/libraries", json={"path": str(lib)}).json()["id"]

    snap = _scan(client, lib_id, {"type": "faces", "with_duplicates": True})
    assert snap["state"] == "succeeded", snap["error"]
    assert snap["result"]["duplicates"]["groups"] == 2
    assert len(client.get(f"/v1/libraries/{lib_id}/duplicates").json()["groups"]) == 2
    # The people part ran too and kept its own scan record.
    conn = open_library_db(library_data_dir(lib).parent)
    types = sorted(r["type"] for r in conn.execute("SELECT type FROM scans"))
    conn.close()
    assert types == ["dedupe", "faces"]


def test_not_duplicates_hides_one_group_and_survives_rescan(client, tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    _library_with_two_copy_pairs(lib)
    lib_id = client.post("/v1/libraries", json={"path": str(lib)}).json()["id"]
    _scan(client, lib_id, {"type": "dedupe"})

    groups = client.get(f"/v1/libraries/{lib_id}/duplicates").json()["groups"]
    res = client.post(f"/v1/libraries/{lib_id}/duplicates/groups/{groups[0]['id']}/dismiss")
    assert res.status_code == 200
    assert len(client.get(f"/v1/libraries/{lib_id}/duplicates").json()["groups"]) == 1

    _scan(client, lib_id, {"type": "dedupe"})
    assert len(client.get(f"/v1/libraries/{lib_id}/duplicates").json()["groups"]) == 1
    assert client.post(f"/v1/libraries/{lib_id}/duplicates/groups/999999/dismiss").status_code == 404


def test_removed_copy_leaves_the_index(client, tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    _library_with_two_copy_pairs(lib)
    lib_id = client.post("/v1/libraries", json={"path": str(lib)}).json()["id"]
    _scan(client, lib_id, {"type": "faces", "with_duplicates": True})

    group = client.get(f"/v1/libraries/{lib_id}/duplicates").json()["groups"][0]
    keep, drop = group["files"][0], group["files"][1]
    client.post(f"/v1/libraries/{lib_id}/duplicates/resolutions", json={"resolutions": [
        {"file_id": keep["id"], "action": "keep"}, {"file_id": drop["id"], "action": "trash"}]})
    report = client.post(f"/v1/libraries/{lib_id}/duplicates/execute",
                         json={"dry_run": False, "expected_trash_count": 1, "permanent": True}).json()
    assert report["ok"], report

    assert not (lib / drop["path"]).exists() and (lib / keep["path"]).exists()
    conn = open_library_db(library_data_dir(lib).parent)
    paths = {r["path"] for r in conn.execute("SELECT path FROM files")}
    faces_of_dropped = conn.execute(
        "SELECT count(*) FROM faces f JOIN files fi ON fi.id = f.file_id WHERE fi.path = ?", (drop["path"],)
    ).fetchone()[0]
    conn.close()
    assert drop["path"] not in paths and keep["path"] in paths
    assert faces_of_dropped == 0
