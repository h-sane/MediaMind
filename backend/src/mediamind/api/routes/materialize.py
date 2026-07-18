"""Materialize a not-yet-foldered person into a brand-new sibling folder
(see `store/materialize.py`).

Routes:
  GET  /v1/libraries/{id}/persons/{person_id}/materialize/preview -> MaterializePreviewOut
  POST /v1/libraries/{id}/persons/{person_id}/materialize          -> ExecutionReportOut
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from mediamind.api.models import (
    ExecutionReportOut,
    ManifestEntryOut,
    MaterializeCandidateOut,
    MaterializeIn,
    MaterializePreviewOut,
)
from mediamind.config import library_data_dir
from mediamind.core.jobs import JobManager
from mediamind.core.libraries import LibraryRegistry
from mediamind.core.organize_plan import safe_folder_name
from mediamind.core.safety import FileOp, execute as safety_execute, new_manifest_path
from mediamind.store import materialize as materialize_store
from mediamind.store.audit import record_action
from mediamind.store.db import library_db_path, open_db
from mediamind.store.materialize import AlreadyBoundError
from mediamind.store.persons import latest_faces_scan

router = APIRouter(tags=["materialize"])


def _registry(request: Request) -> LibraryRegistry:
    return request.app.state.registry


def _job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


def _get_library_root(request: Request, library_id: str) -> Path:
    lib = _registry(request).get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    return Path(lib.path)


def _provider_id(conn) -> str:
    scan = latest_faces_scan(conn)
    if scan is None:
        raise HTTPException(status_code=422, detail="No face scan found — run a face scan first")
    return json.loads(scan["params"] or "{}").get("provider_id", "")


@router.get(
    "/libraries/{library_id}/persons/{person_id}/materialize/preview",
    response_model=MaterializePreviewOut,
)
def preview_materialize(library_id: str, person_id: int, request: Request):
    library_root = _get_library_root(request, library_id)
    conn = open_db(library_db_path(library_data_dir(library_root)))
    try:
        provider_id = _provider_id(conn)
        if materialize_store.is_bound(conn, person_id):
            raise HTTPException(status_code=409, detail="This person already has a folder")
        candidates = materialize_store.list_candidates(conn, provider_id, person_id)
        return MaterializePreviewOut(
            person_id=person_id,
            candidates=[
                MaterializeCandidateOut(file_id=c.file_id, path=c.source_rel, kind=c.kind)
                for c in candidates
            ],
        )
    finally:
        conn.close()


@router.post(
    "/libraries/{library_id}/persons/{person_id}/materialize",
    response_model=ExecutionReportOut,
)
def materialize(library_id: str, person_id: int, body: MaterializeIn, request: Request):
    running = _job_manager(request).running_for(library_id)
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"A {running.type} scan is still running — wait for it to finish",
        )

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name is required")

    library_root = _get_library_root(request, library_id)
    conn = open_db(library_db_path(library_data_dir(library_root)))
    try:
        provider_id = _provider_id(conn)
        if materialize_store.is_bound(conn, person_id):
            raise HTTPException(status_code=409, detail="This person already has a folder")

        candidates = materialize_store.list_candidates(conn, provider_id, person_id)
        excluded = set(body.excluded_file_ids)
        reassign_map = {r.file_id: r.dest_folder_rel for r in body.reassignments}
        dest_folder_rel = safe_folder_name(name)

        moves: list[tuple[int, str, str]] = []  # (file_id, source_rel, dest_folder_rel)
        for c in candidates:
            if c.file_id in excluded:
                continue
            dest = reassign_map.get(c.file_id, dest_folder_rel)
            moves.append((c.file_id, c.source_rel, dest))

        if body.expected_move_count is not None and len(moves) != body.expected_move_count:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Plan changed: expected {body.expected_move_count} moves but "
                    f"server computed {len(moves)}. Refresh and re-confirm."
                ),
            )

        ops = [
            FileOp(source=library_root / src, dest_folder=library_root / dest, mode="move")
            for _fid, src, dest in moves
        ]

        manifest_path = new_manifest_path(library_data_dir(library_root), "faces-materialize")
        report = safety_execute(ops, manifest_path=manifest_path, dry_run=body.dry_run)

        if not body.dry_run:
            record_action(
                conn,
                kind="faces-materialize",
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

            # Binding + rename apply regardless of how many stray files moved,
            # same rationale as merge_suggestion.
            try:
                materialize_store.materialize_person_folder(conn, person_id, name)
            except AlreadyBoundError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

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
    finally:
        conn.close()
