"""Scan job routes: start, poll, cancel."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from mediamind.api.models import JobSnapshot, ScanIn
from mediamind.config import library_data_dir
from mediamind.core.dedupe import DEFAULT_NEAR_THRESHOLD, find_duplicates
from mediamind.core.jobs import JobContext, JobManager
from mediamind.core.libraries import LibraryRegistry
from mediamind.core.scanner import scan_folder
from mediamind.store.db import library_db_path, open_db
from mediamind.store.duplicates import persist_scan

router = APIRouter(tags=["scans"])


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

        files = list(scan_folder(library_root))

        def progress(done: int, total: int) -> None:
            if not ctx.cancelled():
                ctx.report_progress(done, total, "hashing")

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

        reclaimable = sum(f.size for g in groups for f in g.files if not f.is_best)
        total_files = sum(len(g.files) for g in groups)
        summary = {
            "groups": len(groups),
            "files": total_files,
            "reclaimable_bytes": reclaimable,
        }

        data_dir = library_data_dir(library_root)
        conn = open_db(library_db_path(data_dir))
        try:
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

        return summary

    return runner


@router.post("/libraries/{library_id}/scans", response_model=JobSnapshot, status_code=202)
def start_scan(library_id: str, body: ScanIn, request: Request):
    lib = _registry(request).get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")

    jm = _job_manager(request)
    if jm.running_for(library_id) is not None:
        raise HTTPException(status_code=409, detail="A scan is already running for this library")

    threshold = body.near_threshold if body.type == "dedupe" else DEFAULT_NEAR_THRESHOLD
    runner = _make_dedupe_runner(Path(lib.path), threshold)
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
