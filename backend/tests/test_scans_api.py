"""Tests for scan job API routes (B4)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mediamind.api.app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app()) as c:
        yield c


def _make_dup_library(root: Path) -> tuple[Path, Path]:
    """Two identical images — will produce exactly one duplicate group."""
    a = root / "a.jpg"
    b = root / "b.jpg"
    img = Image.new("RGB", (64, 64), (100, 150, 200))
    img.save(a)
    b.write_bytes(a.read_bytes())
    return a, b


def _add_library(client, path: Path) -> str:
    res = client.post("/v1/libraries", json={"path": str(path)})
    assert res.status_code == 201
    return res.json()["id"]


def _wait_job(client, lib_id, job_id, timeout=30.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        snap = client.get(f"/v1/libraries/{lib_id}/scans/{job_id}").json()
        if snap["state"] in ("succeeded", "failed", "cancelled"):
            return snap
        if time.monotonic() > deadline:
            raise TimeoutError(f"Job {job_id} stuck in {snap['state']}")
        time.sleep(0.05)


# ---------------------------------------------------------------------------
# Start / status / cancel
# ---------------------------------------------------------------------------

def test_start_dedupe_scan_returns_202(client, tmp_path):
    lib_dir = tmp_path / "photos"
    lib_dir.mkdir()
    _make_dup_library(lib_dir)
    lib_id = _add_library(client, lib_dir)

    res = client.post(f"/v1/libraries/{lib_id}/scans", json={"type": "dedupe"})
    assert res.status_code == 202
    snap = res.json()
    assert snap["library_id"] == lib_id
    assert snap["type"] == "dedupe"
    assert snap["state"] in ("queued", "running", "succeeded")


def test_scan_reaches_succeeded(client, tmp_path):
    lib_dir = tmp_path / "photos"
    lib_dir.mkdir()
    _make_dup_library(lib_dir)
    lib_id = _add_library(client, lib_dir)

    res = client.post(f"/v1/libraries/{lib_id}/scans", json={"type": "dedupe"})
    snap = _wait_job(client, lib_id, res.json()["id"])
    assert snap["state"] == "succeeded"
    assert snap["result"]["groups"] == 1


def test_get_scan_status(client, tmp_path):
    lib_dir = tmp_path / "photos"
    lib_dir.mkdir()
    _make_dup_library(lib_dir)
    lib_id = _add_library(client, lib_dir)

    job_id = client.post(f"/v1/libraries/{lib_id}/scans", json={"type": "dedupe"}).json()["id"]
    _wait_job(client, lib_id, job_id)

    snap = client.get(f"/v1/libraries/{lib_id}/scans/{job_id}").json()
    assert snap["id"] == job_id
    assert snap["state"] == "succeeded"


def test_scan_results_persisted_to_db(client, tmp_path):
    lib_dir = tmp_path / "photos"
    lib_dir.mkdir()
    _make_dup_library(lib_dir)
    lib_id = _add_library(client, lib_dir)

    job_id = client.post(f"/v1/libraries/{lib_id}/scans", json={"type": "dedupe"}).json()["id"]
    _wait_job(client, lib_id, job_id)

    dups = client.get(f"/v1/libraries/{lib_id}/duplicates")
    assert dups.status_code == 200
    body = dups.json()
    assert body["scan_id"] == job_id
    assert body["summary"]["groups"] == 1


def test_409_when_scan_already_running(client, tmp_path, monkeypatch):
    lib_dir = tmp_path / "photos"
    lib_dir.mkdir()
    _make_dup_library(lib_dir)
    lib_id = _add_library(client, lib_dir)

    import threading
    block = threading.Event()

    original_find = None

    def slow_find(*args, **kwargs):
        block.wait(timeout=5)
        return original_find(*args, **kwargs)

    import mediamind.api.routes.scans as scans_module
    import mediamind.core.dedupe as dedupe_module
    original_find = dedupe_module.find_duplicates
    monkeypatch.setattr(scans_module, "find_duplicates", slow_find)

    res1 = client.post(f"/v1/libraries/{lib_id}/scans", json={"type": "dedupe"})
    assert res1.status_code == 202

    import time; time.sleep(0.05)  # let the worker thread start

    res2 = client.post(f"/v1/libraries/{lib_id}/scans", json={"type": "dedupe"})
    assert res2.status_code == 409
    block.set()


def test_cancel_scan(client, tmp_path, monkeypatch):
    lib_dir = tmp_path / "photos"
    lib_dir.mkdir()
    _make_dup_library(lib_dir)
    lib_id = _add_library(client, lib_dir)

    import threading
    started = threading.Event()
    block = threading.Event()

    def slow_find(files, **kwargs):
        started.set()
        block.wait(timeout=5)
        should_cancel = kwargs.get("should_cancel")
        if should_cancel and should_cancel():
            return []
        return []

    import mediamind.api.routes.scans as scans_module
    monkeypatch.setattr(scans_module, "find_duplicates", slow_find)

    res = client.post(f"/v1/libraries/{lib_id}/scans", json={"type": "dedupe"})
    job_id = res.json()["id"]
    started.wait(timeout=5)

    cancel = client.delete(f"/v1/libraries/{lib_id}/scans/{job_id}")
    assert cancel.status_code == 202
    block.set()

    snap = _wait_job(client, lib_id, job_id)
    assert snap["state"] == "cancelled"


# ---------------------------------------------------------------------------
# Concurrent scan types (dedupe + faces are independent; same type still 409s)
# ---------------------------------------------------------------------------

@pytest.fixture
def faces_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Client whose app has an installed (fake) face provider."""
    from mediamind.providers.catalog import CatalogEntry, LicenseInfo
    from mediamind.providers.manager import ProviderManager

    entry = CatalogEntry(
        id="fake-color",
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
    pm = ProviderManager(tmp_path / "models", catalog=[entry])
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app(provider_manager=pm)) as c:
        yield c


