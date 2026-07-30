"""Tests for the duplicate-location manager (Phase 6B): GET groups photos
exported into multiple person folders; POST prunes copies, never originals.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mediamind.api.app import create_app
from mediamind.core.safety import ExecutionReport, ManifestEntry
from mediamind.store.audit import record_action
from mediamind.store.db import library_db_path, open_db
from mediamind.config import library_data_dir


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def lib(client: TestClient, tmp_path: Path):
    root = tmp_path / "photos"
    (root / "Alice").mkdir(parents=True)
    (root / "Bob").mkdir(parents=True)

    Image.new("RGB", (64, 48), (255, 0, 0)).save(root / "group.jpg")
    Image.new("RGB", (64, 48), (255, 0, 0)).save(root / "Alice" / "group.jpg")
    Image.new("RGB", (64, 48), (255, 0, 0)).save(root / "Bob" / "group.jpg")
    Image.new("RGB", (64, 48), (0, 255, 0)).save(root / "solo.jpg")

    res = client.post("/v1/libraries", json={"path": str(root)})
    assert res.status_code == 201
    return res.json()["id"], root


def _seed_export(root: Path, kind: str = "export-by-person", undone: bool = False) -> None:
    """Record a fake export action copying group.jpg into two person folders,
    the same shape record_action() writes for a real Phase 6A export."""
    conn = open_db(library_db_path(library_data_dir(root)))
    try:
        report = ExecutionReport(
            planned=2,
            handled=2,
            entries=[
                ManifestEntry(str(root / "group.jpg"), "copied", str(root / "Alice" / "group.jpg")),
                ManifestEntry(str(root / "group.jpg"), "copied", str(root / "Bob" / "group.jpg")),
            ],
        )
        action_id = record_action(
            conn, kind=kind, manifest_path=str(root / ".mediamind" / "fake.json"),
            report=report, dry_run=False,
        )
        if undone:
            conn.execute("UPDATE organize_actions SET undone = 1 WHERE id = ?", (action_id,))
            conn.commit()
    finally:
        conn.close()


def test_lists_group_with_all_locations(client: TestClient, lib):
    lib_id, root = lib
    _seed_export(root)

    res = client.get(f"/v1/libraries/{lib_id}/organize/duplicate-locations")
    assert res.status_code == 200
    groups = res.json()
    assert len(groups) == 1
    g = groups[0]
    assert g["source"] == "group.jpg"
    paths = {loc["path"]: loc["is_source"] for loc in g["locations"]}
    assert paths == {
        "group.jpg": True,
        "Alice/group.jpg": False,
        "Bob/group.jpg": False,
    }
    assert all(loc["kind"] == "image" for loc in g["locations"])


def test_solo_file_never_appears(client: TestClient, lib):
    lib_id, root = lib
    _seed_export(root)

    res = client.get(f"/v1/libraries/{lib_id}/organize/duplicate-locations")
    sources = {g["source"] for g in res.json()}
    assert "solo.jpg" not in sources


def test_undone_export_excluded(client: TestClient, lib):
    lib_id, root = lib
    _seed_export(root, undone=True)

    res = client.get(f"/v1/libraries/{lib_id}/organize/duplicate-locations")
    assert res.json() == []


def test_deleted_copy_drops_out_on_next_list(client: TestClient, lib):
    lib_id, root = lib
    _seed_export(root)
    (root / "Bob" / "group.jpg").unlink()

    res = client.get(f"/v1/libraries/{lib_id}/organize/duplicate-locations")
    g = res.json()[0]
    paths = {loc["path"] for loc in g["locations"]}
    assert paths == {"group.jpg", "Alice/group.jpg"}


def test_prune_trashes_only_named_copies(client: TestClient, lib):
    lib_id, root = lib
    _seed_export(root)

    res = client.post(
        f"/v1/libraries/{lib_id}/organize/duplicate-locations/prune",
        json={"paths": ["Bob/group.jpg"], "dry_run": False},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["handled"] == 1
    assert not (root / "Bob" / "group.jpg").exists()
    assert (root / "Alice" / "group.jpg").exists()
    assert (root / "group.jpg").exists(), "the original must never be touched by this endpoint"

    # And it drops out of the next listing.
    res2 = client.get(f"/v1/libraries/{lib_id}/organize/duplicate-locations")
    g = res2.json()[0]
    paths = {loc["path"] for loc in g["locations"]}
    assert paths == {"group.jpg", "Alice/group.jpg"}


def test_prune_dry_run_deletes_nothing(client: TestClient, lib):
    lib_id, root = lib
    _seed_export(root)

    res = client.post(
        f"/v1/libraries/{lib_id}/organize/duplicate-locations/prune",
        json={"paths": ["Bob/group.jpg"], "dry_run": True},
    )
    assert res.status_code == 200
    assert (root / "Bob" / "group.jpg").exists()


def test_prune_rejects_path_traversal(client: TestClient, lib):
    lib_id, root = lib
    _seed_export(root)

    res = client.post(
        f"/v1/libraries/{lib_id}/organize/duplicate-locations/prune",
        json={"paths": ["../outside.jpg"], "dry_run": False},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["planned"] == 0, "an unresolvable/unsafe path must never reach trash()"
