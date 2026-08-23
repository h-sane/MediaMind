"""Store-level tests for the cross-library identity DB (`global_people.sqlite3`).

Pure SQLite behaviour — no libraries, no face model. Each test uses an
isolated `db_path` so nothing touches real app data.
"""

from __future__ import annotations

from pathlib import Path

from mediamind.core.global_people import resolve_link_suggestion
from mediamind.store import global_people as gp


def _open(tmp_path: Path):
    return gp.open_global_db(db_path=tmp_path / "gp.sqlite3")


def test_link_is_idempotent_and_repoints(tmp_path: Path) -> None:
    conn = _open(tmp_path)
    a = gp.create_global_person(conn, "Mom")
    b = gp.create_global_person(conn, "Mum")
    gp.link(conn, a, "lib1", 5, "prov")
    assert gp.global_for_local(conn, "lib1", 5) == a
    # Re-linking the same local person repoints it, never duplicates (the
    # UNIQUE(library_id, local_person_id) invariant).
    gp.link(conn, b, "lib1", 5, "prov")
    assert gp.global_for_local(conn, "lib1", 5) == b
    assert len(gp.links_for_global(conn, a)) == 0
    assert len(gp.links_for_global(conn, b)) == 1


def test_unlink(tmp_path: Path) -> None:
    conn = _open(tmp_path)
    a = gp.create_global_person(conn, "Mom")
    gp.link(conn, a, "lib1", 5, "prov")
    assert gp.unlink(conn, "lib1", 5) is True
    assert gp.global_for_local(conn, "lib1", 5) is None
    assert gp.unlink(conn, "lib1", 5) is False  # already gone


def test_resolve_link_suggestion_prunes_orphan(tmp_path: Path) -> None:
    """Accepting a suggestion repoints B onto A's identity and deletes B's
    now-empty identity — no duplicate single-member person left behind."""
    conn = _open(tmp_path)
    a = gp.create_global_person(conn, "Mom")
    b = gp.create_global_person(conn, "Mom")
    gp.link(conn, a, "lib1", 1, "prov")
    gp.link(conn, b, "lib2", 2, "prov")

    resolve_link_suggestion(conn, "lib1", 1, "lib2", 2, "prov")

    assert gp.global_for_local(conn, "lib1", 1) == a
    assert gp.global_for_local(conn, "lib2", 2) == a
    assert gp.get_global_person(conn, b) is None  # orphan pruned
    assert len(gp.links_for_global(conn, a)) == 2


def test_dismiss_link_pair_is_order_independent(tmp_path: Path) -> None:
    conn = _open(tmp_path)
    gp.dismiss_link_suggestion(conn, "libB", 2, "libA", 1)  # deliberately reversed
    pairs = gp.dismissed_link_pairs(conn)
    # Stored normalized so a lookup with either ordering hits.
    lo, hi = sorted([("libA", 1), ("libB", 2)])
    assert (lo[0], lo[1], hi[0], hi[1]) in pairs


def test_move_suggestion_dismissal(tmp_path: Path) -> None:
    conn = _open(tmp_path)
    gid = gp.create_global_person(conn, "Mom")
    gp.dismiss_move_suggestion(conn, gid, "hash-abc")
    assert gp.dismissed_move_hashes(conn, gid) == {"hash-abc"}
    # Idempotent — a second dismiss doesn't error or duplicate.
    gp.dismiss_move_suggestion(conn, gid, "hash-abc")
    assert gp.dismissed_move_hashes(conn, gid) == {"hash-abc"}


def test_undoable_move_tracking(tmp_path: Path) -> None:
    conn = _open(tmp_path)
    gid = gp.create_global_person(conn, "Mom")

    # A dry run is never undoable.
    gp.record_move_action(conn, gid, "/dest", 3, dry_run=True,
                          manifest_path="/m/dry.csv", ok_count=3, error_count=0)
    assert gp.latest_undoable_move(conn) is None

    # A real move is; its file_count aggregates rows sharing the manifest.
    gp.record_move_action(conn, gid, "/dest", 2, dry_run=False,
                          manifest_path="/m/real.csv", ok_count=2, error_count=0)
    gp.record_move_action(conn, 999, "/dest2", 1, dry_run=False,
                          manifest_path="/m/real.csv", ok_count=1, error_count=0)
    undoable = gp.latest_undoable_move(conn)
    assert undoable is not None
    assert undoable.manifest_path == "/m/real.csv"
    assert undoable.file_count == 3  # 2 + 1 across the two rows

    # Marking it undone flips every row for that manifest, leaving nothing.
    assert gp.mark_manifest_undone(conn, "/m/real.csv") == 2
    assert gp.latest_undoable_move(conn) is None
