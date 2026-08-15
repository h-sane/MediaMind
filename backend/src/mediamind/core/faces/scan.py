"""Face scan pipeline: hash → cache-or-detect → cluster → persist.

Mirrors _make_dedupe_runner's shape from api/routes/scans.py.
Per-file commits to the embedding cache mean a cancelled scan can be resumed:
on the next run, only files not yet in the cache need re-detection.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import numpy as np

from mediamind.core.concurrency import TIMED_OUT, hash_timeout_for, run_with_timeout
from mediamind.core.faces.clustering import DEFAULT_EPS, DEFAULT_MIN_SAMPLES, cluster_embeddings
from mediamind.core.faces.engine import (
    DEFAULT_GIF_FRAMES,
    DEFAULT_MIN_FACE_SIZE,
    DEFAULT_VIDEO_FRAMES,
    extract_file_faces,
)
from mediamind.core.hashing import hash_file
from mediamind.core.ingest import lookup_file_cache, store_file_cache
from mediamind.core.jobs import JobContext
from mediamind.core.scanner import KIND_VIDEO, ScannedFile, scan_folder
from mediamind.config import library_data_dir
from mediamind.providers.base import FaceProvider
from mediamind.store.db import library_db_path, open_db
from mediamind.store.embeddings import CachedFace, get_cached_faces, put_cached_faces
from mediamind.store.persons import FileFaces, file_ids_with_faces, persist_face_scan, upsert_file
from mediamind.store.rejected_faces import is_rejected, regions_for

logger = logging.getLogger("mediamind.faces.scan")

# hash_file() has no cooperative cancellation point (a blocking read()) — on a
# stalled network/encrypted-drive mount (e.g. a Cryptomator vault gone
# unresponsive) it can hang forever with no exception to catch, freezing the
# whole scan on file #1 with no progress and no error. Mirrors dedupe.py's
# identical guard around the same hash_file() call. This is a floor, not a
# flat cap — hash_timeout_for() scales it up for large files (see below).
DEFAULT_HASH_TIMEOUT_SECONDS = 30.0
MAX_LEAKED_STALL_THREADS = 64

# Hashing is I/O-bound (hash_file releases the GIL during reads), so
# oversubscribing cores pays off — mirrors dedupe.py's find_duplicates()
# identical constant/rationale (F15's hashing half; detection itself stays
# sequential, see detect_batch's docstring for why).
_HASH_WORKERS = min(8, (os.cpu_count() or 4) * 2)

# Same throttle as _make_dedupe_runner's — logging every tick would flood the
# dev log on a large scan; this is just frequent enough to prove the walk is
# alive on a slow mount.
_LOG_INTERVAL_SECONDS = 2.0

# A folder with even one large video would otherwise make the user wait
# through decoding/hashing it before seeing *any* result. Videos at or above
# this size are deferred to a second pass that runs after the fast pass
# (everything else) is already hashed, detected, and persisted — so results
# are reviewable immediately and the slow videos finish in the background.
# ponytail: size is a proxy for "slow to process", not duration — good enough
# since size and video length correlate for a given codec/resolution; swap
# for an actual duration probe if this proxy turns out to be too coarse.
SLOW_VIDEO_BYTES = 200 * 1024 * 1024


def make_face_scan_runner(
    library_root: Path,
    provider_factory: Callable[[], FaceProvider],
    provider_id: str,
    *,
    eps: float = DEFAULT_EPS,
    pending_for_named: bool = False,
    video_frames: int = DEFAULT_VIDEO_FRAMES,
    gif_frames: int = DEFAULT_GIF_FRAMES,
    min_face_size: int = DEFAULT_MIN_FACE_SIZE,
) -> Callable[[JobContext], dict]:
    """Return a face-scan runner for JobManager."""

    def runner(ctx: JobContext) -> dict:
        started_at = time.time()
        ctx.report_progress(0, 0, "scanning")
        logger.info("Face scan: walking %s", library_root)

        # scan_folder()'s walk + per-file stat pass can take minutes on a
        # slow network/encrypted-drive mount (each file is a guarded,
        # individually-timed-out syscall — see core/scanner.py). Without
        # wiring its on_walk/on_stat callbacks through, this whole phase
        # reported nothing: the UI sat frozen on "Scanning folders" with no
        # way to tell a live-but-slow walk apart from a genuinely hung one.
        # Mirrors _make_dedupe_runner's identical wiring in api/routes/scans.py.
        last_log = 0.0

        def _throttled_log(msg: str, *args: object) -> None:
            nonlocal last_log
            now = time.monotonic()
            if now - last_log >= _LOG_INTERVAL_SECONDS:
                last_log = now
                logger.info(msg, *args)

        def on_walk(n: int) -> None:
            if ctx.cancelled():
                return
            ctx.report_progress(n, 0, "scanning")
            _throttled_log("Face scan: %d files found so far…", n)

        def on_stat(done: int, total_walked: int) -> None:
            if ctx.cancelled():
                return
            ctx.report_progress(done, total_walked, "reading")
            _throttled_log("Face scan: read details for %d/%d files…", done, total_walked)

        scanned_files = list(
            scan_folder(library_root, on_walk=on_walk, on_stat=on_stat, should_cancel=ctx.cancelled)
        )
        total = len(scanned_files)
        if ctx.cancelled():
            return {}
        logger.info("Face scan: %d files found — detecting faces", total)

        # Large videos go through a second pass (see SLOW_VIDEO_BYTES) so the
        # fast pass's results are reviewable without waiting on them.
        fast_files: list[ScannedFile] = []
        slow_files: list[ScannedFile] = []
        for f in scanned_files:
            (slow_files if f.kind == KIND_VIDEO and f.size >= SLOW_VIDEO_BYTES else fast_files).append(f)

        data_dir = library_data_dir(library_root)
        conn = open_db(library_db_path(data_dir))
        provider: FaceProvider | None = None
        hash_limiter = threading.Semaphore(MAX_LEAKED_STALL_THREADS)

        try:
            existing_file_ids = file_ids_with_faces(conn, provider_id)

            file_ids: list[int | None] = []
            content_hashes: list[str | None] = []
            file_faces_list: list[FileFaces] = []
            no_face_files = 0
            unreadable_files = 0

            def _hash_one(scanned: ScannedFile) -> object | None:
                """Just the I/O-bound read+hash — no DB access, so this is
                safe to run from a worker thread. Returns TIMED_OUT, a
                content-hash string, or None (stat/hash failure)."""
                try:
                    stat = scanned.path.stat()
                    return run_with_timeout(
                        lambda p=scanned.path: hash_file(p),
                        hash_timeout_for(stat.st_size, floor=DEFAULT_HASH_TIMEOUT_SECONDS),
                        hash_limiter,
                    )
                except Exception:
                    return None

            def hash_batch(batch: list[ScannedFile]) -> bool:
                """Hash a batch in parallel (mirrors dedupe.py's
                find_duplicates() — hash_file releases the GIL during reads,
                so oversubscribing cores pays off), then upsert the results
                serially on the single sqlite connection: sqlite3 connections
                aren't safe for concurrent access from multiple threads, so
                all DB access (both the cache lookup below and the write-back
                after hashing) stays on this thread even though the slow part
                (disk I/O) runs concurrently. Returns False if cancelled
                partway through either phase.

                An unchanged file (same size+mtime, already-cached hash) skips
                hash_file() entirely via core.ingest's persisted files cache —
                this is what makes rescanning a large library for faces cheap
                (Performance & Ingest V4 Phase 1); a changed/new file still
                goes through the stall-timeout-guarded pool exactly as before.
                """
                base = len(file_ids)
                # Cache lookups are DB reads — this thread only, before any
                # file reaches the pool (see docstring above).
                cached_by_idx: dict[int, object] = {}
                to_hash: list[int] = []
                for i, scanned in enumerate(batch):
                    cached = lookup_file_cache(conn, library_root, scanned)
                    if cached is not None:
                        cached_by_idx[i] = cached
                    else:
                        to_hash.append(i)

                hash_results: dict[int, object] = {}
                if to_hash:
                    with ThreadPoolExecutor(max_workers=_HASH_WORKERS) as pool:
                        futures = {pool.submit(_hash_one, batch[i]): i for i in to_hash}
                        done = 0
                        for fut in as_completed(futures):
                            hash_results[futures[fut]] = fut.result()
                            done += 1
                            ctx.report_progress(base + len(cached_by_idx) + done, total, "hashing")
                            if ctx.cancelled():
                                for pending in futures:
                                    pending.cancel()
                                return False
                elif cached_by_idx:
                    ctx.report_progress(base + len(cached_by_idx), total, "hashing")

                for i, scanned in enumerate(batch):
                    if i in cached_by_idx:
                        cached = cached_by_idx[i]
                        file_ids.append(cached.file_id)
                        content_hashes.append(cached.content_hash)
                        continue
                    outcome = hash_results.get(i)
                    if outcome is TIMED_OUT:
                        logger.warning(
                            "face scan: skipping %s - timed out after %.0fs reading it "
                            "(likely a cloud-sync placeholder or a stalled network/encrypted-drive read)",
                            scanned.path,
                            hash_timeout_for(scanned.size, floor=DEFAULT_HASH_TIMEOUT_SECONDS),
                        )
                        file_ids.append(None)
                        content_hashes.append(None)
                        continue
                    if outcome is None:
                        file_ids.append(None)
                        content_hashes.append(None)
                        continue
                    content_hash: str = outcome  # type: ignore[assignment]
                    try:
                        fid = store_file_cache(conn, library_root, scanned, content_hash, None)
                        file_ids.append(fid)
                        content_hashes.append(content_hash)
                    except Exception:
                        file_ids.append(None)
                        content_hashes.append(None)
                return True

            def detect_batch(batch: list[ScannedFile], start_offset: int) -> bool:
                """Detect faces (cache-first) for one batch, appending to
                file_faces_list. `start_offset` locates the batch's entries in
                file_ids/content_hashes. Returns False if cancelled partway through."""
                nonlocal provider, no_face_files, unreadable_files
                for local_i, scanned in enumerate(batch):
                    if ctx.cancelled():
                        return False
                    i = start_offset + local_i
                    fid = file_ids[i]
                    content_hash = content_hashes[i]
                    rel = scanned.path.relative_to(library_root).as_posix()

                    if fid is None or content_hash is None:
                        unreadable_files += 1
                        file_faces_list.append(
                            FileFaces(file_id=fid or -1, content_hash="",
                                      decoded_ok=False, faces=[])
                        )
                        ctx.report_progress(len(file_faces_list), total, "detecting")
                        continue

                    cached = get_cached_faces(conn, content_hash, provider_id)
                    if cached is not None:
                        regions = regions_for(conn, content_hash, provider_id)
                        kept = [cf for cf in cached if not is_rejected(regions, cf.bbox)]
                        file_faces_list.append(
                            FileFaces(file_id=fid, content_hash=content_hash,
                                      decoded_ok=True, faces=kept)
                        )
                        if not kept:
                            no_face_files += 1
                    else:
                        # cache miss: run provider
                        if provider is None:
                            provider = provider_factory()
                            provider.prepare()

                        mf = extract_file_faces(
                            scanned, provider,
                            video_frames=video_frames,
                            gif_frames=gif_frames,
                            min_face_size=min_face_size,
                        )
                        cached_faces: list[CachedFace] = [
                            CachedFace(
                                frame_no=fr.frame_no,
                                bbox=fr.bbox,
                                embedding=fr.embedding,
                            )
                            for fr in mf.faces
                        ]
                        # Only cache successful decodes — failures should be retried on the next scan.
                        if mf.decoded_ok:
                            put_cached_faces(conn, content_hash, provider_id, cached_faces)
                        # update decoded_ok in the files row
                        try:
                            stat = scanned.path.stat()
                            upsert_file(conn, rel, scanned.kind,
                                        stat.st_size, stat.st_mtime,
                                        content_hash, mf.decoded_ok)
                        except Exception:
                            pass
                        conn.commit()

                        regions = regions_for(conn, content_hash, provider_id)
                        kept = [cf for cf in cached_faces if not is_rejected(regions, cf.bbox)]
                        file_faces_list.append(
                            FileFaces(file_id=fid, content_hash=content_hash,
                                      decoded_ok=mf.decoded_ok, faces=kept)
                        )
                        if not mf.decoded_ok:
                            unreadable_files += 1
                        elif not kept:
                            no_face_files += 1

                    ctx.report_progress(len(file_faces_list), total, "detecting")
                return True

            def cluster_and_persist(files_done: int) -> dict:
                """Cluster whatever's in file_faces_list so far and persist it.
                Safe to call more than once — persist_face_scan() fully rebuilds
                the provider's faces/persons rows each time it's called."""
                flat_embeddings: list[np.ndarray] = []
                flat_owners: list[int] = []
                for media_idx, ff in enumerate(file_faces_list):
                    for cf in ff.faces:
                        flat_embeddings.append(cf.embedding)
                        flat_owners.append(media_idx)

                flat_labels = cluster_embeddings(
                    flat_embeddings, eps=eps, min_samples=DEFAULT_MIN_SAMPLES
                )
                n_people = len({int(l) for l in flat_labels if int(l) != -1})

                new_file_ids = {
                    ff.file_id
                    for ff in file_faces_list
                    if ff.file_id >= 0 and ff.file_id not in existing_file_ids
                }

                summary = {
                    "files": files_done,
                    "faces": len(flat_embeddings),
                    "people": n_people,
                    "no_face_files": no_face_files,
                    "unreadable_files": unreadable_files,
                }

                return persist_face_scan(
                    conn,
                    scan_id=ctx.job_id,
                    provider_id=provider_id,
                    file_faces=file_faces_list,
                    labels=flat_labels,
                    owners=flat_owners,
                    started_at=started_at,
                    finished_at=time.time(),
                    params={
                        "type": "faces",
                        "provider_id": provider_id,
                        "eps": eps,
                        "video_frames": video_frames,
                        "gif_frames": gif_frames,
                    },
                    summary=summary,
                    pending_for_named=pending_for_named,
                    new_file_ids=new_file_ids,
                )

            # Pass 1: everything except large videos — hashed, detected, and
            # persisted first so results are reviewable right away.
            if not hash_batch(fast_files):
                return {}
            if not detect_batch(fast_files, 0):
                return {}

            if slow_files and fast_files:
                ctx.report_progress(0, 0, "clustering")
                cluster_and_persist(len(fast_files))
                # Tells the frontend to refetch persons now — pass 2 below
                # keeps running in the background while the user reviews.
                ctx.report_progress(len(file_faces_list), total, "reviewable")

                if not hash_batch(slow_files):
                    return {}
                if not detect_batch(slow_files, len(fast_files)):
                    return {}

            if ctx.cancelled():
                return {}

            # Prune stale faces for paths no longer on disk (external moves/
            # deletes) — done once, after both passes, using every file seen
            # this run. Pruning after only the fast pass would wrongly treat a
            # not-yet-reached slow video's existing faces as stale.
            seen_file_ids = {fid for fid in file_ids if fid is not None}
            if seen_file_ids:
                # A NOT IN (?,?,...) with one placeholder per file blows past
                # SQLite's ~32,766 bound-parameter limit on large libraries
                # (OperationalError: too many SQL variables), failing the scan
                # at the finish line after hours of work. A temp table sidesteps
                # the limit entirely — each INSERT binds only a few params.
                conn.execute("CREATE TEMP TABLE IF NOT EXISTS _scan_seen_file_ids (file_id INTEGER PRIMARY KEY)")
                conn.execute("DELETE FROM _scan_seen_file_ids")
                conn.executemany(
                    "INSERT INTO _scan_seen_file_ids (file_id) VALUES (?)",
                    [(fid,) for fid in seen_file_ids],
                )
                conn.execute(
                    "DELETE FROM faces WHERE provider_id = ? AND file_id NOT IN (SELECT file_id FROM _scan_seen_file_ids)",
                    (provider_id,),
                )
                # Also prune `files` rows themselves for entries that are both
                # unseen this walk AND reference no remaining face (any
                # provider) — a file deleted/moved outside the app otherwise
                # sits in the index forever (only `faces` rows were pruned
                # above), and organize_plan.py routes every decoded_ok=0 row
                # into People/_Needs Review, including these phantom entries
                # (F10). Scoped to "no faces left" rather than "unseen" alone
                # so a directory that merely timed out this one walk (see
                # scan_folder's per-directory timeout) never loses a real
                # person's face/identity data over a transient stall.
                conn.execute(
                    """
                    DELETE FROM files
                    WHERE id NOT IN (SELECT file_id FROM _scan_seen_file_ids)
                      AND id NOT IN (SELECT DISTINCT file_id FROM faces)
                    """
                )
                conn.execute("DROP TABLE _scan_seen_file_ids")
                conn.commit()

            ctx.report_progress(0, 0, "clustering")
            ctx.report_progress(0, 0, "saving")
            final_summary = cluster_and_persist(total)

        finally:
            conn.close()

        return final_summary

    return runner
