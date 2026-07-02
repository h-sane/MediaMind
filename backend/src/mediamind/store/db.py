"""Per-library SQLite index.

Lives in `<library>/.mediamind/index.db` so it travels with the folder.
It is a rebuildable cache — the filesystem stays the source of truth, and
deleting the index only means the next scan starts cold.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2

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

# Each migration string is idempotent (CREATE TABLE IF NOT EXISTS).
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

_MIGRATIONS: list[tuple[int, str]] = [
    (2, _V2_ADDITIONS),
]


def _apply_migrations(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    current = int(row["value"]) if row else 1
    for target_version, sql in _MIGRATIONS:
        if current < target_version:
            conn.executescript(sql)
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
