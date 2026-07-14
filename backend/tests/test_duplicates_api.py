"""Tests for duplicate review API (B6) — safety-critical section.

Every test here corresponds to a safety invariant from the Fable plan §2.4:
- dry_run changes nothing on disk
- count-mismatch → 409
- zero-keeper groups are permitted — deleting every copy is the user's call
- NULL-resolution files are never trashed
- vanished file → error entry, not blind trash
- manifest always written on real execution
- report.ok reflects real outcome
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mediamind.api.app import create_app
from mediamind.config import library_data_dir
from mediamind.core.dedupe import DuplicateFile, DuplicateGroup
from mediamind.store.db import library_db_path, open_db
from mediamind.store.duplicates import persist_scan


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def lib_with_dups(client, tmp_path):
    """Register a library, create two image files, and persist a dup scan."""
    lib_dir = tmp_path / "photos"
    lib_dir.mkdir()

    a = lib_dir / "a.jpg"
    b = lib_dir / "b.jpg"
    img = Image.new("RGB", (128, 128), (100, 150, 200))
    img.save(a)
    b.write_bytes(a.read_bytes())

    res = client.post("/v1/libraries", json={"path": str(lib_dir)})
    lib_id = res.json()["id"]

    # Persist a fake scan directly (avoids real scan latency in unit tests).
    data_dir = library_data_dir(lib_dir)
    conn = open_db(library_db_path(data_dir))
    now = time.time()
    group = DuplicateGroup(
        files=[
            DuplicateFile(path=a, size=a.stat().st_size, mtime=a.stat().st_mtime,
                          kind="image", content_hash="abc", width=128, height=128, is_best=True),
            DuplicateFile(path=b, size=b.stat().st_size, mtime=b.stat().st_mtime,
                          kind="image", content_hash="abc", width=128, height=128, is_best=False),
        ],
        match="exact",
    )
    persist_scan(conn, "scan1", [group], lib_dir, now, now + 1,
                 {"type": "dedupe"}, {"groups": 1, "files": 2, "reclaimable_bytes": b.stat().st_size})
    conn.close()

    return lib_id, lib_dir, a, b


def _member_ids(client, lib_id) -> list[int]:
    dups = client.get(f"/v1/libraries/{lib_id}/duplicates").json()
    return [f["id"] for g in dups["groups"] for f in g["files"]]


# ---------------------------------------------------------------------------
# List duplicates
# ---------------------------------------------------------------------------

def test_list_duplicates_returns_groups(lib_with_dups, client):
    lib_id, lib_dir, a, b = lib_with_dups
    res = client.get(f"/v1/libraries/{lib_id}/duplicates")
    assert res.status_code == 200
    body = res.json()
    assert body["scan_id"] == "scan1"
    assert len(body["groups"]) == 1
    assert body["summary"]["groups"] == 1


def test_list_duplicates_no_scan_returns_404(client, tmp_path, monkeypatch):
    lib_dir = tmp_path / "empty_lib"
    lib_dir.mkdir()
    res = client.post("/v1/libraries", json={"path": str(lib_dir)})
    lib_id = res.json()["id"]
    assert client.get(f"/v1/libraries/{lib_id}/duplicates").status_code == 404


# ---------------------------------------------------------------------------
# Resolutions
# ---------------------------------------------------------------------------

def test_set_resolution_keep_and_trash(lib_with_dups, client):
    lib_id, lib_dir, a, b = lib_with_dups
    ids = _member_ids(client, lib_id)
    res = client.post(
        f"/v1/libraries/{lib_id}/duplicates/resolutions",
        json={"resolutions": [
            {"file_id": ids[0], "action": "keep"},
            {"file_id": ids[1], "action": "trash"},
        ]},
    )
    assert res.status_code == 200
    assert res.json()["updated"] == 2


def test_zero_keeper_resolution_allowed(lib_with_dups, client):
    """Marking every member of a group as 'trash' is a valid user choice."""
    lib_id, lib_dir, a, b = lib_with_dups
    ids = _member_ids(client, lib_id)
    res = client.post(
        f"/v1/libraries/{lib_id}/duplicates/resolutions",
        json={"resolutions": [
            {"file_id": ids[0], "action": "trash"},
            {"file_id": ids[1], "action": "trash"},
        ]},
    )
    assert res.status_code == 200
    assert res.json()["updated"] == 2


def test_invalid_action_rejected(lib_with_dups, client):
    lib_id, lib_dir, a, b = lib_with_dups
    ids = _member_ids(client, lib_id)
    res = client.post(
        f"/v1/libraries/{lib_id}/duplicates/resolutions",
        json={"resolutions": [{"file_id": ids[0], "action": "delete"}]},
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Execute — dry-run
# ---------------------------------------------------------------------------

def test_dry_run_changes_nothing_on_disk(lib_with_dups, client):
    lib_id, lib_dir, a, b = lib_with_dups
    ids = _member_ids(client, lib_id)

    client.post(
        f"/v1/libraries/{lib_id}/duplicates/resolutions",
        json={"resolutions": [
            {"file_id": ids[0], "action": "keep"},
            {"file_id": ids[1], "action": "trash"},
        ]},
    )

    before = {p: p.stat().st_size for p in lib_dir.rglob("*.jpg")}
    res = client.post(
        f"/v1/libraries/{lib_id}/duplicates/execute",
        json={"dry_run": True, "expected_trash_count": 1},
    )
    assert res.status_code == 200
    after = {p: p.stat().st_size for p in lib_dir.rglob("*.jpg")}
    assert before == after  # nothing moved


def test_dry_run_report(lib_with_dups, client):
    lib_id, lib_dir, a, b = lib_with_dups
    ids = _member_ids(client, lib_id)
    client.post(
        f"/v1/libraries/{lib_id}/duplicates/resolutions",
        json={"resolutions": [
            {"file_id": ids[0], "action": "keep"},
            {"file_id": ids[1], "action": "trash"},
        ]},
    )
    res = client.post(
        f"/v1/libraries/{lib_id}/duplicates/execute",
        json={"dry_run": True, "expected_trash_count": 1},
    )
    body = res.json()
    assert body["dry_run"] is True
    assert body["planned"] == 1


# ---------------------------------------------------------------------------
# Execute — count mismatch guard
# ---------------------------------------------------------------------------

def test_count_mismatch_returns_409(lib_with_dups, client):
    """Server must reject if expected_trash_count doesn't match actual trash set."""
    lib_id, lib_dir, a, b = lib_with_dups
    ids = _member_ids(client, lib_id)
    client.post(
        f"/v1/libraries/{lib_id}/duplicates/resolutions",
        json={"resolutions": [{"file_id": ids[1], "action": "trash"}]},
    )
    res = client.post(
        f"/v1/libraries/{lib_id}/duplicates/execute",
        json={"dry_run": False, "expected_trash_count": 99},
    )
    assert res.status_code == 409


