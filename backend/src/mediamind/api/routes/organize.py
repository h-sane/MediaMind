"""Organize routes: preview, execute, undo, audit.

Flow:
  POST /v1/libraries/{id}/organize/preview  -> OrganizePreviewOut (no side effects)
  POST /v1/libraries/{id}/organize/execute  -> ExecutionReportOut
  POST /v1/libraries/{id}/organize/undo     -> {ok, handled, planned, errors}
  GET  /v1/libraries/{id}/organize/audit    -> list[OrganizeActionOut]
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from mediamind.api.models import (
    ExecutionReportOut,
    ManifestEntryOut,
    OrganizeActionOut,
    OrganizeExecuteIn,
    OrganizePreviewOut,
    PlannedMoveOut,
)
from mediamind.config import library_data_dir
from mediamind.core.libraries import LibraryRegistry
from mediamind.core.organize_plan import build_organize_plan
from mediamind.core.safety import FileOp, execute as safety_execute, new_manifest_path
from mediamind.store.audit import last_undoable, list_actions, mark_undone, record_action
from mediamind.store.db import library_db_path, open_db
from mediamind.store.persons import latest_faces_scan

router = APIRouter(tags=["organize"])


def _registry(request: Request) -> LibraryRegistry:
    return request.app.state.registry


def _get_library_root(request: Request, library_id: str) -> Path:
    lib = _registry(request).get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    return Path(lib.path)


def _open_db(library_root: Path):
    return open_db(library_db_path(library_data_dir(library_root)))


def _require_provider_id(conn, library_root: Path) -> str:
    scan = latest_faces_scan(conn)
    if scan is None:
        raise HTTPException(
            status_code=422,
            detail="No face scan found — run a face scan first",
        )
    params = json.loads(scan["params"] or "{}")
    return params.get("provider_id", "")


@router.post("/libraries/{library_id}/organize/preview", response_model=OrganizePreviewOut)
def organize_preview(library_id: str, request: Request):
    """Return the organize plan without touching anything on disk."""
    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        provider_id = _require_provider_id(conn, library_root)
        moves = build_organize_plan(conn, provider_id)
    finally:
        conn.close()

    by_person: dict[str, int] = {}
    for m in moves:
        key = m.person_name or m.dest_folder_rel.split("/")[-1]
        by_person[key] = by_person.get(key, 0) + 1

    return OrganizePreviewOut(
        planned=len(moves),
        by_person=by_person,
        moves=[
            PlannedMoveOut(
                source_rel=m.source_rel,
                dest_folder_rel=m.dest_folder_rel,
                person_id=m.person_id,
                person_name=m.person_name,
            )
            for m in moves
        ],
    )


@router.post("/libraries/{library_id}/organize/execute", response_model=ExecutionReportOut)
def organize_execute(library_id: str, body: OrganizeExecuteIn, request: Request):
    """Execute the organize plan (or dry-run it)."""
    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        provider_id = _require_provider_id(conn, library_root)
        moves = build_organize_plan(conn, provider_id)
    finally:
        conn.close()

    if not moves:
        raise HTTPException(
            status_code=422,
            detail="Nothing to organize — run a face scan first or name some people",
        )

    ops = [
        FileOp(
            source=library_root / m.source_rel,
            dest_folder=library_root / m.dest_folder_rel,
            mode="move",
        )
        for m in moves
    ]

    data_dir = library_data_dir(library_root)
    manifest_path = new_manifest_path(data_dir, "organize")
    report = safety_execute(ops, manifest_path=manifest_path, dry_run=body.dry_run)

    conn = _open_db(library_root)
    try:
        record_action(
            conn,
            kind="organize-by-person",
            manifest_path=str(manifest_path),
            report=report,
            dry_run=body.dry_run,
        )
    finally:
        conn.close()

    return ExecutionReportOut(
        planned=report.planned,
        handled=report.handled,
        ok=report.ok,
        dry_run=body.dry_run,
        manifest_path=str(report.manifest_path) if report.manifest_path else None,
        entries=[
            ManifestEntryOut(
                source=e.source,
                action=e.action,
                destination=e.destination,
                error=e.error,
            )
            for e in report.entries
        ],
    )


@router.post("/libraries/{library_id}/organize/undo")
def organize_undo(library_id: str, request: Request):
    """Undo the most recent non-dry-run organize action."""
    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        action = last_undoable(conn)
        if action is None:
            raise HTTPException(status_code=404, detail="No undoable organize action found")

        entries = conn.execute(
            """
            SELECT source, destination FROM manifest_entries
            WHERE action_id = ? AND action = 'moved'
            """,
            (action["id"],),
        ).fetchall()
    finally:
        conn.close()

    if not entries:
        raise HTTPException(
            status_code=422,
            detail="Action recorded no successful moves — nothing to undo",
        )

    # Reverse: move each destination back to its original source folder
    ops = [
        FileOp(
            source=Path(e["destination"]),
            dest_folder=Path(e["source"]).parent,
            mode="move",
        )
        for e in entries
    ]

    data_dir = library_data_dir(library_root)
    manifest_path = new_manifest_path(data_dir, "undo")
    report = safety_execute(ops, manifest_path=manifest_path)

    conn = _open_db(library_root)
    try:
        if report.ok:
            mark_undone(conn, action["id"])
        record_action(
            conn,
            kind="undo",
            manifest_path=str(manifest_path),
            report=report,
            dry_run=False,
        )
    finally:
        conn.close()

    return {
        "ok": report.ok,
        "handled": report.handled,
        "planned": report.planned,
        "errors": len(report.errors),
    }


@router.get("/libraries/{library_id}/organize/audit", response_model=list[OrganizeActionOut])
def organize_audit(library_id: str, request: Request):
    """Return all organize actions for this library, newest first."""
    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        actions = list_actions(conn)
    finally:
        conn.close()

    return [
        OrganizeActionOut(
            id=a["id"],
            kind=a["kind"],
            created_at=a["created_at"],
            planned=a["planned"],
            handled=a["handled"],
            ok=bool(a["ok"]),
            dry_run=bool(a["dry_run"]),
            undone=bool(a["undone"]),
        )
        for a in actions
    ]
