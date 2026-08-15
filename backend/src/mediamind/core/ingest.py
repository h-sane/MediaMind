"""Shared per-file ingest pipeline: index + hash-cache, incremental dedupe
flagging, immediate face matching, thumbnail pre-warm.

`ingest_file` (and its convenience wrapper `ingest_path`) is the one place
that knows how to fully process a single file. The always-on watcher/worker
(a separate, parallel effort — see docs/PERFORMANCE_AND_INGEST_V4_PLAN.md
Phase 2) calls `ingest_path` once per changed file. The two existing
full-folder scans (`core.dedupe.find_duplicates`, `core.faces.scan`) source
their per-file hash/phash caching through this module's `lookup_file_cache`/
`store_file_cache` (the split, thread-pool-safe halves of the same cache —
see the docstring on `hash_and_cache_file` for why they're split) instead of
re-implementing it, while keeping their own walk and finalize step (union-find
for dedupe, DBSCAN for faces) intact — this is one shared per-file body, not a
shared framework.

Ingest never moves or deletes a file. It only writes index rows (`files`,
`embeddings`, `faces`, `pending_matches`, `duplicate_flags`) and warms the
thumbnail cache — CLAUDE.md's "never break user media" / "review before
commit" rules apply to every write here (see `_match_faces_to_existing_persons`
for how the named-person review gate is preserved).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from mediamind.core.faces.engine import extract_file_faces
from mediamind.core.hashing import hash_file
from mediamind.core.scanner import KIND_GIF, KIND_IMAGE, KIND_VIDEO, ScannedFile, kind_of
from mediamind.core.thumbnails import media_thumbnail_jpeg
from mediamind.providers.base import FaceProvider
from mediamind.store import face_assignments
from mediamind.store.duplicate_flags import flag_duplicate
from mediamind.store.embeddings import CachedFace, get_cached_faces, put_cached_faces
from mediamind.store.persons import (
    AUTO_MATCH_THRESHOLD,
    gate_face_match,
    load_person_centroids,
    named_person_ids,
    upsert_file,
)
from mediamind.store.rejected_faces import is_rejected, regions_for

logger = logging.getLogger("mediamind.ingest")

# Matches api/routes/fs.py's /thumbnail route default `size` query param —
# the grid tile size the Explorer/Gallery view actually requests, so a
# pre-warmed cache entry is the one a folder-open request will hit.
DEFAULT_GRID_THUMB_SIZE = 256

# Mirrors core.dedupe.DEFAULT_NEAR_THRESHOLD. Duplicated (not imported) to
# keep this module dependency-free of core.dedupe — dedupe.py imports the
# hash-cache helpers below, and a back-import here would create a cycle.
_NEAR_THRESHOLD = 5


# ---------------------------------------------------------------------------
# Step 1: hash + phash cache (shared by ingest_file, core.dedupe, core.faces.scan)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _HashCache:
    file_id: int
    content_hash: str
    phash: str | None
    was_cached: bool = False


def _phash(path: Path) -> str | None:
    """Perceptual hash as a hex string (DB-storable). None on any decode
    failure — an undecodable image just never gets a near-dup candidate."""
    try:
        import imagehash
        from PIL import Image

        with Image.open(str(path)) as im:
            return str(imagehash.phash(im))
    except Exception:
        return None


def _hex_to_imagehash(hex_str: str):
    try:
        import imagehash

        return imagehash.hex_to_hash(hex_str)
    except Exception:
        return None


def lookup_file_cache(conn: sqlite3.Connection, library_root: Path, scanned: ScannedFile) -> _HashCache | None:
    """DB-read-only cache check: unchanged size+mtime and a real stored
    content_hash (and, for images, a stored phash) means the file's bytes
    haven't changed since it was last hashed — safe to reuse without
    re-reading it. Returns None on a cache miss (new/changed file, or never
    seen before).

    Read-only, so this is safe to call from any thread — but only the one
    thread that owns `conn` for the duration (sqlite3 connections cannot be
    shared across threads). Callers that hash in parallel across a
    ThreadPoolExecutor (core.dedupe.find_duplicates, core.faces.scan) must
    call this only on the thread that opened `conn`, before handing files to
    the pool — see those modules for the split lookup/hash/store pattern.
    """
    rel = scanned.path.relative_to(library_root).as_posix()
    row = conn.execute(
        "SELECT id, size, mtime, content_hash, phash FROM files WHERE path = ?", (rel,)
    ).fetchone()
    if (
        row is not None
        and row["size"] == scanned.size
        and row["mtime"] == scanned.mtime
        and row["content_hash"]
        and (scanned.kind != KIND_IMAGE or row["phash"] is not None)
    ):
        return _HashCache(file_id=row["id"], content_hash=row["content_hash"], phash=row["phash"], was_cached=True)
    return None


def store_file_cache(
    conn: sqlite3.Connection,
    library_root: Path,
    scanned: ScannedFile,
    content_hash: str,
    phash: str | None,
) -> int:
    """DB-write-only: upsert the files row with a freshly computed hash/phash.
    Same single-thread-owns-`conn` constraint as `lookup_file_cache` — callers
    that hashed in a pool must call this back on the connection's own thread."""
    rel = scanned.path.relative_to(library_root).as_posix()
    file_id = upsert_file(conn, rel, scanned.kind, scanned.size, scanned.mtime, content_hash, None, phash=phash)
    conn.commit()
    return file_id


