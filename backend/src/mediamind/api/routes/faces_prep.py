"""Pre-scan folder-structure check for the Faces tool (see `core/faces/folder_prep.py`).

Routes:
  GET  /v1/libraries/{id}/faces/prep                      -> FacesPrepOut
  POST /v1/libraries/{id}/faces/prep/create-unsorted       -> ExecutionReportOut
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from mediamind.api.models import CreateUnsortedIn, ExecutionReportOut, FacesPrepOut, ManifestEntryOut
from mediamind.config import library_data_dir
from mediamind.core.faces.folder_prep import (
    UNSORTED_DIRNAME,
    build_unsorted_moves,
    scan_folder_prep,
)
from mediamind.core.jobs import JobManager
from mediamind.core.safety import FileOp, execute as safety_execute, new_manifest_path
from mediamind.store.audit import record_action
from mediamind.store.db import library_db_path, open_db

router = APIRouter(tags=["faces-prep"])


def _get_library_root(request: Request, library_id: str) -> Path:
    lib = request.app.state.registry.get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    return Path(lib.path)


def _job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


@router.get("/libraries/{library_id}/faces/prep", response_model=FacesPrepOut)
def get_faces_prep(library_id: str, request: Request):
    library_root = _get_library_root(request, library_id)
    result = scan_folder_prep(library_root)
    return FacesPrepOut(**result.__dict__)


@router.post(
    "/libraries/{library_id}/faces/prep/create-unsorted",
    response_model=ExecutionReportOut,
)
def create_unsorted(library_id: str, body: CreateUnsortedIn, request: Request):
    running = _job_manager(request).running_for(library_id)
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"A {running.type} scan is still running — wait for it to finish",
        )

    library_root = _get_library_root(request, library_id)
    sources = build_unsorted_moves(library_root)
    ops = [
        FileOp(source=path, dest_folder=library_root / UNSORTED_DIRNAME, mode="move")
        for path in sources
    ]

    manifest_path = new_manifest_path(library_data_dir(library_root), "faces-prep-unsorted")
    report = safety_execute(ops, manifest_path=manifest_path, dry_run=body.dry_run)

    conn = open_db(library_db_path(library_data_dir(library_root)))
    try:
        if not body.dry_run:
            record_action(
                conn,
                kind="faces-prep-create-unsorted",
                manifest_path=str(manifest_path),
                report=report,
                dry_run=False,
            )
            for e in report.entries:
                if e.action == "moved" and e.destination:
                    try:
                        old_rel = Path(e.source).relative_to(library_root).as_posix()
                        new_rel = Path(e.destination).relative_to(library_root).as_posix()
                        conn.execute("UPDATE files SET path = ? WHERE path = ?", (new_rel, old_rel))
                    except ValueError:
                        pass  # source outside library_root — skip gracefully
            conn.commit()
    finally:
        conn.close()

    return ExecutionReportOut(
        planned=report.planned,
        handled=report.handled,
        ok=report.ok,
        dry_run=body.dry_run,
        manifest_path=str(report.manifest_path) if report.manifest_path else None,
        entries=[
            ManifestEntryOut(source=e.source, action=e.action, destination=e.destination, error=e.error)
            for e in report.entries
        ],
    )
