"""Cross-library person identity.

Per-library `index.db` files (`store/db.py`) are isolated, rebuildable
caches — deleting one just means the next scan starts cold. A person that
spans multiple libraries is not rebuildable that way: it is pure user
intent (a name, explicit links between local person clusters, and an
optional destination folder). That is exactly the class of state the app
already keeps outside any library, in the app data dir (see
`config.app_data_dir`, `core/libraries.py`'s `libraries.json`,
`core/discovery.py`) — so this store lives there too, in its own small
SQLite database, and never touches any per-library `index.db`.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from mediamind.config import app_data_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS global_persons (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    primary_location TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS global_person_links (
    global_person_id INTEGER NOT NULL REFERENCES global_persons(id) ON DELETE CASCADE,
    library_id TEXT NOT NULL,
    local_person_id INTEGER NOT NULL,
    provider_id TEXT NOT NULL,
    UNIQUE(library_id, local_person_id)
);
CREATE INDEX IF NOT EXISTS idx_global_links_person ON global_person_links(global_person_id);

CREATE TABLE IF NOT EXISTS dismissed_global_links (
    library_id_a TEXT NOT NULL,
    local_person_id_a INTEGER NOT NULL,
    library_id_b TEXT NOT NULL,
    local_person_id_b INTEGER NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (library_id_a, local_person_id_a, library_id_b, local_person_id_b)
);

CREATE TABLE IF NOT EXISTS dismissed_move_suggestions (
    global_person_id INTEGER NOT NULL REFERENCES global_persons(id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (global_person_id, content_hash)
);

CREATE TABLE IF NOT EXISTS global_move_actions (
    id TEXT PRIMARY KEY,
    global_person_id INTEGER NOT NULL,
    dest_folder TEXT NOT NULL,
    file_count INTEGER NOT NULL,
    dry_run INTEGER NOT NULL,
    manifest_path TEXT,
    started_at REAL NOT NULL,
    finished_at REAL,
    ok_count INTEGER,
    error_count INTEGER
);
"""


def global_people_db_path() -> Path:
    return app_data_dir() / "global_people.sqlite3"


def open_global_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or global_people_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


@dataclass(frozen=True)
class GlobalPerson:
    id: int
    name: str
    primary_location: str | None


@dataclass(frozen=True)
class PersonLink:
    library_id: str
    local_person_id: int
    provider_id: str


# ---------------------------------------------------------------------------
# Global persons
# ---------------------------------------------------------------------------

def create_global_person(conn: sqlite3.Connection, name: str) -> int:
    cur = conn.execute(
        "INSERT INTO global_persons (name, primary_location, created_at) VALUES (?, NULL, ?)",
        (name, time.time()),
    )
    conn.commit()
    return cur.lastrowid


def rename_global_person(conn: sqlite3.Connection, global_person_id: int, name: str) -> bool:
    cur = conn.execute(
        "UPDATE global_persons SET name = ? WHERE id = ?", (name, global_person_id)
    )
    conn.commit()
    return cur.rowcount > 0


def get_global_person(conn: sqlite3.Connection, global_person_id: int) -> GlobalPerson | None:
    row = conn.execute(
        "SELECT id, name, primary_location FROM global_persons WHERE id = ?",
        (global_person_id,),
    ).fetchone()
    if row is None:
        return None
    return GlobalPerson(id=row["id"], name=row["name"], primary_location=row["primary_location"])


def list_global_persons(conn: sqlite3.Connection) -> list[GlobalPerson]:
    rows = conn.execute(
        "SELECT id, name, primary_location FROM global_persons ORDER BY name COLLATE NOCASE"
    ).fetchall()
    return [GlobalPerson(id=r["id"], name=r["name"], primary_location=r["primary_location"]) for r in rows]


