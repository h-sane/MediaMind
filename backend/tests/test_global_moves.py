"""Core tests for cross-library move + undo — the feature's destructive path.

Exercises the CLAUDE.md safety invariants directly (dry-run changes nothing,
count/plan-hash guards, copy-then-delete, per-file isolation, undo) against
real files on disk with fake libraries and no face model. `MEDIAMIND_DATA_DIR`
is redirected per-test so manifests never touch real app data.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from mediamind.core import global_people as core
from mediamind.core.global_people import (
    MoveRequestItem,
    execute_move_plan,
    execute_undo,
    list_move_suggestions,
    open_library_db,
    plan_undo,
)
from mediamind.core.libraries import LibraryRegistry
from mediamind.store import global_people as gp

PROVIDER = "test-provider"


@pytest.fixture(autouse=True)
def _isolated_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))


def _make_library(reg: LibraryRegistry, root: Path, person_files: dict[str, list[str]]):
    """Create a registered library with a face scan, one person per name, and
    real files on disk. Returns (library, {name: local_person_id})."""
    root.mkdir(parents=True, exist_ok=True)
    lib = reg.add(root)
    conn = open_library_db(lib)
    try:
        conn.execute(
            "INSERT INTO scans (id, type, state, params, started_at, finished_at, summary) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("scan1", "faces", "succeeded", json.dumps({"provider_id": PROVIDER}), 0.0, 1.0, "{}"),
        )
        centroid = np.zeros(512, dtype=np.float32)
        centroid[0] = 1.0
        ids: dict[str, int] = {}
        for name, rels in person_files.items():
            cur = conn.execute(
                "INSERT INTO persons (auto_label, name, provider_id, centroid) VALUES (?, ?, ?, ?)",
                (f"Person_{len(ids) + 1:03d}", name, PROVIDER, centroid.tobytes()),
            )
            pid = cur.lastrowid
            ids[name] = pid
            for rel in rels:
                abs_path = Path(lib.path) / rel
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_bytes(b"content-of-" + rel.encode())
                fcur = conn.execute(
                    "INSERT INTO files (path, kind, size, mtime, content_hash, decoded_ok) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (rel, "image", abs_path.stat().st_size, 0.0, f"hash-{rel}", 1),
                )
                conn.execute(
                    "INSERT INTO faces (file_id, provider_id, embedding, person_id) VALUES (?, ?, ?, ?)",
                    (fcur.lastrowid, PROVIDER, b"\x00" * 8, pid),
                )
        conn.commit()
    finally:
        conn.close()
    return lib, ids


def _file_ids(lib) -> dict[str, int]:
    conn = open_library_db(lib)
    try:
        return {r["path"]: r["id"] for r in conn.execute("SELECT id, path FROM files").fetchall()}
    finally:
        conn.close()


def _setup(tmp_path: Path):
    """One library ('src') with a two-file 'Mom', a global identity for her,
    and a primary_location outside the source library."""
    reg = LibraryRegistry(registry_path=tmp_path / "libraries.json")
    src, ids = _make_library(reg, tmp_path / "src", {"Mom": ["a.jpg", "b.jpg"]})
    dest = tmp_path / "dest"
    dest.mkdir()

    gp_conn = gp.open_global_db()
    gid = gp.create_global_person(gp_conn, "Mom")
    gp.link(gp_conn, gid, src.id, ids["Mom"], PROVIDER)
    gp.set_primary_location(gp_conn, gid, str(dest))
    return reg, gp_conn, src, gid, dest


def test_move_suggestions_lists_files_not_at_primary(tmp_path: Path) -> None:
    reg, gp_conn, src, gid, dest = _setup(tmp_path)
    groups = list_move_suggestions(gp_conn, reg)
    assert len(groups) == 1
    assert groups[0]["global_person_id"] == gid
    assert {Path(i["abs_path"]).name for i in groups[0]["items"]} == {"a.jpg", "b.jpg"}


def test_dry_run_changes_nothing_on_disk(tmp_path: Path) -> None:
    reg, gp_conn, src, gid, dest = _setup(tmp_path)
    fids = _file_ids(src)
    items = [MoveRequestItem(gid, src.id, fid) for fid in fids.values()]

    result = execute_move_plan(gp_conn, reg, items, dry_run=True,
                               expected_count=None, expected_plan_hash=None)

    assert result["dry_run"] is True
    assert result["planned"] == 2
    assert (Path(src.path) / "a.jpg").exists()      # sources untouched
    assert not any(dest.iterdir())                  # nothing delivered
    assert _file_ids(src) == fids                   # index untouched


def test_real_move_copies_then_deletes_and_drops_files_row(tmp_path: Path) -> None:
    reg, gp_conn, src, gid, dest = _setup(tmp_path)
    fids = _file_ids(src)
    items = [MoveRequestItem(gid, src.id, fid) for fid in fids.values()]

    result = execute_move_plan(gp_conn, reg, items, dry_run=False,
                               expected_count=None, expected_plan_hash=None)

    assert result["ok"] is True
    assert result["handled"] == 2
    assert not (Path(src.path) / "a.jpg").exists()  # source gone (deleted half of move)
    assert (dest / "a.jpg").exists() and (dest / "b.jpg").exists()  # arrived
    assert _file_ids(src) == {}                     # stale rows dropped
    # A move batch is now undoable.
    assert gp.latest_undoable_move(gp_conn) is not None


def test_count_mismatch_raises(tmp_path: Path) -> None:
    reg, gp_conn, src, gid, dest = _setup(tmp_path)
    items = [MoveRequestItem(gid, src.id, fid) for fid in _file_ids(src).values()]
    with pytest.raises(ValueError, match="Plan changed"):
        execute_move_plan(gp_conn, reg, items, dry_run=False,
                          expected_count=999, expected_plan_hash=None)
    assert (Path(src.path) / "a.jpg").exists()  # guard fired before any move


def test_plan_hash_mismatch_raises(tmp_path: Path) -> None:
    reg, gp_conn, src, gid, dest = _setup(tmp_path)
    items = [MoveRequestItem(gid, src.id, fid) for fid in _file_ids(src).values()]
    with pytest.raises(ValueError, match="Plan contents changed"):
        execute_move_plan(gp_conn, reg, items, dry_run=False,
                          expected_count=None, expected_plan_hash="deadbeef")
    assert (Path(src.path) / "a.jpg").exists()


def test_vanished_file_is_skipped_not_fatal(tmp_path: Path) -> None:
    reg, gp_conn, src, gid, dest = _setup(tmp_path)
    fids = _file_ids(src)
    good = min(fids.values())
    items = [
        MoveRequestItem(gid, src.id, good),
        MoveRequestItem(gid, src.id, 999999),  # never existed
    ]
    result = execute_move_plan(gp_conn, reg, items, dry_run=False,
                               expected_count=None, expected_plan_hash=None)
    assert result["planned"] == 1  # bogus one resolved away, real one still moved
    assert result["ok"] is True


def test_undo_moves_files_back_and_marks_undone(tmp_path: Path) -> None:
    reg, gp_conn, src, gid, dest = _setup(tmp_path)
    items = [MoveRequestItem(gid, src.id, fid) for fid in _file_ids(src).values()]
    execute_move_plan(gp_conn, reg, items, dry_run=False,
                      expected_count=None, expected_plan_hash=None)
    assert (dest / "a.jpg").exists()

    plan = plan_undo(gp_conn, reg)
    assert plan is not None
    assert src.id in plan.involved_libraries  # source library gets locked

    report = execute_undo(gp_conn, plan)
    assert report["ok"] is True
    assert (Path(src.path) / "a.jpg").exists()   # back where it came from
    assert (Path(src.path) / "b.jpg").exists()
    assert not (dest / "a.jpg").exists()         # removed from destination
    # Nothing left to undo, and the batch is marked so it can't be re-undone.
    assert plan_undo(gp_conn, reg) is None
    assert gp.latest_undoable_move(gp_conn) is None


def test_list_aggregated_skips_offline_library(tmp_path: Path) -> None:
    """ADR-0004: one library's drive unmounted (and never migrated off-drive)
    must not 409 the whole cross-library People view — the offline library is
    skipped, the mounted one's people still aggregate."""
    import shutil

    from mediamind.config import library_index_db_path

    reg = LibraryRegistry(registry_path=tmp_path / "libraries.json")
    online, _ = _make_library(reg, tmp_path / "online", {"Mom": ["a.jpg"]})
    offline, _ = _make_library(reg, tmp_path / "offline", {"Dad": ["b.jpg"]})

    # Take the offline library away: drop its off-drive index AND its root, so
    # open_library_db raises LibraryOffline for it (no index, drive gone).
    shutil.rmtree(library_index_db_path(Path(offline.path)).parent)
    shutil.rmtree(offline.path)

    gp_conn = gp.open_global_db()
    people = core.list_aggregated(gp_conn, reg)  # must not raise

    names = {p["name"] for p in people}
    assert "Mom" in names
    assert "Dad" not in names
