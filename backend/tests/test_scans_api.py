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


def test_unknown_library_returns_404(client):
    res = client.post("/v1/libraries/nope/scans", json={"type": "dedupe"})
    assert res.status_code == 404


def test_unknown_scan_returns_404(client, tmp_path):
    lib_dir = tmp_path / "photos"
    lib_dir.mkdir()
    lib_id = _add_library(client, lib_dir)
    assert client.get(f"/v1/libraries/{lib_id}/scans/nope").status_code == 404