# ---------------------------------------------------------------------------
# Execute — NULL-resolution never trashed
# ---------------------------------------------------------------------------

def test_null_resolution_files_never_trashed(lib_with_dups, client):
    """Files with no resolution must not appear in the trash set."""
    lib_id, lib_dir, a, b = lib_with_dups
    ids = _member_ids(client, lib_id)

    # Don't set any resolutions at all → trash set is empty → expected_count 0.
    res = client.post(
        f"/v1/libraries/{lib_id}/duplicates/execute",
        json={"dry_run": True, "expected_trash_count": 0},
    )
    assert res.status_code == 200
    assert res.json()["planned"] == 0


# ---------------------------------------------------------------------------
# Execute — vanished file → error entry, not blind trash
# ---------------------------------------------------------------------------

def test_vanished_file_produces_error_not_blind_trash(lib_with_dups, client, tmp_path):
    lib_id, lib_dir, a, b = lib_with_dups
    ids = _member_ids(client, lib_id)

    client.post(
        f"/v1/libraries/{lib_id}/duplicates/resolutions",
        json={"resolutions": [
            {"file_id": ids[0], "action": "keep"},
            {"file_id": ids[1], "action": "trash"},
        ]},
    )

    # Delete the file that was marked for trash so it vanishes before execute.
    b.unlink()

    res = client.post(
        f"/v1/libraries/{lib_id}/duplicates/execute",
        json={"dry_run": False, "expected_trash_count": 1},
    )
    assert res.status_code == 200
    body = res.json()
    # The vanished file should appear as an error entry, not be silently skipped.
    error_entries = [e for e in body["entries"] if e["action"] == "error"]
    assert len(error_entries) >= 1
    assert body["ok"] is False  # report.ok reflects the error