def hash_and_cache_file(conn: sqlite3.Connection, library_root: Path, scanned: ScannedFile) -> _HashCache:
    """Look up the cache and, on a miss, hash + store — one call.

    Only safe for single-file, single-threaded callers (e.g. `ingest_file`,
    invoked once per file by the always-on worker's one thread — see Phase 2).
    NOT safe to call concurrently from a thread pool sharing one connection;
    multi-threaded callers must use `lookup_file_cache`/`store_file_cache`
    directly, split across the pool boundary (see core.dedupe.find_duplicates
    for the pattern).
    """
    cached = lookup_file_cache(conn, library_root, scanned)
    if cached is not None:
        return cached
    content_hash = hash_file(scanned.path)
    phash = _phash(scanned.path) if scanned.kind == KIND_IMAGE else None
    file_id = store_file_cache(conn, library_root, scanned, content_hash, phash)
    return _HashCache(file_id=file_id, content_hash=content_hash, phash=phash, was_cached=False)


# ---------------------------------------------------------------------------
# Step 2 (Phase 3): cheap existing-duplicate lookup
# ---------------------------------------------------------------------------


def _find_existing_match(
    conn: sqlite3.Connection,
    rel: str,
    content_hash: str,
    phash: str | None,
    kind: str,
) -> tuple[str | None, str | None]:
    """Return (match_path, match_type) for an existing `files` row this file
    duplicates, or (None, None). Exact matching covers every media kind
    (mirrors core.dedupe's docstring); near (phash Hamming distance) is
    images only.

    Uses the existing `idx_files_hash` index for the exact lookup — O(1)-ish.
    Near matching is a linear scan of the phash column: cheap here because
    the incremental caller only checks a handful of new files per batch, not
    the whole library (that O(n^2) cost lives in core.dedupe's full scan).
    # ponytail: linear scan of the phash column; swap for a BK-tree only if
    # a library's image count makes even this bite — same upgrade note
    # core.dedupe.py's near-match loop already carries.
    """
    row = conn.execute(
        "SELECT path FROM files WHERE content_hash = ? AND path != ? LIMIT 1",
        (content_hash, rel),
    ).fetchone()
    if row is not None:
        return row["path"], "exact"

    if kind == KIND_IMAGE and phash:
        target = _hex_to_imagehash(phash)
        if target is None:
            return None, None
        for r in conn.execute(
            "SELECT path, phash FROM files WHERE phash IS NOT NULL AND path != ?", (rel,)
        ):
            candidate = _hex_to_imagehash(r["phash"])
            if candidate is None:
                continue
            if target - candidate <= _NEAR_THRESHOLD:
                return r["path"], "near"
    return None, None


# ---------------------------------------------------------------------------
# Step 3 (Phase 4): immediate match-to-existing-person (no DBSCAN)
# ---------------------------------------------------------------------------


def _best_person(embedding: np.ndarray, persons: dict[int, np.ndarray]) -> tuple[int | None, float]:
    """argmax cosine similarity against every existing person centroid,
    clearing AUTO_MATCH_THRESHOLD — mirrors persist_face_scan's per-cluster
    matching (store/persons.py), applied per-face instead of per-cluster."""
    best_pid: int | None = None
    best_sim = AUTO_MATCH_THRESHOLD
    for pid, centroid in persons.items():
        sim = float(np.dot(embedding, centroid))
        if sim > best_sim:
            best_sim = sim
            best_pid = pid
    return best_pid, best_sim


