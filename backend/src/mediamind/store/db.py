"""Per-library SQLite index.

Lives in `<library>/.mediamind/index.db` so it travels with the folder.
It is a rebuildable cache — the filesystem stays the source of truth, and
deleting the index only means the next scan starts cold.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
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


def open_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
    return conn


def library_db_path(library_data_dir: Path) -> Path:
    return library_data_dir / "index.db"
