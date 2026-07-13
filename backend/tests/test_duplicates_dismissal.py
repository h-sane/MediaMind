"""Tests for cross-scan duplicate-group dismissals ("Save configuration").

Core invariant: a group the user has reviewed and confirmed must not
resurface on a rescan of the same folder unless its membership actually
changes (a new duplicate file joins it) — see core.dedupe.group_signature and
the dedupe runner in routes/scans.py.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mediamind.api.app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app()) as c:
        yield c


def _wait_job(client, lib_id, job_id, timeout=30.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        snap = client.get(f"/v1/libraries/{lib_id}/scans/{job_id}").json()
        if snap["state"] in ("succeeded", "failed", "cancelled"):
            return snap
        if time.monotonic() > deadline:
            raise TimeoutError(f"Job {job_id} stuck in {snap['state']}")
        time.sleep(0.05)


def _noise_image(path: Path, seed: int, size: tuple[int, int] = (128, 128)) -> Path:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
    Image.fromarray(arr).save(path)
    return path


def _run_scan(client, lib_id) -> dict:
    job_id = client.post(f"/v1/libraries/{lib_id}/scans", json={"type": "dedupe"}).json()["id"]
    return _wait_job(client, lib_id, job_id)


def test_confirmed_group_does_not_reappear_until_membership_changes(client, tmp_path):
    lib_dir = tmp_path / "photos"
    lib_dir.mkdir()
    original = _noise_image(lib_dir / "photo.png", seed=1)
    # Unique-size near duplicate — the exact shape that produced the sentinel-
    # hash instability bug caught in review, so this test doubles as coverage
    # for the fix, not just the dismissal feature.
    with Image.open(original) as im:
        im.resize((96, 96)).save(lib_dir / "photo_small.jpg", quality=90)

    lib_id = client.post("/v1/libraries", json={"path": str(lib_dir)}).json()["id"]

    snap = _run_scan(client, lib_id)
    assert snap["state"] == "succeeded", snap.get("error")
    assert snap["result"]["groups"] == 1

    dups = client.get(f"/v1/libraries/{lib_id}/duplicates").json()
    assert len(dups["groups"]) == 1

    # Review complete, nothing marked for deletion — a false-positive visual
    # match the user wants to keep exactly as-is. Confirm it.
    res = client.post(f"/v1/libraries/{lib_id}/duplicates/confirm")
    assert res.status_code == 200
    body = res.json()
    assert body["confirmed_groups"] == 1
    assert body["skipped_pending"] == 0

    # Gone from the live view immediately, no rescan needed.
    dups = client.get(f"/v1/libraries/{lib_id}/duplicates").json()
    assert dups["groups"] == []

    # Rescan with nothing changed — must stay dismissed.
    snap2 = _run_scan(client, lib_id)
    assert snap2["result"]["groups"] == 0
    dups2 = client.get(f"/v1/libraries/{lib_id}/duplicates").json()
    assert dups2["groups"] == []

    # A genuinely new near-duplicate joins — the (now 3-file) group must
    # reappear, including the new file.
    with Image.open(original) as im:
        im.resize((64, 64)).save(lib_dir / "photo_tiny.jpg", quality=90)
    snap3 = _run_scan(client, lib_id)
    assert snap3["result"]["groups"] == 1
    dups3 = client.get(f"/v1/libraries/{lib_id}/duplicates").json()
    assert len(dups3["groups"]) == 1
    names = {Path(f["path"]).name for f in dups3["groups"][0]["files"]}
    assert names == {"photo.png", "photo_small.jpg", "photo_tiny.jpg"}


def test_confirm_skips_groups_with_pending_trash(client, tmp_path):
    """A group with an unresolved (not-yet-executed) trash mark must not be
    dismissed — those files are still on disk and the user hasn't finished
    with this group yet."""
    lib_dir = tmp_path / "photos"
    lib_dir.mkdir()
    a = lib_dir / "a.jpg"
    b = lib_dir / "b.jpg"
    img = Image.new("RGB", (64, 64), (100, 150, 200))
    img.save(a)
    b.write_bytes(a.read_bytes())

    lib_id = client.post("/v1/libraries", json={"path": str(lib_dir)}).json()["id"]
    _run_scan(client, lib_id)

    dups = client.get(f"/v1/libraries/{lib_id}/duplicates").json()
    ids = [f["id"] for g in dups["groups"] for f in g["files"]]
    client.post(
        f"/v1/libraries/{lib_id}/duplicates/resolutions",
        json={"resolutions": [{"file_id": ids[1], "action": "trash"}]},
    )

    res = client.post(f"/v1/libraries/{lib_id}/duplicates/confirm")
    assert res.status_code == 200
    body = res.json()
    assert body["confirmed_groups"] == 0
    assert body["skipped_pending"] == 1

    # Still visible — not dismissed.
    dups2 = client.get(f"/v1/libraries/{lib_id}/duplicates").json()
    assert len(dups2["groups"]) == 1


def test_confirm_no_scan_returns_404(client, tmp_path):
    lib_dir = tmp_path / "empty_lib"
    lib_dir.mkdir()
    lib_id = client.post("/v1/libraries", json={"path": str(lib_dir)}).json()["id"]
    res = client.post(f"/v1/libraries/{lib_id}/duplicates/confirm")
    assert res.status_code == 404


def test_reset_dismissals_restores_confirmed_groups(client, tmp_path):
    """"Reset configuration" is the inverse of "Save configuration": it must
    clear every recorded dismissal and immediately un-hide the groups they
    were hiding, without requiring a rescan."""
    lib_dir = tmp_path / "photos"
    lib_dir.mkdir()
    a = lib_dir / "a.jpg"
    b = lib_dir / "b.jpg"
    img = Image.new("RGB", (64, 64), (100, 150, 200))
    img.save(a)
    b.write_bytes(a.read_bytes())

    lib_id = client.post("/v1/libraries", json={"path": str(lib_dir)}).json()["id"]
    _run_scan(client, lib_id)

    confirm = client.post(f"/v1/libraries/{lib_id}/duplicates/confirm")
    assert confirm.json()["confirmed_groups"] == 1
    assert client.get(f"/v1/libraries/{lib_id}/duplicates").json()["groups"] == []

    reset = client.delete(f"/v1/libraries/{lib_id}/duplicates/dismissals")
    assert reset.status_code == 200
    body = reset.json()
    assert body["cleared_dismissals"] == 1
    assert body["restored_groups"] == 1

    dups = client.get(f"/v1/libraries/{lib_id}/duplicates").json()
    assert len(dups["groups"]) == 1


def test_reset_dismissals_with_nothing_saved_is_a_noop(client, tmp_path):
    lib_dir = tmp_path / "empty_lib"
    lib_dir.mkdir()
    lib_id = client.post("/v1/libraries", json={"path": str(lib_dir)}).json()["id"]
    res = client.delete(f"/v1/libraries/{lib_id}/duplicates/dismissals")
    assert res.status_code == 200
    assert res.json() == {"cleared_dismissals": 0, "restored_groups": 0}