def test_faces_scan_starts_while_dedupe_running(faces_client, tmp_path, monkeypatch):
    """Different-type scans may run concurrently on one library; same type may not."""
    client = faces_client
    lib_dir = tmp_path / "photos"
    lib_dir.mkdir()
    _make_dup_library(lib_dir)
    lib_id = _add_library(client, lib_dir)

    import threading
    started = threading.Event()
    block = threading.Event()

    import mediamind.api.routes.scans as scans_module
    import mediamind.core.dedupe as dedupe_module
    original_find = dedupe_module.find_duplicates

    def slow_find(*args, **kwargs):
        started.set()
        block.wait(timeout=10)
        return original_find(*args, **kwargs)

    monkeypatch.setattr(scans_module, "find_duplicates", slow_find)

    res_dedupe = client.post(f"/v1/libraries/{lib_id}/scans", json={"type": "dedupe"})
    assert res_dedupe.status_code == 202
    assert started.wait(timeout=5)

    # Different type: allowed while the dedupe scan is mid-run.
    res_faces = client.post(f"/v1/libraries/{lib_id}/scans", json={"type": "faces"})
    assert res_faces.status_code == 202

    # Same type: still refused.
    res_dedupe2 = client.post(f"/v1/libraries/{lib_id}/scans", json={"type": "dedupe"})
    assert res_dedupe2.status_code == 409

    # The faces scan completes (writing the shared index.db) while the dedupe
    # scan is still running — true temporal overlap, both must succeed.
    faces_snap = _wait_job(client, lib_id, res_faces.json()["id"])
    assert faces_snap["state"] == "succeeded"
    dedupe_mid = client.get(
        f"/v1/libraries/{lib_id}/scans/{res_dedupe.json()['id']}"
    ).json()
    assert dedupe_mid["state"] == "running"

    block.set()
    dedupe_snap = _wait_job(client, lib_id, res_dedupe.json()["id"])
    assert dedupe_snap["state"] == "succeeded"
    assert dedupe_snap["result"]["groups"] == 1


def test_dedupe_scan_starts_while_faces_running(faces_client, tmp_path, monkeypatch):
    """The reverse direction: dedupe is allowed mid-faces-scan; second faces scan 409s."""
    client = faces_client
    lib_dir = tmp_path / "photos"
    lib_dir.mkdir()
    _make_dup_library(lib_dir)
    lib_id = _add_library(client, lib_dir)

    import threading
    started = threading.Event()
    block = threading.Event()

    import mediamind.core.faces.scan as face_scan_module
    original_scan = face_scan_module.scan_folder

    def slow_scan(root, **kwargs):
        started.set()
        block.wait(timeout=10)
        return original_scan(root, **kwargs)

    monkeypatch.setattr(face_scan_module, "scan_folder", slow_scan)

    res_faces = client.post(f"/v1/libraries/{lib_id}/scans", json={"type": "faces"})
    assert res_faces.status_code == 202
    assert started.wait(timeout=5)

    # Same type: refused while a faces scan is active.
    res_faces2 = client.post(f"/v1/libraries/{lib_id}/scans", json={"type": "faces"})
    assert res_faces2.status_code == 409

    # Different type: allowed; runs to completion against the same index.db
    # while the faces job is still active.
    res_dedupe = client.post(f"/v1/libraries/{lib_id}/scans", json={"type": "dedupe"})
    assert res_dedupe.status_code == 202
    dedupe_snap = _wait_job(client, lib_id, res_dedupe.json()["id"])
    assert dedupe_snap["state"] == "succeeded"
    assert dedupe_snap["result"]["groups"] == 1

    block.set()
    faces_snap = _wait_job(client, lib_id, res_faces.json()["id"])
    assert faces_snap["state"] == "succeeded"


def test_unknown_library_returns_404(client):
    res = client.post("/v1/libraries/nope/scans", json={"type": "dedupe"})
    assert res.status_code == 404


def test_unknown_scan_returns_404(client, tmp_path):
    lib_dir = tmp_path / "photos"
    lib_dir.mkdir()
    lib_id = _add_library(client, lib_dir)
    assert client.get(f"/v1/libraries/{lib_id}/scans/nope").status_code == 404
