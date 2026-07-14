"""Scan job routes: start, poll, cancel."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from mediamind.api.models import JobSnapshot, ScanIn
from mediamind.config import library_data_dir
from mediamind.core.dedupe import DEFAULT_NEAR_THRESHOLD, find_duplicates, group_signature
from mediamind.core.jobs import JobContext, JobManager
from mediamind.core.libraries import LibraryRegistry
from mediamind.core.scanner import scan_folder
from mediamind.store.db import library_db_path, open_db
from mediamind.store.duplicates import get_dismissed_signatures, persist_scan

router = APIRouter(tags=["scans"])
logger = logging.getLogger("mediamind.scans")

# Coarser than JobContext's 0.2s progress-broadcast throttle — logging every
# tick would flood the in-app dev log console on a large scan. This only
# needs to be frequent enough that a user watching the log can tell a scan is
# actually moving, not frozen.
_LOG_INTERVAL_SECONDS = 2.0


def _registry(request: Request) -> LibraryRegistry:
    return request.app.state.registry


def _job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


def _snapshot(job) -> JobSnapshot:
    return JobSnapshot(
        id=job.id,
        library_id=job.library_id,
        type=job.type,
        state=job.state,
        phase=job.phase,
        done=job.done,
        total=job.total,
        error=job.error,
        result=job.result,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


def _make_dedupe_runner(library_root: Path, threshold: int):
    """Return a runner function closed over the library path and threshold."""

    def runner(ctx: JobContext) -> dict:
        started_at = time.time()
        ctx.report_progress(0, 0, "scanning")
        logger.info("Dedupe scan: walking %s", library_root)

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
            _throttled_log("Dedupe scan: %d files found so far…", n)

        def on_stat(done: int, total: int) -> None:
            if ctx.cancelled():
                return
            # A real total (not 0) here — the previously-invisible "reading
            # file info" step now shows an actual percentage and ETA instead
            # of a progress bar frozen on the last walk count.
            ctx.report_progress(done, total, "reading")
            _throttled_log("Dedupe scan: read details for %d/%d files…", done, total)

        files = list(
            scan_folder(library_root, on_walk=on_walk, on_stat=on_stat, should_cancel=ctx.cancelled)
        )
        if ctx.cancelled():
            return {}

        media_count = sum(1 for f in files if f.is_media)
        logger.info(
            "Dedupe scan: %d files found (%d media) — comparing for duplicates",
            len(files), media_count,
        )

        def progress(done: int, total: int) -> None:
            if not ctx.cancelled():
                ctx.report_progress(done, total, "hashing")
                _throttled_log("Dedupe scan: compared %d/%d files…", done, total)

        groups = find_duplicates(
            files,
            near_threshold=threshold,
            progress=progress,
            should_cancel=ctx.cancelled,
        )

        # Distinguish "cancelled" from "no duplicates" — find_duplicates returns
        # [] for both cases, so we must check the cancel flag explicitly here.
        if ctx.cancelled():
            return {}

        data_dir = library_data_dir(library_root)
        conn = open_db(library_db_path(data_dir))
        try:
            # A group the user already reviewed and confirmed via "Save
            # configuration" must not resurface on a rescan unless its
            # membership actually changed (e.g. a new duplicate file joined).
            dismissed = get_dismissed_signatures(conn)
            groups = [
                g for g in groups
                if group_signature([f.identity for f in g.files]) not in dismissed
            ]

            reclaimable = sum(f.size for g in groups for f in g.files if not f.is_best)
            total_files = sum(len(g.files) for g in groups)
            summary = {
                "groups": len(groups),
                "files": total_files,
                "reclaimable_bytes": reclaimable,
            }

            persist_scan(
                conn,
                scan_id=ctx.job_id,
                groups=groups,
                library_root=library_root,
                started_at=started_at,
                finished_at=time.time(),
                params={"type": "dedupe", "near_threshold": threshold},
                summary=summary,
            )
        finally:
            conn.close()

        logger.info(
            "Dedupe scan complete: %d groups, %d files, %d bytes reclaimable",
            summary["groups"], summary["files"], summary["reclaimable_bytes"],
        )
        return summary

    return runner


@router.post("/libraries/{library_id}/scans", response_model=JobSnapshot, status_code=202)
def start_scan(library_id: str, body: ScanIn, request: Request):
    lib = _registry(request).get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")

    jm = _job_manager(request)
    # Same-type guard only: a dedupe scan and a face scan are independent
    # (disjoint DB tables, read-only filesystem walks) and may run
    # concurrently; two scans of the same type may not.
    if jm.running_for(library_id, body.type) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"A {body.type} scan is already running for this library",
        )

    if body.type == "dedupe":
        runner = _make_dedupe_runner(Path(lib.path), body.near_threshold)
    elif body.type == "faces":
        from mediamind.core.faces.scan import make_face_scan_runner
        from mediamind.providers.manager import ProviderManager

        pm: ProviderManager = request.app.state.providers

        # Resolve which provider to use
        if body.provider_id:
            entry = pm.get_entry(body.provider_id)
        else:
            entry = next((e for e in pm.entries() if pm.is_installed(e.id)), None)

        if entry is None or not pm.is_installed(entry.id):
            raise HTTPException(
                status_code=422,
                detail="No face recognition provider installed — download one first",
            )

        provider_id = entry.id
        runner = make_face_scan_runner(
            Path(lib.path),
            lambda: pm.create(provider_id),
            provider_id,
            eps=entry.cluster_eps,
            pending_for_named=True,
        )
    else:
        raise HTTPException(status_code=422, detail=f"Unknown scan type '{body.type}'")

    job = jm.start(library_id, body.type, runner)
    return _snapshot(job)


@router.get("/libraries/{library_id}/scans/{job_id}", response_model=JobSnapshot)
def get_scan(library_id: str, job_id: str, request: Request):
    if _registry(request).get(library_id) is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    job = _job_manager(request).get(job_id)
    if job is None or job.library_id != library_id:
        raise HTTPException(status_code=404, detail="Unknown scan")
    return _snapshot(job)


@router.delete("/libraries/{library_id}/scans/{job_id}", status_code=202)
def cancel_scan(library_id: str, job_id: str, request: Request):
    if _registry(request).get(library_id) is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    job = _job_manager(request).get(job_id)
    if job is None or job.library_id != library_id:
        raise HTTPException(status_code=404, detail="Unknown scan")
    _job_manager(request).cancel(job_id)
    return {"status": "cancelling"}
