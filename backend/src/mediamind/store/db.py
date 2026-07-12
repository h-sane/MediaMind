"""Per-library SQLite index.

Lives in `<library>/.mediamind/index.db` so it travels with the folder.
It is a rebuildable cache — the filesystem stays the source of truth, and
deleting the index only means the next scan starts cold.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

SCHEMA_VERSION = 3

_V1_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,          -- relative to the library root
    kind TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    content_hash TEXT,
    decoded_ok INTEGER
);
CREATE INDEX IF NOT EXISTS idx_files_hash ON files(content_hash);

CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY,
    content_hash TEXT NOT NULL,         -- survives rename/move of the file
    provider_id TEXT NOT NULL,
    vector BLOB NOT NULL,
    dim INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_embeddings_key ON embeddings(content_hash, provider_id);

CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY,
    auto_label TEXT NOT NULL,           -- Person_001 ...
    name TEXT,                          -- user-given; NULL until named
    provider_id TEXT NOT NULL,
    centroid BLOB
);
"""

_V2_ADDITIONS = """
CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    state TEXT NOT NULL,
    params TEXT,
    started_at REAL,
    finished_at REAL,
    summary TEXT
);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id INTEGER PRIMARY KEY,
    scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    match TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dup_groups_scan ON duplicate_groups(scan_id);

CREATE TABLE IF NOT EXISTS duplicate_members (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES duplicate_groups(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    size INTEGER,
    mtime REAL,
    kind TEXT,
    width INTEGER,
    height INTEGER,
    suggested_keep INTEGER NOT NULL DEFAULT 0,
    resolution TEXT
);
CREATE INDEX IF NOT EXISTS idx_dup_members_group ON duplicate_members(group_id);
"""


def _v3_migration(conn: sqlite3.Connection) -> None:
    """Schema v3: bbox columns on embeddings + faces, persons, organize tracking tables."""
    # ALTER TABLE is not idempotent — guard each column addition.
    for col in ("frame_no", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"):
        try:
            conn.execute(f"ALTER TABLE embeddings ADD COLUMN {col} REAL")
        except sqlite3.OperationalError:
            pass  # column already exists

    conn.executescript("""
CREATE TABLE IF NOT EXISTS faces (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    provider_id TEXT NOT NULL,
    frame_no INTEGER NOT NULL DEFAULT 0,
    bbox_x1 REAL NOT NULL DEFAULT 0, bbox_y1 REAL NOT NULL DEFAULT 0,
    bbox_x2 REAL NOT NULL DEFAULT 0, bbox_y2 REAL NOT NULL DEFAULT 0,
    embedding BLOB NOT NULL,
    person_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    confidence REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_faces_file ON faces(file_id);
CREATE INDEX IF NOT EXISTS idx_faces_person ON faces(person_id);
CREATE INDEX IF NOT EXISTS idx_faces_provider ON faces(provider_id);

CREATE TABLE IF NOT EXISTS pending_matches (
    id INTEGER PRIMARY KEY,
    face_id INTEGER NOT NULL REFERENCES faces(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    confidence REAL NOT NULL,
    decision TEXT
);

CREATE TABLE IF NOT EXISTS route_choices (
    file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    decided_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS organize_actions (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    created_at REAL NOT NULL,
    manifest_path TEXT NOT NULL,
    planned INTEGER NOT NULL, handled INTEGER NOT NULL, ok INTEGER NOT NULL,
    dry_run INTEGER NOT NULL DEFAULT 0,
    undone INTEGER NOT NULL DEFAULT 0,
    undo_data TEXT
);

CREATE TABLE IF NOT EXISTS manifest_entries (
    id INTEGER PRIMARY KEY,
    action_id INTEGER NOT NULL REFERENCES organize_actions(id) ON DELETE CASCADE,
    source TEXT NOT NULL, action TEXT NOT NULL,
    destination TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_manifest_action ON manifest_entries(action_id);
""")
    conn.commit()


# v2 is a string; v3 is a callable (ALTER TABLE requires special handling).
_MIGRATIONS: list[tuple[int, str | Callable[[sqlite3.Connection], None]]] = [
    (2, _V2_ADDITIONS),
    (3, _v3_migration),
]


def _apply_migrations(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    current = int(row["value"]) if row else 1
    for target_version, migration in _MIGRATIONS:
        if current < target_version:
            if callable(migration):
                migration(conn)
            else:
                conn.executescript(migration)
            conn.execute(
                "UPDATE meta SET value = ? WHERE key = 'schema_version'",
                (str(target_version),),
            )
            conn.commit()
            current = target_version


def open_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Concurrent jobs (e.g. a dedupe scan and a face scan) each open their own
    # connection to this file. WAL lets readers and the single active writer
    # coexist; the generous busy timeout makes a second writer wait for the
    # other's transaction instead of failing with "database is locked".
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_V1_SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1')",
    )
    conn.commit()
    _apply_migrations(conn)
    return conn


def library_db_path(library_data_dir: Path) -> Path:
    return library_data_dir / "index.db"