# ---------------------------------------------------------------------------
# Execute — manifest written
# ---------------------------------------------------------------------------

def test_executed_group_disappears_from_list(lib_with_dups, client):
    """Regression: after a real (non-dry-run) execute, the trashed file and
    its now-resolved group must never reappear in GET /duplicates — a stale
    UI can't offer a re-click on a file that's already gone from disk.
    """
    lib_id, lib_dir, a, b = lib_with_dups
    ids = _member_ids(client, lib_id)
    client.post(
        f"/v1/libraries/{lib_id}/duplicates/resolutions",
        json={"resolutions": [
            {"file_id": ids[0], "action": "keep"},
            {"file_id": ids[1], "action": "trash"},
        ]},
    )
    res = client.post(
        f"/v1/libraries/{lib_id}/duplicates/execute",
        json={"dry_run": False, "expected_trash_count": 1},
    )
    assert res.status_code == 200
    assert res.json()["ok"]

    dups = client.get(f"/v1/libraries/{lib_id}/duplicates").json()
    all_ids = [f["id"] for g in dups["groups"] for f in g["files"]]
    assert ids[1] not in all_ids, "trashed file must not reappear in the review list"
    # Only one file is left in the group (the keeper) — it's no longer a
    # "duplicate" group at all, so the group itself must be gone too.
    assert dups["groups"] == []
    assert dups["summary"]["groups"] == 0


def test_manifest_written_on_execute(lib_with_dups, client):
    lib_id, lib_dir, a, b = lib_with_dups
    ids = _member_ids(client, lib_id)
    client.post(
        f"/v1/libraries/{lib_id}/duplicates/resolutions",
        json={"resolutions": [
            {"file_id": ids[0], "action": "keep"},
            {"file_id": ids[1], "action": "trash"},
        ]},
    )
    res = client.post(
        f"/v1/libraries/{lib_id}/duplicates/execute",
        json={"dry_run": True, "expected_trash_count": 1},
    )
    assert res.status_code == 200
    manifest_path = res.json()["manifest_path"]
    assert manifest_path is not None
    assert Path(manifest_path).exists()


# ---------------------------------------------------------------------------
# Execute as a background job (async — the "no keeper" removal's other half:
# a large delete must not block the caller)
# ---------------------------------------------------------------------------

