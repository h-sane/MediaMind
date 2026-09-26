"""Per-library SQLite index.

Lives OFF the library drive, in app-data (`config.library_index_db_path`), so
the People view / catalog survive the library's drive (Cryptomator, cloud,
removable) unmounting — ADR-0004. It is mostly a rebuildable cache (the
filesystem stays the source of truth), but it also holds curated data — person
names, rejections, folder bindings — that a rescan cannot reconstruct, which is
why `open_library_db` migrates the pre-ADR-0004 on-drive index instead of
letting it be silently recreated empty.
"""

from __future__ import annotations

import shutil
import sqlite3
import threading
from pathlib import Path
from typing import Callable

from mediamind.config import LIBRARY_DATA_DIRNAME, library_index_db_path
from mediamind.core.reachability import is_root_reachable

SCHEMA_VERSION = 13

# Two connections racing to create/migrate the SAME brand-new database file
# (e.g. the always-on ingest worker and an HTTP request, opening within
# milliseconds of a library's first registration) can hit "database is
# locked" on the first-ever WAL transition even with busy_timeout set —
# SQLite's busy handler doesn't reliably cover that specific transition.
# A per-process lock keyed by path serializes just the create/migrate step
# (not queries afterward) — cheap, and sufficient since this app only ever
# runs as one process.
_creation_locks: dict[str, threading.Lock] = {}
_creation_locks_guard = threading.Lock()


def _creation_lock(db_path: Path) -> threading.Lock:
    key = str(db_path)
    with _creation_locks_guard:
        lock = _creation_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _creation_locks[key] = lock
        return lock

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


def _v4_migration(conn: sqlite3.Connection) -> None:
    """Schema v4: cross-scan duplicate-group dismissals (Save configuration)."""
    for col, ddl in (
        ("content_hash", "ALTER TABLE duplicate_members ADD COLUMN content_hash TEXT"),
        ("ignored_at", "ALTER TABLE duplicate_groups ADD COLUMN ignored_at REAL"),
    ):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass  # column already exists

    conn.executescript("""
CREATE TABLE IF NOT EXISTS dedupe_dismissals (
    id INTEGER PRIMARY KEY,
    signature TEXT NOT NULL UNIQUE,
    match TEXT NOT NULL,
    file_count INTEGER NOT NULL,
    dismissed_at REAL NOT NULL
);
""")
    conn.commit()


def _v5_migration(conn: sqlite3.Connection) -> None:
    """Schema v5: folder-binding detection (Phase B — respect pre-existing
    person/group subfolders instead of bulldozing them into People/)."""
    conn.executescript("""
CREATE TABLE IF NOT EXISTS folder_bindings (
    id INTEGER PRIMARY KEY,
    folder_rel TEXT NOT NULL UNIQUE,    -- bound folder, relative to library root (posix)
    kind TEXT NOT NULL,                 -- 'person' | 'group'
    provider_id TEXT NOT NULL,
    accepted_outlier_file_ids TEXT NOT NULL DEFAULT '[]',  -- JSON array of files.id explicitly approved to move
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS folder_binding_members (
    id INTEGER PRIMARY KEY,
    binding_id INTEGER NOT NULL REFERENCES folder_bindings(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE
);
-- One-folder-per-person: a person can be a member of at most one binding.
CREATE UNIQUE INDEX IF NOT EXISTS idx_binding_members_person ON folder_binding_members(person_id);
CREATE INDEX IF NOT EXISTS idx_binding_members_binding ON folder_binding_members(binding_id);

CREATE TABLE IF NOT EXISTS binding_suggestions (
    id INTEGER PRIMARY KEY,
    folder_rel TEXT NOT NULL,
    kind TEXT NOT NULL,                 -- 'person' | 'group'
    provider_id TEXT NOT NULL,
    file_count INTEGER NOT NULL,
    coverage REAL NOT NULL,
    person_ids TEXT NOT NULL,           -- JSON array of person ids, ranked
    outlier_file_ids TEXT NOT NULL DEFAULT '[]',  -- JSON array of files.id
    status TEXT NOT NULL DEFAULT 'pending',       -- pending | accepted | dismissed
    created_at REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_binding_suggestions_folder
    ON binding_suggestions(folder_rel, provider_id);
""")
    conn.commit()


def _v6_migration(conn: sqlite3.Connection) -> None:
    """Schema v6: manual "not a face" rejection (Phase D — background/object
    false positives). Keyed by content_hash (survives rename/move) + provider_id
    + bbox rather than faces.id, since faces rows get wiped and recreated wholesale
    on every rescan (see persist_face_scan) — a rejection must outlive that."""
    conn.executescript("""
CREATE TABLE IF NOT EXISTS rejected_face_regions (
    id INTEGER PRIMARY KEY,
    content_hash TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    bbox_x1 REAL NOT NULL, bbox_y1 REAL NOT NULL, bbox_x2 REAL NOT NULL, bbox_y2 REAL NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rejected_face_regions_key
    ON rejected_face_regions(content_hash, provider_id);
""")
    conn.commit()


