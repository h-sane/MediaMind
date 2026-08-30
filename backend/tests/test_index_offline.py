"""ADR-0004: the per-library index lives off-drive and survives unmount.

Covers the safety-critical bits of `open_library_db`: a fresh library, the
one-time migration of a legacy on-drive index (curated data must not be lost),
and the refusal to fabricate an empty index while the drive is offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mediamind.config import library_index_db_path
from mediamind.store.db import LibraryOffline, library_db_path, open_db, open_library_db


def test_fresh_library_creates_offdrive_index(tmp_path: Path):
    root = tmp_path / "lib"
    root.mkdir()
    conn = open_library_db(root)
    try:
        conn.execute(
            "INSERT INTO persons (id, auto_label, name, provider_id) "
            "VALUES (1, 'Person_001', 'Alice', 'test')"
        )
        conn.commit()
    finally:
        conn.close()
    # Index is in app-data, NOT under the library.
    assert library_index_db_path(root).exists()
    assert not (root / ".mediamind" / "index.db").exists()


def test_legacy_ondrive_index_is_migrated(tmp_path: Path):
    root = tmp_path / "lib"
    legacy = root / ".mediamind" / "index.db"
    seed = open_db(library_db_path(root / ".mediamind"))
    seed.execute(
        "INSERT INTO persons (id, auto_label, name, provider_id) "
        "VALUES (7, 'Person_007', 'Bob', 'test')"
    )
    seed.commit()
    seed.close()
    assert legacy.exists()

    conn = open_library_db(root)
    try:
        name = conn.execute("SELECT name FROM persons WHERE id = 7").fetchone()[0]
    finally:
        conn.close()

    assert name == "Bob"  # curated data survived the move
    assert library_index_db_path(root).exists()
    assert not legacy.exists()  # legacy moved, not copied


def test_offline_unmigrated_refuses_to_fabricate(tmp_path: Path):
    # Drive unmounted (root does not exist) and never migrated: must raise
    # rather than create an empty index that would strand the real one.
    with pytest.raises(LibraryOffline):
        open_library_db(tmp_path / "unmounted")


def test_offline_after_migration_still_opens(tmp_path: Path):
    root = tmp_path / "lib"
    root.mkdir()
    open_library_db(root).close()  # migrate/create while "mounted"

    # Simulate unmount: remove the library root entirely.
    import shutil

    shutil.rmtree(root)
    assert not root.is_dir()

    conn = open_library_db(root)  # off-drive index still reachable
    try:
        assert conn.execute("SELECT 1").fetchone()[0] == 1
    finally:
        conn.close()
