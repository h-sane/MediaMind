"""Tests for schema migration (v1 → v2) and duplicates store helpers."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mediamind.core.dedupe import DuplicateFile, DuplicateGroup
from mediamind.store.db import SCHEMA_VERSION, library_db_path, open_db
from mediamind.store.duplicates import (
    StoredScan,
    get_trash_set,
    load_scan,
    mark_members_trashed,
    persist_scan,
    upsert_resolution,
    validate_no_empty_groups,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_image(path: Path, color=(128, 64, 32), size=(64, 64)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def _make_group(root: Path, suffix: str, n: int = 2) -> tuple[DuplicateGroup, list[Path]]:
    paths = []
    files = []
    for i in range(n):
        p = _make_image(root / f"img{suffix}_{i}.jpg")
        paths.append(p)
        files.append(DuplicateFile(
            path=p, size=p.stat().st_size, mtime=p.stat().st_mtime,
            kind="image", content_hash=f"hash{suffix}{i}", width=64, height=64,
            is_best=(i == 0),
        ))
    return DuplicateGroup(files=files, match="exact"), paths


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------

def test_fresh_db_reaches_current_schema_version(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    assert row["value"] == str(SCHEMA_VERSION)


def test_v1_db_migrates_to_v2(tmp_path: Path):
    """Simulate a v1 database (no scan/duplicate tables) and verify migration."""
    db_path = library_db_path(tmp_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Build a minimal v1 db manually.
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL, size INTEGER NOT NULL, mtime REAL NOT NULL,
            content_hash TEXT, decoded_ok INTEGER
        );
        INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1');
    """)
    conn.commit()
    conn.close()

    # open_db should migrate it.
    conn = open_db(db_path)
    version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()["value"]
    assert version == "2"

    # v2 tables must exist.
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "scans" in tables
    assert "duplicate_groups" in tables
    assert "duplicate_members" in tables


def test_migration_is_idempotent(tmp_path: Path):
    """Opening a v2 db a second time must not raise or change the version."""
    conn1 = open_db(library_db_path(tmp_path))
    conn1.close()
    conn2 = open_db(library_db_path(tmp_path))
    row = conn2.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    assert row["value"] == "2"


# ---------------------------------------------------------------------------
# Persist / load round-trip
# ---------------------------------------------------------------------------

def test_persist_and_load_roundtrip(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    group, _ = _make_group(tmp_path, "A")
    now = time.time()

    persist_scan(
        conn, scan_id="scan1", groups=[group], library_root=tmp_path,
        started_at=now, finished_at=now + 1,
        params={"type": "dedupe"}, summary={"groups": 1, "files": 2, "reclaimable_bytes": 100},
    )

    result = load_scan(conn)
    assert result is not None
    assert result.id == "scan1"
    assert len(result.groups) == 1
    assert len(result.groups[0].files) == 2
    assert result.groups[0].files[0].suggested_keep  # is_best → suggested_keep


def test_persist_replaces_previous_scan(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    g1, _ = _make_group(tmp_path, "A")
    g2, _ = _make_group(tmp_path, "B")
    now = time.time()

    persist_scan(conn, "scan1", [g1], tmp_path, now, now + 1, {}, {})
    persist_scan(conn, "scan2", [g2], tmp_path, now + 2, now + 3, {}, {})

    result = load_scan(conn)
    assert result is not None
    assert result.id == "scan2"
    # Old scan must be gone.
    assert conn.execute("SELECT COUNT(*) AS c FROM scans").fetchone()["c"] == 1


def test_load_scan_returns_none_when_empty(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    assert load_scan(conn) is None


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------

def test_upsert_resolution(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    group, _ = _make_group(tmp_path, "R")
    now = time.time()
    persist_scan(conn, "s1", [group], tmp_path, now, now + 1, {}, {})

    members = conn.execute("SELECT id FROM duplicate_members").fetchall()
    mid = members[0]["id"]

    assert upsert_resolution(conn, mid, "trash") is True
    row = conn.execute("SELECT resolution FROM duplicate_members WHERE id = ?", (mid,)).fetchone()
    assert row["resolution"] == "trash"


def test_upsert_resolution_unknown_id_returns_false(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    assert upsert_resolution(conn, 9999, "trash") is False


def test_get_trash_set(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    group, _ = _make_group(tmp_path, "T")
    now = time.time()
    persist_scan(conn, "s1", [group], tmp_path, now, now + 1, {}, {})

    members = conn.execute("SELECT id FROM duplicate_members ORDER BY id").fetchall()
    # Mark one as trash, one as keep.
    upsert_resolution(conn, members[0]["id"], "trash")
    upsert_resolution(conn, members[1]["id"], "keep")

    trash_set = get_trash_set(conn)
    assert len(trash_set) == 1
    assert trash_set[0][0] == members[0]["id"]


def test_null_resolution_not_in_trash_set(tmp_path: Path):
    """Files with resolution=NULL must never appear in the trash set."""
    conn = open_db(library_db_path(tmp_path))
    group, _ = _make_group(tmp_path, "N")
    now = time.time()
    persist_scan(conn, "s1", [group], tmp_path, now, now + 1, {}, {})
    # Don't set any resolution.
    assert get_trash_set(conn) == []


def test_mark_members_trashed(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    group, _ = _make_group(tmp_path, "M")
    now = time.time()
    persist_scan(conn, "s1", [group], tmp_path, now, now + 1, {}, {})

    members = conn.execute("SELECT id FROM duplicate_members").fetchall()
    ids = [m["id"] for m in members]
    mark_members_trashed(conn, ids)

    rows = conn.execute("SELECT resolution FROM duplicate_members").fetchall()
    assert all(r["resolution"] == "trashed" for r in rows)


# ---------------------------------------------------------------------------
# Zero-keeper validation
# ---------------------------------------------------------------------------

def test_validate_no_empty_groups_catches_all_trash(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    group, _ = _make_group(tmp_path, "V")
    now = time.time()
    persist_scan(conn, "s1", [group], tmp_path, now, now + 1, {}, {})

    members = conn.execute("SELECT id FROM duplicate_members").fetchall()
    for m in members:
        upsert_resolution(conn, m["id"], "trash")

    bad = validate_no_empty_groups(conn)
    assert len(bad) == 1


def test_validate_no_empty_groups_passes_when_keeper_exists(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    group, _ = _make_group(tmp_path, "W")
    now = time.time()
    persist_scan(conn, "s1", [group], tmp_path, now, now + 1, {}, {})

    members = conn.execute("SELECT id FROM duplicate_members ORDER BY id").fetchall()
    upsert_resolution(conn, members[0]["id"], "keep")
    upsert_resolution(conn, members[1]["id"], "trash")

    assert validate_no_empty_groups(conn) == []
