"""Tests for the Explorer shell's file operations (M12 Phase B):
new folder / rename / move / copy / delete / undo.

Invariants under test:
- Same-volume moves are atomic (os.replace); cross-volume/dir moves are
  copy-then-delete and the source survives any copy failure intact.
- Every batch write (move/copy/delete) writes a manifest and never aborts on
  one bad item — a failure becomes an error entry, the rest of the batch
  continues, and report.ok reflects the verifiable count check.
- Explorer-style collision naming: "name - Copy" in the same folder,
  "name (2)" in a different folder.
- Rename/new-folder are exempt from the manifest/dry-run machinery
  (non-destructive) but still get an op-log line for undo.
- Undo reverses exactly the most recent non-undone operation.
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mediamind.api.app import create_app
from mediamind.core import archive, fsops, oplog
from mediamind.core.fsops import FsOpError

# ---------------------------------------------------------------------------
# new_folder
# ---------------------------------------------------------------------------

def test_new_folder_default_name(tmp_path: Path):
    p = fsops.new_folder(tmp_path, None)
    assert p == tmp_path / "New folder"
    assert p.is_dir()


def test_new_folder_default_name_collision(tmp_path: Path):
    (tmp_path / "New folder").mkdir()
    p = fsops.new_folder(tmp_path, None)
    assert p == tmp_path / "New folder (2)"


def test_new_folder_custom_name(tmp_path: Path):
    p = fsops.new_folder(tmp_path, "Vacation Photos")
    assert p == tmp_path / "Vacation Photos"


def test_new_folder_rejects_illegal_name(tmp_path: Path):
    with pytest.raises(FsOpError):
        fsops.new_folder(tmp_path, "bad:name")


def test_new_folder_rejects_empty_name(tmp_path: Path):
    with pytest.raises(FsOpError):
        fsops.new_folder(tmp_path, "   ")


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------

def test_rename_basic(tmp_path: Path):
    f = tmp_path / "old.txt"
    f.write_text("hi")
    new_path = fsops.rename(f, "new.txt")
    assert new_path == tmp_path / "new.txt"
    assert new_path.exists()
    assert not f.exists()


def test_rename_rejects_collision(tmp_path: Path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    with pytest.raises(FsOpError):
        fsops.rename(tmp_path / "a.txt", "b.txt")


def test_rename_rejects_illegal_name(tmp_path: Path):
    f = tmp_path / "old.txt"
    f.write_text("hi")
    with pytest.raises(FsOpError):
        fsops.rename(f, "bad/name.txt")


# ---------------------------------------------------------------------------
# collision naming
# ---------------------------------------------------------------------------

def test_explorer_unique_destination_same_folder(tmp_path: Path):
    src = tmp_path / "photo.jpg"
    src.write_text("x")
    (tmp_path / "photo - Copy.jpg").write_text("x")
    dest = fsops.explorer_unique_destination(tmp_path, src, same_folder=True)
    assert dest == tmp_path / "photo - Copy (2).jpg"


def test_explorer_unique_destination_different_folder(tmp_path: Path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    src = src_dir / "photo.jpg"
    src.write_text("x")
    (dst_dir / "photo.jpg").write_text("existing")
    dest = fsops.explorer_unique_destination(dst_dir, src, same_folder=False)
    assert dest == dst_dir / "photo (2).jpg"


def test_explorer_unique_destination_no_collision(tmp_path: Path):
    src = tmp_path / "photo.jpg"
    src.write_text("x")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    dest = fsops.explorer_unique_destination(dst_dir, src, same_folder=False)
    assert dest == dst_dir / "photo.jpg"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_delete_trash_calls_send2trash(tmp_path: Path, monkeypatch):
    f = tmp_path / "a.txt"
    f.write_text("x")
    trashed = []

    def fake_send2trash(path):
        trashed.append(path)
        Path(path).unlink()

    monkeypatch.setattr("send2trash.send2trash", fake_send2trash)
    report = fsops.delete_entries([f], permanent=False)
    assert report.ok
    assert report.handled == 1
    assert trashed == [str(f)]
    assert not f.exists()


def test_delete_permanent_removes_file(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    report = fsops.delete_entries([f], permanent=True)
    assert report.ok
    assert not f.exists()


def test_delete_permanent_removes_directory(tmp_path: Path):
    d = tmp_path / "folder"
    (d / "sub").mkdir(parents=True)
    (d / "sub" / "file.txt").write_text("x")
    report = fsops.delete_entries([d], permanent=True)
    assert report.ok
    assert not d.exists()


def test_delete_stale_path_is_error_not_abort(tmp_path: Path):
    real = tmp_path / "real.txt"
    real.write_text("x")
    missing = tmp_path / "gone.txt"  # never created
    report = fsops.delete_entries([missing, real], permanent=True)
    assert not report.ok
    assert report.handled == 1
    assert len(report.errors) == 1
    assert not real.exists()  # the valid item was still handled


def test_delete_dry_run_changes_nothing(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    report = fsops.delete_entries([f], permanent=True, dry_run=True)
    assert report.ok
    assert f.exists()
    assert report.entries[0].action == "dry-run-deleted"


# ---------------------------------------------------------------------------
# move
# ---------------------------------------------------------------------------

def test_move_same_volume_atomic(tmp_path: Path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    f = src_dir / "photo.jpg"
    f.write_text("x")

    report = fsops.move_entries([f], dst_dir)
    assert report.ok
    assert (dst_dir / "photo.jpg").exists()
    assert not f.exists()


def test_move_no_op_when_dest_is_current_parent(tmp_path: Path):
    f = tmp_path / "photo.jpg"
    f.write_text("x")
    report = fsops.move_entries([f], tmp_path)
    assert report.ok
    assert report.entries[0].action == "unchanged"
    assert f.exists()


def test_move_rejects_dest_inside_source(tmp_path: Path):
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)

    report = fsops.move_entries([parent], child)
    assert not report.ok
    assert report.errors[0].action == "error"
    assert parent.exists()  # nothing touched


def test_move_directory_tree_cross_volume_simulated(tmp_path: Path, monkeypatch):
    src_dir = tmp_path / "src" / "album"
    dst_dir = tmp_path / "dst"
    (src_dir).mkdir(parents=True)
    dst_dir.mkdir()
    (src_dir / "a.jpg").write_text("a")
    (src_dir / "sub").mkdir()
    (src_dir / "sub" / "b.jpg").write_text("b")

    monkeypatch.setattr(fsops, "_same_volume", lambda a, b: False)
    report = fsops.move_entries([src_dir], dst_dir)
    assert report.ok
    assert (dst_dir / "album" / "a.jpg").exists()
    assert (dst_dir / "album" / "sub" / "b.jpg").exists()
    assert not src_dir.exists()  # deleted only after full copy succeeded


def test_move_directory_tree_partial_failure_preserves_source(tmp_path: Path, monkeypatch):
    src_dir = tmp_path / "src" / "album"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir(parents=True)
    dst_dir.mkdir()
    (src_dir / "a.jpg").write_text("a")

    monkeypatch.setattr(fsops, "_same_volume", lambda a, b: False)
    monkeypatch.setattr(
        fsops,
        "_copy_tree_resilient",
        lambda s, d: (0, [fsops.ManifestEntry(str(s / "a.jpg"), "error", "", "boom")]),
    )
    report = fsops.move_entries([src_dir], dst_dir)
    assert not report.ok
    assert src_dir.exists()  # copy-then-delete: source survives a failed copy
    assert (src_dir / "a.jpg").exists()


def test_move_dry_run_changes_nothing(tmp_path: Path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    f = src_dir / "photo.jpg"
    f.write_text("x")

    report = fsops.move_entries([f], dst_dir, dry_run=True)
    assert report.ok
    assert report.entries[0].action == "dry-run-moved"
    assert f.exists()
    assert not (dst_dir / "photo.jpg").exists()


# ---------------------------------------------------------------------------
# copy
# ---------------------------------------------------------------------------

def test_copy_leaves_source_intact(tmp_path: Path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    f = src_dir / "photo.jpg"
    f.write_text("x")

    report = fsops.copy_entries([f], dst_dir)
    assert report.ok
    assert f.exists()
    assert (dst_dir / "photo.jpg").exists()


def test_copy_same_folder_uses_copy_suffix(tmp_path: Path):
    f = tmp_path / "photo.jpg"
    f.write_text("x")
    report = fsops.copy_entries([f], tmp_path)
    assert report.ok
    assert report.entries[0].destination == str(tmp_path / "photo - Copy.jpg")


def test_copy_directory_tree(tmp_path: Path):
    src_dir = tmp_path / "src" / "album"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir(parents=True)
    dst_dir.mkdir()
    (src_dir / "a.jpg").write_text("a")

    report = fsops.copy_entries([src_dir], dst_dir)
    assert report.ok
    assert (src_dir / "a.jpg").exists()  # source untouched
    assert (dst_dir / "album" / "a.jpg").exists()


def test_copy_rejects_dest_inside_source(tmp_path: Path):
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    report = fsops.copy_entries([parent], child)
    assert not report.ok


# ---------------------------------------------------------------------------
# delete -> oplog history (Phase P item 4 — "Recent deletions" panel)
# ---------------------------------------------------------------------------

def test_delete_permanent_is_logged_for_history(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    f = tmp_path / "a.txt"
    f.write_text("x")
    fsops.delete_entries([f], permanent=True)

    deletions = oplog.list_deletions()
    assert len(deletions) == 1
    assert deletions[0].path == str(f)
    assert deletions[0].permanent is True


def test_delete_trashed_is_logged_for_history(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    f = tmp_path / "a.txt"
    f.write_text("x")
    monkeypatch.setattr("send2trash.send2trash", lambda path: Path(path).unlink())
    fsops.delete_entries([f], permanent=False)

    deletions = oplog.list_deletions()
    assert len(deletions) == 1
    assert deletions[0].permanent is False


def test_delete_dry_run_is_not_logged(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    f = tmp_path / "a.txt"
    f.write_text("x")
    fsops.delete_entries([f], permanent=True, dry_run=True)
    assert oplog.list_deletions() == []


def test_delete_failure_is_not_logged(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    fsops.delete_entries([tmp_path / "does_not_exist.txt"], permanent=True)
    assert oplog.list_deletions() == []


def test_list_deletions_most_recent_first(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("x")
    b.write_text("x")
    fsops.delete_entries([a], permanent=True)
    fsops.delete_entries([b], permanent=True)

    deletions = oplog.list_deletions()
    assert [d.path for d in deletions] == [str(b), str(a)]


def test_undo_after_delete_is_a_friendly_no_op(tmp_path: Path, monkeypatch):
    """Deletes are never reversible via the op-log (see `fsops.delete_entries`'s
    comment) — undo must surface a clear message, not "Unknown op kind"."""
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    f = tmp_path / "a.txt"
    f.write_text("x")
    fsops.delete_entries([f], permanent=True)

    result = oplog.undo_last()
    assert not result.ok
    assert result.kind == "delete"
    assert "Recycle Bin" in result.message


def test_api_recent_deletions_empty_by_default(client: TestClient, tmp_path: Path):
    res = client.get("/v1/fs/recent-deletions")
    assert res.status_code == 200
    assert res.json()["deletions"] == []


def test_api_recent_deletions_after_delete(client: TestClient, tmp_path: Path, monkeypatch):
    f = tmp_path / "a.txt"
    f.write_text("x")
    monkeypatch.setattr("send2trash.send2trash", lambda path: Path(path).unlink())
    client.post("/v1/fs/delete", json={"paths": [str(f)]})

    res = client.get("/v1/fs/recent-deletions")
    assert res.status_code == 200
    body = res.json()["deletions"]
    assert len(body) == 1
    assert body[0]["path"] == str(f)
    assert body[0]["permanent"] is False


# ---------------------------------------------------------------------------
# undo
# ---------------------------------------------------------------------------

def test_undo_nothing_to_undo(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    result = oplog.undo_last()
    assert not result.ok


def test_undo_rename(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    f = tmp_path / "old.txt"
    f.write_text("x")
    new_path = fsops.rename(f, "new.txt")

    result = oplog.undo_last()
    assert result.ok
    assert result.kind == "rename"
    assert f.exists()
    assert not new_path.exists()


def test_undo_new_folder_removes_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    p = fsops.new_folder(tmp_path, "Empty")
    result = oplog.undo_last()
    assert result.ok
    assert not p.exists()


def test_undo_new_folder_rejects_when_not_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    p = fsops.new_folder(tmp_path, "NotEmpty")
    (p / "file.txt").write_text("x")
    result = oplog.undo_last()
    assert not result.ok
    assert p.exists()


def test_undo_move(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    f = src_dir / "photo.jpg"
    f.write_text("x")
    fsops.move_entries([f], dst_dir)

    result = oplog.undo_last()
    assert result.ok
    assert result.kind == "move"
    assert f.exists()
    assert not (dst_dir / "photo.jpg").exists()


def test_undo_copy_trashes_the_copy(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    trashed = []

    def fake_send2trash(path):
        trashed.append(path)
        Path(path).unlink()

    monkeypatch.setattr("send2trash.send2trash", fake_send2trash)

    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    f = src_dir / "photo.jpg"
    f.write_text("x")
    fsops.copy_entries([f], dst_dir)

    result = oplog.undo_last()
    assert result.ok
    assert result.kind == "copy"
    assert f.exists()  # original untouched
    assert trashed  # the copy was trashed


def test_undo_reverses_in_reverse_order(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    first = fsops.new_folder(tmp_path, "First")
    second = fsops.new_folder(tmp_path, "Second")

    result = oplog.undo_last()
    assert result.ok
    assert not second.exists()
    assert first.exists()  # not touched by undoing the most recent op yet

    # Each further undo call walks one more step back through the op-log.
    result2 = oplog.undo_last()
    assert result2.ok
    assert not first.exists()

    result3 = oplog.undo_last()
    assert not result3.ok  # nothing left to undo


# ---------------------------------------------------------------------------
# redo — bounded to the single most recently undone operation
# ---------------------------------------------------------------------------

def test_redo_nothing_to_redo(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    result = oplog.redo_last()
    assert not result.ok


def test_redo_rename(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    f = tmp_path / "old.txt"
    f.write_text("x")
    new_path = fsops.rename(f, "new.txt")
    oplog.undo_last()

    result = oplog.redo_last()
    assert result.ok
    assert result.kind == "rename"
    assert new_path.exists()
    assert not f.exists()


def test_redo_new_folder(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    p = fsops.new_folder(tmp_path, "Empty")
    oplog.undo_last()
    assert not p.exists()

    result = oplog.redo_last()
    assert result.ok
    assert p.exists()


def test_redo_move(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    f = src_dir / "photo.jpg"
    f.write_text("x")
    fsops.move_entries([f], dst_dir)
    oplog.undo_last()
    assert f.exists()

    result = oplog.redo_last()
    assert result.ok
    assert result.kind == "move"
    assert not f.exists()
    assert (dst_dir / "photo.jpg").exists()


def test_redo_copy(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    trashed = []
    monkeypatch.setattr("send2trash.send2trash", lambda path: (trashed.append(path), Path(path).unlink()))

    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    f = src_dir / "photo.jpg"
    f.write_text("x")
    fsops.copy_entries([f], dst_dir)
    oplog.undo_last()
    assert not (dst_dir / "photo.jpg").exists()

    result = oplog.redo_last()
    assert result.ok
    assert result.kind == "copy"
    assert f.exists()  # original still untouched
    assert (dst_dir / "photo.jpg").exists()


def test_redo_invalidated_by_a_new_action(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    p = fsops.new_folder(tmp_path, "Empty")
    oplog.undo_last()

    fsops.new_folder(tmp_path, "Unrelated")  # a new action clears the redo slot

    result = oplog.redo_last()
    assert not result.ok
    assert not p.exists()


def test_redo_then_undo_again_toggles_cleanly(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    p = fsops.new_folder(tmp_path, "Empty")
    oplog.undo_last()
    oplog.redo_last()
    assert p.exists()

    result = oplog.undo_last()
    assert result.ok
    assert not p.exists()


# ---------------------------------------------------------------------------
# create_shortcut
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="Windows .lnk shortcuts only")
def test_create_shortcut_basic(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    target = tmp_path / "target.txt"
    target.write_text("x")
    dest_folder = tmp_path / "dest"
    dest_folder.mkdir()

    shortcut = fsops.create_shortcut(target, dest_folder)
    assert shortcut.exists()
    assert shortcut.suffix == ".lnk"
    assert shortcut.parent == dest_folder


@pytest.mark.skipif(sys.platform != "win32", reason="Windows .lnk shortcuts only")
def test_create_shortcut_collision_renames(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    target = tmp_path / "target.txt"
    target.write_text("x")
    (tmp_path / "target - Shortcut.lnk").write_text("occupied")

    shortcut = fsops.create_shortcut(target, tmp_path)
    assert shortcut.name == "target - Shortcut (2).lnk"


def test_create_shortcut_rejects_on_non_windows(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.setattr(os, "name", "posix")
    target = tmp_path / "target.txt"
    target.write_text("x")
    with pytest.raises(FsOpError):
        fsops.create_shortcut(target, tmp_path)


def test_undo_create_shortcut(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.setattr(
        fsops, "create_shortcut", lambda target, dest_folder, name=None: _fake_shortcut(dest_folder, name)
    )
    dest = fsops.create_shortcut(tmp_path / "target.txt", tmp_path, name="target - Shortcut")

    result = oplog.undo_last()
    assert result.ok
    assert result.kind == "create_shortcut"
    assert not dest.exists()


def _fake_shortcut(dest_folder: Path, name: str | None) -> Path:
    """Stand-in for `fsops.create_shortcut()` on non-Windows test runners —
    writes a placeholder file and logs the same op-log entry the real
    implementation would, so undo/redo of this kind can be exercised without
    PowerShell/WScript.Shell being available."""
    dest = dest_folder / f"{name or 'target - Shortcut'}.lnk"
    dest.write_text("shortcut")
    oplog.append_op_log({"kind": "create_shortcut", "path": str(dest), "target": str(dest_folder / "target.txt")})
    return dest


# ---------------------------------------------------------------------------
# API level
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app()) as c:
        yield c


def test_api_new_folder(client: TestClient, tmp_path: Path):
    res = client.post("/v1/fs/new-folder", json={"parent": str(tmp_path), "name": "Trip"})
    assert res.status_code == 200
    assert Path(res.json()["path"]).is_dir()


def test_api_new_folder_bad_parent(client: TestClient, tmp_path: Path):
    res = client.post("/v1/fs/new-folder", json={"parent": str(tmp_path / "nope")})
    assert res.status_code == 404


def test_api_rename(client: TestClient, tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    res = client.post("/v1/fs/rename", json={"path": str(f), "new_name": "b.txt"})
    assert res.status_code == 200
    assert (tmp_path / "b.txt").exists()


def test_api_rename_collision_returns_409(client: TestClient, tmp_path: Path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    res = client.post("/v1/fs/rename", json={"path": str(tmp_path / "a.txt"), "new_name": "b.txt"})
    assert res.status_code == 409


def test_api_delete(client: TestClient, tmp_path: Path, monkeypatch):
    f = tmp_path / "a.txt"
    f.write_text("x")
    monkeypatch.setattr("send2trash.send2trash", lambda path: Path(path).unlink())
    res = client.post("/v1/fs/delete", json={"paths": [str(f)]})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert not f.exists()


def test_api_move(client: TestClient, tmp_path: Path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    f = src_dir / "photo.jpg"
    f.write_text("x")

    res = client.post("/v1/fs/move", json={"sources": [str(f)], "dest": str(dst_dir)})
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert (dst_dir / "photo.jpg").exists()


def test_api_copy(client: TestClient, tmp_path: Path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    f = src_dir / "photo.jpg"
    f.write_text("x")

    res = client.post("/v1/fs/copy", json={"sources": [str(f)], "dest": str(dst_dir)})
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert f.exists()
    assert (dst_dir / "photo.jpg").exists()


def test_api_move_rejects_relative_path(client: TestClient, tmp_path: Path):
    res = client.post("/v1/fs/move", json={"sources": ["relative.jpg"], "dest": str(tmp_path)})
    assert res.status_code == 404


def test_api_undo(client: TestClient, tmp_path: Path):
    res = client.post("/v1/fs/new-folder", json={"parent": str(tmp_path), "name": "Trip"})
    path = Path(res.json()["path"])
    res = client.post("/v1/fs/undo")
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert not path.exists()


def test_api_redo(client: TestClient, tmp_path: Path):
    res = client.post("/v1/fs/new-folder", json={"parent": str(tmp_path), "name": "Trip"})
    path = Path(res.json()["path"])
    client.post("/v1/fs/undo")

    res = client.post("/v1/fs/redo")
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert path.exists()


def test_api_redo_nothing_to_redo(client: TestClient):
    res = client.post("/v1/fs/redo")
    assert res.status_code == 200
    assert res.json()["ok"] is False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows .lnk shortcuts only")
def test_api_create_shortcut(client: TestClient, tmp_path: Path):
    target = tmp_path / "target.txt"
    target.write_text("x")
    res = client.post(
        "/v1/fs/create-shortcut", json={"target": str(target), "dest_folder": str(tmp_path)}
    )
    assert res.status_code == 200
    assert Path(res.json()["path"]).exists()


def test_api_create_shortcut_bad_target(client: TestClient, tmp_path: Path):
    res = client.post(
        "/v1/fs/create-shortcut",
        json={"target": str(tmp_path / "nope.txt"), "dest_folder": str(tmp_path)},
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# compress (M12 Phase H)
# ---------------------------------------------------------------------------

def test_compress_dry_run_changes_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    src = tmp_path / "a.txt"
    src.write_text("hi")

    report = archive.compress([src], tmp_path / "Archive.zip", dry_run=True)
    assert report.ok
    assert report.entries[0].action == "dry-run-archived"
    assert not (tmp_path / "Archive.zip").exists()
    assert not list(tmp_path.glob("*.part"))


def test_compress_writes_zip_atomically(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    src = tmp_path / "a.txt"
    src.write_text("hi")
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()

    report = archive.compress([src], dest_dir / "Archive.zip", dry_run=False)
    assert report.ok
    final = dest_dir / "Archive.zip"
    assert final.exists()
    assert not list(dest_dir.glob("*.part"))  # no leftover partial file
    with zipfile.ZipFile(final) as zf:
        assert zf.namelist() == ["a.txt"]


def test_compress_directory_tree(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    album = tmp_path / "album"
    album.mkdir()
    (album / "a.jpg").write_text("a")
    (album / "sub").mkdir()
    (album / "sub" / "b.jpg").write_text("b")
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()

    report = archive.compress([album], dest_dir / "Archive.zip", dry_run=False)
    assert report.ok
    with zipfile.ZipFile(dest_dir / "Archive.zip") as zf:
        names = set(zf.namelist())
    assert names == {"album/a.jpg", "album/sub/b.jpg"}


def test_compress_collision_renames_explorer_style(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    src = tmp_path / "a.txt"
    src.write_text("hi")
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()

    first = archive.compress([src], dest_dir / "Archive.zip", dry_run=False)
    second = archive.compress([src], dest_dir / "Archive.zip", dry_run=False)
    assert first.ok and second.ok
    assert (dest_dir / "Archive.zip").exists()
    assert (dest_dir / "Archive (2).zip").exists()


def test_compress_resilient_to_missing_source(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    good = tmp_path / "a.txt"
    good.write_text("hi")
    missing = tmp_path / "gone.txt"  # never created
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()

    report = archive.compress([good, missing], dest_dir / "Archive.zip", dry_run=False)
    assert not report.ok
    assert report.handled == 1
    assert len(report.errors) == 1
    final = dest_dir / "Archive.zip"
    assert final.exists()  # the good file was still archived
    with zipfile.ZipFile(final) as zf:
        assert zf.namelist() == ["a.txt"]


# ---------------------------------------------------------------------------
# extract (M12 Phase H)
# ---------------------------------------------------------------------------

def _make_zip(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return path


def test_extract_dry_run_changes_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    zip_path = _make_zip(tmp_path / "a.zip", {"a.txt": "hi"})
    dest = tmp_path / "extracted"

    report = archive.extract(zip_path, dest, dry_run=True)
    assert report.ok
    assert not dest.exists()
    assert report.entries[0].action == "dry-run-extracted"


def test_extract_basic(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    zip_path = _make_zip(tmp_path / "a.zip", {"a.txt": "hi", "sub/b.txt": "bye"})
    dest = tmp_path / "extracted"

    report = archive.extract(zip_path, dest, dry_run=False)
    assert report.ok
    assert report.planned == 2
    assert report.handled == 2
    assert (dest / "a.txt").read_text() == "hi"
    assert (dest / "sub" / "b.txt").read_text() == "bye"


def test_extract_collision_renames(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    zip_path = _make_zip(tmp_path / "a.zip", {"a.txt": "new"})
    dest = tmp_path / "extracted"
    dest.mkdir()
    (dest / "a.txt").write_text("existing")

    report = archive.extract(zip_path, dest, dry_run=False)
    assert report.ok
    assert (dest / "a.txt").read_text() == "existing"  # untouched
    renamed = [e for e in report.entries if e.action == "extracted"][0]
    assert Path(renamed.destination) != dest / "a.txt"
    assert Path(renamed.destination).read_text() == "new"


def test_extract_zip_slip_is_rejected(tmp_path: Path, monkeypatch):
    """A malicious member name (`../../evil.txt`-style) must be rejected as
    an error entry, never silently extracted outside the destination root —
    this is the mandatory zip-slip regression guard for Phase H."""
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    zip_path = _make_zip(
        tmp_path / "evil.zip",
        {"../../evil.txt": "pwned", "safe.txt": "fine"},
    )
    dest = tmp_path / "extracted"

    report = archive.extract(zip_path, dest, dry_run=False)

    assert not report.ok  # the malicious member counts as an error, not a silent skip
    escaped = tmp_path.parent / "evil.txt"
    assert not escaped.exists()
    assert not (tmp_path / "evil.txt").exists()
    error_sources = [e.source for e in report.errors]
    assert "../../evil.txt" in error_sources
    # the well-behaved member alongside it still extracts normally
    assert (dest / "safe.txt").read_text() == "fine"


def test_extract_bad_zip_file_is_error_not_crash(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    not_a_zip = tmp_path / "fake.zip"
    not_a_zip.write_text("not actually a zip")
    dest = tmp_path / "extracted"

    report = archive.extract(not_a_zip, dest, dry_run=False)
    assert not report.ok
    assert report.errors


# ---------------------------------------------------------------------------
# API level — compress / extract
# ---------------------------------------------------------------------------

def test_api_compress(client: TestClient, tmp_path: Path):
    src = tmp_path / "a.txt"
    src.write_text("hi")

    res = client.post(
        "/v1/fs/compress",
        json={"paths": [str(src)], "dest": str(tmp_path / "Archive.zip")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert (tmp_path / "Archive.zip").exists()


def test_api_compress_dry_run(client: TestClient, tmp_path: Path):
    src = tmp_path / "a.txt"
    src.write_text("hi")

    res = client.post(
        "/v1/fs/compress",
        json={"paths": [str(src)], "dest": str(tmp_path / "Archive.zip"), "dry_run": True},
    )
    assert res.status_code == 200
    assert not (tmp_path / "Archive.zip").exists()


def test_api_compress_no_paths_422(client: TestClient, tmp_path: Path):
    res = client.post("/v1/fs/compress", json={"paths": [], "dest": str(tmp_path / "Archive.zip")})
    assert res.status_code == 422


def test_api_extract(client: TestClient, tmp_path: Path):
    zip_path = _make_zip(tmp_path / "a.zip", {"a.txt": "hi"})

    res = client.post(
        "/v1/fs/extract",
        json={"zip_path": str(zip_path), "dest": str(tmp_path / "extracted")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert (tmp_path / "extracted" / "a.txt").read_text() == "hi"


def test_api_extract_rejects_non_zip(client: TestClient, tmp_path: Path):
    not_zip = tmp_path / "a.txt"
    not_zip.write_text("hi")

    res = client.post(
        "/v1/fs/extract",
        json={"zip_path": str(not_zip), "dest": str(tmp_path / "extracted")},
    )
    assert res.status_code == 422