def _was_rejected(conn: sqlite3.Connection, content_hash: str, frame_no: int, person_id: int) -> bool:
    """Same rejected-pairs check persist_face_scan does before re-staging a
    pending match — a user's "not this person" must survive here too."""
    row = conn.execute(
        """
        SELECT 1
        FROM pending_matches pm
        JOIN faces f ON f.id = pm.face_id
        JOIN files fi ON fi.id = f.file_id
        WHERE pm.decision = 'rejected' AND fi.content_hash = ? AND f.frame_no = ? AND pm.person_id = ?
        LIMIT 1
        """,
        (content_hash, frame_no, person_id),
    ).fetchone()
    return row is not None


def _match_faces_to_existing_persons(
    conn: sqlite3.Connection,
    file_id: int,
    content_hash: str,
    faces: list[CachedFace],
    provider_id: str,
) -> tuple[int, int]:
    """Match each of this file's faces against existing person centroids —
    no DBSCAN (that stays a whole-library batch operation; see
    core.faces.scan's cluster_and_persist). A face matching nobody is stored
    with person_id=NULL and picked up by the next full scan's DBSCAN pass.

    Guarded to run only the first time a file gets faces rows for this
    provider (`file_ids_with_faces`-style check): a file that already has
    faces rows was already handled either by this path or by a full scan's
    persist_face_scan, and re-running here would either duplicate its faces
    rows or silently blow away an already-decided pending_matches row (which
    persist_face_scan's wipe-and-rebuild is careful to preserve via its
    rejected-pairs snapshot — a single-file path isn't set up to replicate
    that machinery, so it simply defers a content change on an
    already-scanned file to the next full scan instead, the documented
    incremental-path backstop).

    Returns (new_faces, pending_faces).
    """
    if not faces:
        return 0, 0
    already_done = conn.execute(
        "SELECT 1 FROM faces WHERE file_id = ? AND provider_id = ? LIMIT 1",
        (file_id, provider_id),
    ).fetchone()
    if already_done is not None:
        return 0, 0

    persons = load_person_centroids(conn, provider_id)
    named = named_person_ids(conn, provider_id)

    new_faces = 0
    pending_faces = 0
    for f in faces:
        pid, sim = _best_person(f.embedding, persons)
        was_rejected = pid is not None and _was_rejected(conn, content_hash, f.frame_no, pid)
        decision = gate_face_match(pid, named, pending_for_named=True, was_rejected=was_rejected)

        embedding_blob = np.asarray(f.embedding, dtype=np.float32).tobytes()
        cur = conn.execute(
            """
            INSERT INTO faces
              (file_id, provider_id, frame_no, bbox_x1, bbox_y1, bbox_x2, bbox_y2,
               embedding, person_id, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_id, provider_id, f.frame_no,
                f.bbox[0], f.bbox[1], f.bbox[2], f.bbox[3],
                embedding_blob, decision.person_id,
                sim if pid is not None else 0.0,
            ),
        )
        face_id = cur.lastrowid
        new_faces += 1

        if decision.pending_person_id is not None:
            conn.execute(
                "INSERT INTO pending_matches (face_id, person_id, confidence) VALUES (?, ?, ?)",
                (face_id, decision.pending_person_id, sim),
            )
            pending_faces += 1
        elif decision.record_assignment and decision.person_id is not None:
            face_assignments.record_assignment(
                conn, content_hash, provider_id, f.bbox, decision.person_id, source="cluster",
            )

    conn.commit()
    return new_faces, pending_faces


def _detect_and_cache(
    conn: sqlite3.Connection,
    scanned: ScannedFile,
    rel: str,
    content_hash: str,
    provider: FaceProvider,
    provider_id: str,
) -> list[CachedFace]:
    """Cache-miss path: run the provider once, persist to the embeddings
    cache, update decoded_ok. Mirrors core.faces.scan's detect_batch
    cache-miss branch (that branch stays as its own inline implementation
    there — it's already routed through this same shared embeddings.py
    cache, and needs its own FileFaces/counter bookkeeping for the batch
    clustering handoff, so extracting a further-shared function buys little)."""
    provider.prepare()
    mf = extract_file_faces(scanned, provider)
    cached_faces = [
        CachedFace(frame_no=fr.frame_no, bbox=fr.bbox, embedding=fr.embedding) for fr in mf.faces
    ]
    if mf.decoded_ok:
        put_cached_faces(conn, content_hash, provider_id, cached_faces)
    try:
        upsert_file(conn, rel, scanned.kind, scanned.size, scanned.mtime, content_hash, mf.decoded_ok)
        conn.commit()
    except Exception:
        pass

    regions = regions_for(conn, content_hash, provider_id)
    return [cf for cf in cached_faces if not is_rejected(regions, cf.bbox)]


# ---------------------------------------------------------------------------
# The shared per-file pipeline
# ---------------------------------------------------------------------------


@dataclass
class IngestOutcome:
    file_id: int | None
    content_hash: str | None
    was_cached: bool          # skipped hashing (unchanged file)
    duplicate_of: str | None  # rel-path of an existing matching file, if any
    match_type: str | None    # "exact" | "near"
    new_faces: int
    pending_faces: int        # staged into pending_matches (named-person gate)


_EMPTY_OUTCOME = IngestOutcome(
    file_id=None, content_hash=None, was_cached=False,
    duplicate_of=None, match_type=None, new_faces=0, pending_faces=0,
)


def ingest_file(
    conn: sqlite3.Connection,
    library_root: Path,
    scanned: ScannedFile,
    *,
    provider: FaceProvider | None = None,
    provider_id: str | None = None,
    warm_thumbnail: bool = True,
) -> IngestOutcome:
    """Index, hash (cached), dedupe-check, face-match, and thumbnail-warm one
    file. Never raises — one bad file must never crash a batch (per-step
    fault isolation, matching the project's existing scan pattern).

    Writes only DB index rows and the thumbnail cache; never touches the
    file itself.
    """
    try:
        cache = hash_and_cache_file(conn, library_root, scanned)
    except Exception:
        logger.warning("ingest: failed to hash %s", scanned.path, exc_info=True)
        return _EMPTY_OUTCOME

    rel = scanned.path.relative_to(library_root).as_posix()

    duplicate_of: str | None = None
    match_type: str | None = None
    if scanned.is_media:
        try:
            duplicate_of, match_type = _find_existing_match(
                conn, rel, cache.content_hash, cache.phash, scanned.kind
            )
            if duplicate_of:
                flag_duplicate(conn, rel, duplicate_of, match_type, cache.content_hash)
        except Exception:
            logger.warning("ingest: dedupe check failed for %s", scanned.path, exc_info=True)

    new_faces = pending_faces = 0
    if provider_id and scanned.kind in (KIND_IMAGE, KIND_GIF, KIND_VIDEO):
        try:
            faces = get_cached_faces(conn, cache.content_hash, provider_id)
            if faces is None:
                if provider is None:
                    faces = []
                else:
                    faces = _detect_and_cache(conn, scanned, rel, cache.content_hash, provider, provider_id)
            if faces:
                new_faces, pending_faces = _match_faces_to_existing_persons(
                    conn, cache.file_id, cache.content_hash, faces, provider_id
                )
        except Exception:
            logger.warning("ingest: face step failed for %s", scanned.path, exc_info=True)

    if warm_thumbnail and scanned.kind in (KIND_IMAGE, KIND_GIF, KIND_VIDEO):
        try:
            media_thumbnail_jpeg(scanned.path, scanned.kind, DEFAULT_GRID_THUMB_SIZE)
        except Exception:
            logger.warning("ingest: thumbnail warm failed for %s", scanned.path, exc_info=True)

    return IngestOutcome(
        file_id=cache.file_id,
        content_hash=cache.content_hash,
        was_cached=cache.was_cached,
        duplicate_of=duplicate_of,
        match_type=match_type,
        new_faces=new_faces,
        pending_faces=pending_faces,
    )


def ingest_path(
    conn: sqlite3.Connection,
    library_root: Path,
    abs_path: Path,
    *,
    provider: FaceProvider | None = None,
    provider_id: str | None = None,
    warm_thumbnail: bool = True,
) -> IngestOutcome:
    """Stat a single absolute path into a ScannedFile and ingest it.

    Entry point for external callers (the always-on watcher/worker) — they
    never construct ScannedFile themselves. FROZEN SIGNATURE: a parallel
    effort (core/ingest_worker.py) calls this exact signature — do not change it.
    """
    abs_path = Path(abs_path)
    try:
        stat = abs_path.stat()
    except OSError:
        return _EMPTY_OUTCOME
    scanned = ScannedFile(path=abs_path, kind=kind_of(abs_path), size=stat.st_size, mtime=stat.st_mtime)
    return ingest_file(
        conn, library_root, scanned,
        provider=provider, provider_id=provider_id, warm_thumbnail=warm_thumbnail,
    )
