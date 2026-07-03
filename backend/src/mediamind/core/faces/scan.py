"""Face scan pipeline: hash → cache-or-detect → cluster → persist.

Mirrors _make_dedupe_runner's shape from api/routes/scans.py.
Per-file commits to the embedding cache mean a cancelled scan can be resumed:
on the next run, only files not yet in the cache need re-detection.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import numpy as np

from mediamind.core.faces.clustering import DEFAULT_EPS, DEFAULT_MIN_SAMPLES, cluster_embeddings
from mediamind.core.faces.engine import (
    DEFAULT_GIF_FRAMES,
    DEFAULT_MIN_FACE_SIZE,
    DEFAULT_VIDEO_FRAMES,
    extract_file_faces,
)
from mediamind.core.hashing import hash_file
from mediamind.core.jobs import JobContext
from mediamind.core.scanner import scan_folder
from mediamind.config import library_data_dir
from mediamind.providers.base import FaceProvider
from mediamind.store.db import library_db_path, open_db
from mediamind.store.embeddings import CachedFace, get_cached_faces, put_cached_faces
from mediamind.store.persons import FileFaces, file_ids_with_faces, persist_face_scan, upsert_file


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

        scanned_files = list(scan_folder(library_root))
        total = len(scanned_files)
        if ctx.cancelled():
            return {}

        data_dir = library_data_dir(library_root)
        conn = open_db(library_db_path(data_dir))
        provider: FaceProvider | None = None

        try:
            existing_file_ids = file_ids_with_faces(conn, provider_id)

            # phase 1: hash + upsert files
            file_ids: list[int | None] = []
            content_hashes: list[str | None] = []

            for i, scanned in enumerate(scanned_files):
                if ctx.cancelled():
                    return {}
                rel = scanned.path.relative_to(library_root).as_posix()
                try:
                    stat = scanned.path.stat()
                    content_hash: str | None = hash_file(scanned.path)
                    fid = upsert_file(conn, rel, scanned.kind,
                                     stat.st_size, stat.st_mtime, content_hash, None)
                    conn.commit()
                    file_ids.append(fid)
                    content_hashes.append(content_hash)
                except Exception:
                    file_ids.append(None)
                    content_hashes.append(None)
                ctx.report_progress(i + 1, total, "hashing")

            # Prune stale faces for paths no longer on disk (external moves/deletes).
            seen_file_ids = {fid for fid in file_ids if fid is not None}
            if seen_file_ids:
                placeholders = ",".join("?" * len(seen_file_ids))
                conn.execute(
                    f"DELETE FROM faces WHERE provider_id = ? AND file_id NOT IN ({placeholders})",
                    [provider_id, *seen_file_ids],
                )
                conn.commit()

            # phase 2: detect faces (cache-first, per-file commits for resume)
            file_faces_list: list[FileFaces] = []
            no_face_files = 0
            unreadable_files = 0

            for i, scanned in enumerate(scanned_files):
                if ctx.cancelled():
                    return {}
                fid = file_ids[i]
                content_hash = content_hashes[i]
                rel = scanned.path.relative_to(library_root).as_posix()

                if fid is None or content_hash is None:
                    unreadable_files += 1
                    file_faces_list.append(
                        FileFaces(file_id=fid or -1, content_hash="",
                                  decoded_ok=False, faces=[])
                    )
                    ctx.report_progress(i + 1, total, "detecting")
                    continue

                cached = get_cached_faces(conn, content_hash, provider_id)
                if cached is not None:
                    file_faces_list.append(
                        FileFaces(file_id=fid, content_hash=content_hash,
                                  decoded_ok=True, faces=cached)
                    )
                    if not cached:
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

                    file_faces_list.append(
                        FileFaces(file_id=fid, content_hash=content_hash,
                                  decoded_ok=mf.decoded_ok, faces=cached_faces)
                    )
                    if not mf.decoded_ok:
                        unreadable_files += 1
                    elif not cached_faces:
                        no_face_files += 1

                ctx.report_progress(i + 1, total, "detecting")

            if ctx.cancelled():
                return {}

            # phase 3: cluster (flat embeddings + owners)
            ctx.report_progress(0, 0, "clustering")
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

            if ctx.cancelled():
                return {}

            # phase 4: persist
            ctx.report_progress(0, 0, "saving")

            new_file_ids = {
                ff.file_id
                for ff in file_faces_list
                if ff.file_id >= 0 and ff.file_id not in existing_file_ids
            }

            summary = {
                "files": total,
                "faces": len(flat_embeddings),
                "people": n_people,
                "no_face_files": no_face_files,
                "unreadable_files": unreadable_files,
            }

            final_summary = persist_face_scan(
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

        finally:
            conn.close()

        return final_summary

    return runner
