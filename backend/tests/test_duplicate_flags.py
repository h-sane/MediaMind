"""Tests for store/duplicate_flags.py (Performance & Ingest V4 Phase 3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediamind.store.db import open_db
from mediamind.store.duplicate_flags import dismiss_flag, flag_duplicate, list_flags


@pytest.fixture
def conn(tmp_path: Path):
    c = open_db(tmp_path / ".mediamind" / "index.db")
    yield c
    c.close()


def _touch(root: Path, rel: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"data")


def test_flag_and_list(tmp_path: Path, conn):
    _touch(tmp_path, "a.jpg")
    _touch(tmp_path, "b.jpg")
    flag_duplicate(conn, "b.jpg", "a.jpg", "exact", "hash123")

    flags = list_flags(conn, tmp_path)
    assert len(flags) == 1
    assert flags[0].path == "b.jpg"
    assert flags[0].match_path == "a.jpg"
    assert flags[0].match_type == "exact"
    assert flags[0].content_hash == "hash123"


def test_near_match_flag(tmp_path: Path, conn):
    _touch(tmp_path, "a.jpg")
    _touch(tmp_path, "b.jpg")
    flag_duplicate(conn, "b.jpg", "a.jpg", "near", None)

    flags = list_flags(conn, tmp_path)
    assert flags[0].match_type == "near"


def test_duplicate_flag_is_idempotent(tmp_path: Path, conn):
    """Unique index on (path, match_path) prevents double-flagging the same pair."""
    _touch(tmp_path, "a.jpg")
    _touch(tmp_path, "b.jpg")
    flag_duplicate(conn, "b.jpg", "a.jpg", "exact", "h")
    flag_duplicate(conn, "b.jpg", "a.jpg", "exact", "h")
    flag_duplicate(conn, "b.jpg", "a.jpg", "exact", "h")

    assert len(list_flags(conn, tmp_path)) == 1


def test_live_dropout_when_flagged_path_deleted(tmp_path: Path, conn):
    _touch(tmp_path, "a.jpg")
    _touch(tmp_path, "b.jpg")
    flag_duplicate(conn, "b.jpg", "a.jpg", "exact", "h")
    assert len(list_flags(conn, tmp_path)) == 1

    (tmp_path / "b.jpg").unlink()
    assert list_flags(conn, tmp_path) == []


def test_live_dropout_when_match_path_deleted(tmp_path: Path, conn):
    _touch(tmp_path, "a.jpg")
    _touch(tmp_path, "b.jpg")
    flag_duplicate(conn, "b.jpg", "a.jpg", "exact", "h")

    (tmp_path / "a.jpg").unlink()
    assert list_flags(conn, tmp_path) == []


def test_dismiss_hides_flag_by_default(tmp_path: Path, conn):
    _touch(tmp_path, "a.jpg")
    _touch(tmp_path, "b.jpg")
    flag_duplicate(conn, "b.jpg", "a.jpg", "exact", "h")
    flag_id = list_flags(conn, tmp_path)[0].id

    assert dismiss_flag(conn, flag_id) is True
    assert list_flags(conn, tmp_path) == []
    # still present when explicitly asked for dismissed ones
    assert len(list_flags(conn, tmp_path, include_dismissed=True)) == 1


def test_dismiss_unknown_flag_returns_false(conn):
    assert dismiss_flag(conn, 999) is False


def test_two_different_matches_for_same_path_both_kept(tmp_path: Path, conn):
    """Unique index is on (path, match_path), not path alone — a file that
    duplicates two different existing files gets two independent flags."""
    _touch(tmp_path, "a.jpg")
    _touch(tmp_path, "c.jpg")
    _touch(tmp_path, "b.jpg")
    flag_duplicate(conn, "b.jpg", "a.jpg", "exact", "h")
    flag_duplicate(conn, "b.jpg", "c.jpg", "near", "h")

    assert len(list_flags(conn, tmp_path)) == 2