def _v7_migration(conn: sqlite3.Connection) -> None:
    """Schema v7: person-scoped file rejections. A user reviewing a
    folder-match/materialize batch can say "not this person" about a specific
    file; that decision must survive the wholesale faces-row rebuild every
    rescan does (see persist_face_scan), so it's keyed by content_hash (not
    faces.id) same as rejected_face_regions — but additionally scoped to
    person_id, since this is "not this person" (a real face, wrong person),
    not "not a face at all". Consulted by organize_plan.py so a rejected
    file is never auto-routed into that person's bound folder."""
    conn.executescript("""
CREATE TABLE IF NOT EXISTS rejected_person_files (
    id INTEGER PRIMARY KEY,
    content_hash TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    person_id INTEGER NOT NULL,
    created_at REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rejected_person_files_key
    ON rejected_person_files(content_hash, provider_id, person_id);
""")
    conn.commit()


def _v8_migration(conn: sqlite3.Connection) -> None:
    """Schema v8: durable per-face person assignments (Phase 1 of the
    faces/organize audit — eliminates identity churn on rescan). Once a face
    is confidently assigned to a person — by clustering or by explicit user
    action — that assignment is recorded here so `persist_face_scan` can
    re-attach it directly on every future rescan instead of re-deriving
    identity from scratch, where a split/merged cluster could silently
    reassign or hijack it. Keyed the same way as rejected_face_regions/
    rejected_person_files (content_hash + provider_id, matched by IOU on
    bbox) since faces rows are wiped and recreated wholesale every rescan."""
    conn.executescript("""
CREATE TABLE IF NOT EXISTS face_assignments (
    id INTEGER PRIMARY KEY,
    content_hash TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    bbox_x1 REAL NOT NULL, bbox_y1 REAL NOT NULL, bbox_x2 REAL NOT NULL, bbox_y2 REAL NOT NULL,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    source TEXT NOT NULL,                -- 'cluster' | 'user'
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_face_assignments_key ON face_assignments(content_hash, provider_id);
CREATE INDEX IF NOT EXISTS idx_face_assignments_person ON face_assignments(person_id);
""")
    conn.commit()


def _v9_migration(conn: sqlite3.Connection) -> None:
    """Schema v9: durable "not the same person" dismissals for the merge-
    suggestion strip. Unlike faces/rejections (which key off content_hash
    because faces rows are wiped and recreated every rescan), persons.id
    itself is the reconciled, largely-stable identity persist_face_scan
    maintains across rescans (a matched cluster keeps its existing person
    row; only an unmatched/renamed identity churns) — same assumption every
    other person_id-keyed table here already makes (folder bindings, face
    assignments' person_id). Cascade-deletes with the person row it
    references, so a stale dismissal for a person that no longer exists is
    just gone, never a dangling row an app has to filter out."""
    conn.executescript("""
CREATE TABLE IF NOT EXISTS dismissed_merge_suggestions (
    id INTEGER PRIMARY KEY,
    person_a_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    person_b_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    created_at REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dismissed_merge_suggestions_pair
    ON dismissed_merge_suggestions(person_a_id, person_b_id);
""")
    conn.commit()