def _wait_job(client, job_id, timeout=30.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        snap = client.get(f"/v1/jobs/{job_id}").json()
        if snap["state"] in ("succeeded", "failed", "cancelled"):
            return snap
        if time.monotonic() > deadline:
            raise TimeoutError(f"Job {job_id} stuck in {snap['state']}")
        time.sleep(0.05)


def test_execute_job_starts_and_completes(lib_with_dups, client):
    lib_id, lib_dir, a, b = lib_with_dups
    ids = _member_ids(client, lib_id)
    client.post(
        f"/v1/libraries/{lib_id}/duplicates/resolutions",
        json={"resolutions": [
            {"file_id": ids[0], "action": "keep"},
            {"file_id": ids[1], "action": "trash"},
        ]},
    )

    res = client.post(
        f"/v1/libraries/{lib_id}/duplicates/execute-job",
        json={"expected_trash_count": 1},
    )
    assert res.status_code == 202
    body = res.json()
    assert body["type"] == "dedupe-execute"
    assert body["state"] in ("queued", "running")

    snap = _wait_job(client, body["id"])
    assert snap["state"] == "succeeded"
    assert snap["result"]["ok"] is True
    assert snap["result"]["handled"] == 1
    assert snap["result"]["error_count"] == 0

    dups = client.get(f"/v1/libraries/{lib_id}/duplicates").json()
    assert dups["groups"] == []


def test_execute_job_count_mismatch_returns_409(lib_with_dups, client):
    lib_id, lib_dir, a, b = lib_with_dups
    ids = _member_ids(client, lib_id)
    client.post(
        f"/v1/libraries/{lib_id}/duplicates/resolutions",
        json={"resolutions": [{"file_id": ids[1], "action": "trash"}]},
    )
    res = client.post(
        f"/v1/libraries/{lib_id}/duplicates/execute-job",
        json={"expected_trash_count": 99},
    )
    assert res.status_code == 409


def test_execute_job_busy_returns_409(lib_with_dups, client, monkeypatch):
    lib_id, lib_dir, a, b = lib_with_dups
    ids = _member_ids(client, lib_id)
    client.post(
        f"/v1/libraries/{lib_id}/duplicates/resolutions",
        json={"resolutions": [
            {"file_id": ids[0], "action": "keep"},
            {"file_id": ids[1], "action": "trash"},
        ]},
    )

    import threading
    block = threading.Event()

    import mediamind.api.routes.duplicates as duplicates_module
    original_trash = duplicates_module.trash

    def slow_trash(*args, **kwargs):
        block.wait(timeout=5)
        return original_trash(*args, **kwargs)

    monkeypatch.setattr(duplicates_module, "trash", slow_trash)

    res1 = client.post(
        f"/v1/libraries/{lib_id}/duplicates/execute-job",
        json={"expected_trash_count": 1},
    )
    assert res1.status_code == 202
    time.sleep(0.05)  # let the worker thread start and grab the guard

    res2 = client.post(
        f"/v1/libraries/{lib_id}/duplicates/execute-job",
        json={"expected_trash_count": 1},
    )
    assert res2.status_code == 409

    block.set()
    _wait_job(client, res1.json()["id"])


class _StubCtx:
    """Minimal JobContext stand-in — the runner only needs cancelled() and
    report_progress(); mirrors test_face_scan_runner.py's _StubCtx."""

    job_id = "test-execute"

    def cancelled(self) -> bool:
        return False

    def report_progress(self, done: int, total: int, phase: str = "") -> None:
        pass


def test_execute_runner_vanished_file_produces_error(lib_with_dups, client):
    """Runner-level check (no threads/HTTP polling needed) mirroring
    test_vanished_file_produces_error_not_blind_trash for the async path."""
    lib_id, lib_dir, a, b = lib_with_dups
    ids = _member_ids(client, lib_id)
    client.post(
        f"/v1/libraries/{lib_id}/duplicates/resolutions",
        json={"resolutions": [
            {"file_id": ids[0], "action": "keep"},
            {"file_id": ids[1], "action": "trash"},
        ]},
    )
    b.unlink()

    from mediamind.api.routes.duplicates import _make_execute_runner

    runner = _make_execute_runner(lib_dir, [ids[1]], [b.name], permanent=False)
    result = runner(_StubCtx())

    assert result["ok"] is False
    assert result["handled"] == 0
    assert result["error_count"] == 1


# ---------------------------------------------------------------------------
# Thumbnail
# ---------------------------------------------------------------------------

def test_thumbnail_returns_jpeg(lib_with_dups, client):
    lib_id, lib_dir, a, b = lib_with_dups
    ids = _member_ids(client, lib_id)
    res = client.get(f"/v1/libraries/{lib_id}/duplicates/files/{ids[0]}/thumbnail")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/jpeg")


def test_thumbnail_unknown_member_404(lib_with_dups, client):
    lib_id, lib_dir, a, b = lib_with_dups
    res = client.get(f"/v1/libraries/{lib_id}/duplicates/files/99999/thumbnail")
    assert res.status_code == 404