def set_primary_location(conn: sqlite3.Connection, global_person_id: int, path: str | None) -> bool:
    """Set (or clear, with path=None) a global person's primary physical
    location. This is an ABSOLUTE path, deliberately unlike
    `store.persons.set_primary_folder`'s library-relative one — it may point
    at a folder in a completely different library or an unregistered
    location. Setting it moves nothing by itself; it only marks a
    destination for future move suggestions (see `core/global_moves.py`,
    Phase 6/7)."""
    cur = conn.execute(
        "UPDATE global_persons SET primary_location = ? WHERE id = ?",
        (path, global_person_id),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_global_person(conn: sqlite3.Connection, global_person_id: int) -> bool:
    cur = conn.execute("DELETE FROM global_persons WHERE id = ?", (global_person_id,))
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Links between a global identity and per-library local persons
# ---------------------------------------------------------------------------

def link(
    conn: sqlite3.Connection,
    global_person_id: int,
    library_id: str,
    local_person_id: int,
    provider_id: str,
) -> None:
    """Link a local (per-library) person to a global identity. Idempotent —
    re-linking the same (library_id, local_person_id) just repoints it, since
    that pair is unique per local person (one local person belongs to at
    most one global identity)."""
    conn.execute(
        "DELETE FROM global_person_links WHERE library_id = ? AND local_person_id = ?",
        (library_id, local_person_id),
    )
    conn.execute(
        "INSERT INTO global_person_links (global_person_id, library_id, local_person_id, provider_id) "
        "VALUES (?, ?, ?, ?)",
        (global_person_id, library_id, local_person_id, provider_id),
    )
    conn.commit()


def unlink(conn: sqlite3.Connection, library_id: str, local_person_id: int) -> bool:
    cur = conn.execute(
        "DELETE FROM global_person_links WHERE library_id = ? AND local_person_id = ?",
        (library_id, local_person_id),
    )
    conn.commit()
    return cur.rowcount > 0


def links_for_global(conn: sqlite3.Connection, global_person_id: int) -> list[PersonLink]:
    rows = conn.execute(
        "SELECT library_id, local_person_id, provider_id FROM global_person_links WHERE global_person_id = ?",
        (global_person_id,),
    ).fetchall()
    return [PersonLink(r["library_id"], r["local_person_id"], r["provider_id"]) for r in rows]


def global_for_local(conn: sqlite3.Connection, library_id: str, local_person_id: int) -> int | None:
    row = conn.execute(
        "SELECT global_person_id FROM global_person_links WHERE library_id = ? AND local_person_id = ?",
        (library_id, local_person_id),
    ).fetchone()
    return row["global_person_id"] if row else None


def all_links(conn: sqlite3.Connection) -> list[tuple[int, PersonLink]]:
    """Every (global_person_id, link) pair — used by the aggregation read to
    group local persons by global identity in one query instead of N."""
    rows = conn.execute(
        "SELECT global_person_id, library_id, local_person_id, provider_id FROM global_person_links"
    ).fetchall()
    return [(r["global_person_id"], PersonLink(r["library_id"], r["local_person_id"], r["provider_id"])) for r in rows]


# ---------------------------------------------------------------------------
# Dismissed cross-library link suggestions ("not the same person")
# ---------------------------------------------------------------------------

def dismiss_link_suggestion(
    conn: sqlite3.Connection,
    library_id_a: str,
    local_person_id_a: int,
    library_id_b: str,
    local_person_id_b: int,
) -> None:
    """Normalized so lookup doesn't care which side of the pair the caller
    passes first — same reasoning as `store.persons.dismiss_merge_suggestion`."""
    a = (library_id_a, local_person_id_a)
    b = (library_id_b, local_person_id_b)
    if b < a:
        a, b = b, a
    conn.execute(
        "INSERT OR IGNORE INTO dismissed_global_links "
        "(library_id_a, local_person_id_a, library_id_b, local_person_id_b, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (a[0], a[1], b[0], b[1], time.time()),
    )
    conn.commit()


def dismissed_link_pairs(conn: sqlite3.Connection) -> set[tuple[str, int, str, int]]:
    rows = conn.execute(
        "SELECT library_id_a, local_person_id_a, library_id_b, local_person_id_b FROM dismissed_global_links"
    ).fetchall()
    return {(r["library_id_a"], r["local_person_id_a"], r["library_id_b"], r["local_person_id_b"]) for r in rows}


# ---------------------------------------------------------------------------
# Dismissed physical-move suggestions
# ---------------------------------------------------------------------------

def dismiss_move_suggestion(conn: sqlite3.Connection, global_person_id: int, content_hash: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO dismissed_move_suggestions (global_person_id, content_hash, created_at) "
        "VALUES (?, ?, ?)",
        (global_person_id, content_hash, time.time()),
    )
    conn.commit()


def dismissed_move_hashes(conn: sqlite3.Connection, global_person_id: int) -> set[str]:
    rows = conn.execute(
        "SELECT content_hash FROM dismissed_move_suggestions WHERE global_person_id = ?",
        (global_person_id,),
    ).fetchall()
    return {r["content_hash"] for r in rows}


# ---------------------------------------------------------------------------
# Move-action audit trail (cross-library moves have no single library's
# `organize_actions` table to belong to)
# ---------------------------------------------------------------------------

def record_move_action(
    conn: sqlite3.Connection,
    global_person_id: int,
    dest_folder: str,
    file_count: int,
    dry_run: bool,
    manifest_path: str,
    ok_count: int,
    error_count: int,
) -> str:
    action_id = uuid.uuid4().hex[:12]
    now = time.time()
    conn.execute(
        "INSERT INTO global_move_actions "
        "(id, global_person_id, dest_folder, file_count, dry_run, manifest_path, "
        " started_at, finished_at, ok_count, error_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (action_id, global_person_id, dest_folder, file_count, int(dry_run), manifest_path,
         now, now, ok_count, error_count),
    )
    conn.commit()
    return action_id