def _v10_migration(conn: sqlite3.Connection) -> None:
    """Schema v10: incremental ingest pipeline (Performance & Ingest V4
    Phase 1/3). `files.phash` caches each image's perceptual hash so a
    rescan/incremental ingest can skip recomputing it for an unchanged file
    (mirrors content_hash's existing role). `duplicate_flags` records the
    advisory "this newly-ingested file matches an existing one" notices the
    always-on ingest worker raises without running the full Dedupe tool scan
    — resolution still goes through that tool's existing manifest-audited
    execute path; a flag never triggers deletion on its own."""
    try:
        conn.execute("ALTER TABLE files ADD COLUMN phash TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists

    conn.executescript("""
CREATE TABLE IF NOT EXISTS duplicate_flags (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,              -- the newly-ingested file (rel to root)
    match_path TEXT NOT NULL,        -- existing file it duplicates ("show matching location")
    match_type TEXT NOT NULL,        -- 'exact' | 'near'
    content_hash TEXT,
    flagged_at REAL NOT NULL,
    dismissed INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dup_flags_path ON duplicate_flags(path, match_path);
""")
    conn.commit()


def _v11_migration(conn: sqlite3.Connection) -> None:
    """Schema v11: per-person "primary folder" — a user-designated destination
    a person's matched files can be routed into directly (organize_plan.py's
    `target_override`), independent of the default People/<name> convention
    and of any folder binding. NULL means unset (no override yet)."""
    try:
        conn.execute("ALTER TABLE persons ADD COLUMN primary_folder_path TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()


def _v12_migration(conn: sqlite3.Connection) -> None:
    """Schema v12: files a scan could not process (kept, with the reason, so the
    user can see and label them by hand) and those hand labels. Both key on the
    library-relative path because a file that never finished hashing has no
    `files` row."""
    conn.executescript("""
CREATE TABLE IF NOT EXISTS unprocessed_files (
    path TEXT PRIMARY KEY,           -- library-relative
    kind TEXT NOT NULL,
    size INTEGER NOT NULL,
    reason TEXT NOT NULL,            -- read_timeout | decode_timeout | read_error | decode_failed
    message TEXT NOT NULL,           -- one plain sentence for the user
    attempts INTEGER NOT NULL DEFAULT 1,
    last_scan_id TEXT,
    failed_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS manual_tags (
    path TEXT NOT NULL,              -- library-relative
    person_id INTEGER NOT NULL,
    tagged_at REAL NOT NULL,
    PRIMARY KEY (path, person_id)
);
""")
    conn.commit()


def _v13_migration(conn: sqlite3.Connection) -> None:
    """Schema v13: a "No" in review ("this face is not this person") that survives rescans.
    pending_matches holds the decision against a faces.id, and every rescan recreates the
    faces rows, so the No was forgotten and the question came back. Keyed like
    face_assignments (content hash + provider + bbox, matched by IoU)."""
    conn.executescript("""
CREATE TABLE IF NOT EXISTS rejected_matches (
    id INTEGER PRIMARY KEY,
    content_hash TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    bbox_x1 REAL NOT NULL, bbox_y1 REAL NOT NULL, bbox_x2 REAL NOT NULL, bbox_y2 REAL NOT NULL,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rejected_matches_key ON rejected_matches(content_hash, provider_id);
""")
    conn.commit()


# v2 is a string; v3+ are callables (ALTER TABLE requires special handling).
_MIGRATIONS: list[tuple[int, str | Callable[[sqlite3.Connection], None]]] = [
    (2, _V2_ADDITIONS),
    (3, _v3_migration),
    (4, _v4_migration),
    (5, _v5_migration),
    (6, _v6_migration),
    (7, _v7_migration),
    (8, _v8_migration),
    (9, _v9_migration),
    (10, _v10_migration),
    (11, _v11_migration),
    (12, _v12_migration),
    (13, _v13_migration),
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
    conn.execute("PRAGMA foreign_keys = ON")
    # Serialize first-time WAL transition + schema/migration against any other
    # connection racing to create the same brand-new file (see _creation_lock).
    with _creation_lock(db_path):
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(_V1_SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1')",
        )
        conn.commit()
        _apply_migrations(conn)
    return conn


def library_db_path(library_data_dir: Path) -> Path:
    """Index path *inside a given dir*. Retained as a plain path helper (used by
    tests and the legacy-migration lookup); production opens the index through
    `open_library_db`, which relocates it off-drive."""
    return library_data_dir / "index.db"


class LibraryOffline(RuntimeError):
    """The library's drive is unmounted and it has no off-drive index yet (never
    opened while mounted since ADR-0004). Raised instead of fabricating an empty
    index, which on remount would strand the real on-drive one (and its curated
    person data). The API maps this to HTTP 409 so the UI can badge "offline".
    """


def _migrate_legacy_index(legacy: Path, dest: Path) -> None:
    """One-time move of a pre-ADR-0004 on-drive index into app-data. Checkpoints
    the WAL first so no committed writes are left in a sidecar, copies to the
    destination, verifies the byte count, then deletes the legacy files. Copy
    (not rename) because source and dest are on different volumes; delete only
    after a verified copy so an interrupted migration retries cleanly."""
    conn = sqlite3.connect(legacy)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".migrating")
    shutil.copy2(legacy, tmp)
    if tmp.stat().st_size != legacy.stat().st_size:
        tmp.unlink(missing_ok=True)
        raise OSError(f"index migration size mismatch for {legacy}")
    tmp.replace(dest)
    for p in (legacy, legacy.with_name(legacy.name + "-wal"), legacy.with_name(legacy.name + "-shm")):
        try:
            p.unlink()
        except OSError:
            pass


def open_library_db(library_root: Path) -> sqlite3.Connection:
    """Open a library's index off-drive (ADR-0004). On first access, migrates a
    pre-ADR-0004 on-drive `<root>/.mediamind/index.db` into app-data. If the
    index has never been migrated and the drive is currently offline, raises
    `LibraryOffline` rather than creating an empty index that could strand the
    real one on remount. Does not touch `<root>/.mediamind`, so a mounted-drive
    read no longer depends on the drive being writable."""
    dest = library_index_db_path(library_root)
    if not dest.exists():
        legacy = library_root / LIBRARY_DATA_DIRNAME / "index.db"
        try:
            legacy_exists = legacy.exists()
        except OSError:
            legacy_exists = False
        if legacy_exists:
            _migrate_legacy_index(legacy, dest)
        elif not is_root_reachable(library_root):
            raise LibraryOffline(str(library_root))
    return open_db(dest)
