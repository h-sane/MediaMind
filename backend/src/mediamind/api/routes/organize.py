"""Organize routes: preview, execute, undo, audit.

Flow:
  POST /v1/libraries/{id}/organize/preview     -> OrganizePreviewOut (no side effects)
  POST /v1/libraries/{id}/organize/execute     -> ExecutionReportOut (dry-run, or real via run_sync)
  POST /v1/libraries/{id}/organize/execute-job -> JobSnapshot (real, async — polled via /scans/{job_id})
  POST /v1/libraries/{id}/organize/undo        -> {ok, handled, planned, errors, kind}
  GET  /v1/libraries/{id}/organize/audit       -> list[OrganizeActionOut]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Request

from mediamind.api.models import (
    ExecutionReportOut,
    JobSnapshot,
    ManifestEntryOut,
    OrganizeActionOut,
    OrganizeExecuteIn,
    OrganizePreviewOut,
    PlannedMoveOut,
)
from mediamind.config import library_data_dir
from mediamind.core.jobs import JobContext, JobManager
from mediamind.core.libraries import LibraryRegistry
from mediamind.core.organize_plan import build_organize_plan, plan_hash as compute_plan_hash
from mediamind.core.safety import FileOp, execute as safety_execute, new_manifest_path
from mediamind.store.audit import last_undoable, list_actions, mark_undone, record_action
from mediamind.store.db import library_db_path, open_db
from mediamind.store.persons import latest_faces_scan

router = APIRouter(tags=["organize"])


def _registry(request: Request) -> LibraryRegistry:
    return request.app.state.registry


def _job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


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
        plan_hash=compute_plan_hash(moves),
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


def _check_plan_guards(
    moves: list,
    expected_planned: int | None,
    expected_plan_hash: str | None,
) -> None:
    """Raise ValueError (routes turn this into a 409) if the freshly-rebuilt
    plan no longer matches what the caller confirmed — either in size
    (`expected_planned`, pre-existing) or in content
    (`expected_plan_hash`: same count, different files — e.g. a rescan
    reassigned who a cluster matched between preview and execute)."""
    if expected_planned is not None and len(moves) != expected_planned:
        raise ValueError(
            f"Plan changed: expected {expected_planned} moves but "
            f"server computed {len(moves)}. Refresh and re-confirm."
        )
    if expected_plan_hash is not None and compute_plan_hash(moves) != expected_plan_hash:
        raise ValueError(
            "Plan contents changed since you confirmed (files were added, removed, "
            "or reassigned to different people) even though the count may match. "
            "Refresh and re-confirm."
        )


def _make_organize_execute_runner(
    library_root: Path,
    expected_planned: int | None,
    expected_plan_hash: str | None,
) -> Callable[[JobContext], dict]:
    """Real (non-dry-run) organize execution as a JobManager runner — shared
    by the synchronous `/execute` route (via `run_sync`) and the async
    `/execute-job` route, so both guard/execute/record logic lives once."""

    def runner(ctx: JobContext) -> dict:
        conn = _open_db(library_root)
        try:
            provider_id = _require_provider_id(conn, library_root)
            moves = build_organize_plan(conn, provider_id)
        finally:
            conn.close()

        if not moves:
            raise ValueError("Nothing to organize — run a face scan first or name some people")
        _check_plan_guards(moves, expected_planned, expected_plan_hash)

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
        ctx.report_progress(0, len(ops), "moving")
        report = safety_execute(
            ops,
            manifest_path=manifest_path,
            dry_run=False,
            on_progress=lambda done, total: ctx.report_progress(done, total, "moving"),
            should_cancel=ctx.cancelled,
        )

        conn = _open_db(library_root)
        try:
            # organize-by-person has no DB side effects beyond files.path (no
            # binding/rename), so no undo_data — unlike faces-merge-into-folder
            # and faces-materialize below.
            record_action(
                conn,
                kind="organize-by-person",
                manifest_path=str(manifest_path),
                report=report,
                dry_run=False,
            )
            for e in report.entries:
                if e.action == "moved" and e.destination:
                    try:
                        old_rel = Path(e.source).relative_to(library_root).as_posix()
                        new_rel = Path(e.destination).relative_to(library_root).as_posix()
                        conn.execute(
                            "UPDATE files SET path = ? WHERE path = ?",
                            (new_rel, old_rel),
                        )
                    except ValueError:
                        pass  # source outside library_root — skip gracefully
            conn.commit()
        finally:
            conn.close()

        return {
            "planned": report.planned,
            "handled": report.handled,
            "ok": report.ok,
            "dry_run": False,
            "manifest_path": str(report.manifest_path) if report.manifest_path else None,
            "entries": [
                {"source": e.source, "action": e.action, "destination": e.destination, "error": e.error}
                for e in report.entries
            ],
        }

    return runner


_PLAN_GUARD_MARKERS = ("Plan changed", "Plan contents changed", "Nothing to organize")


def _execute_error_status(error: str) -> int:
    """A runner's ValueError (guard rejection — plan changed/empty) is a
    client-correctable 409; anything else (an unexpected exception from
    `safety_execute`/the DB) is a genuine server error."""
    return 409 if any(marker in error for marker in _PLAN_GUARD_MARKERS) else 500


def _report_out_from_job_result(result: dict) -> ExecutionReportOut:
    return ExecutionReportOut(
        planned=result["planned"],
        handled=result["handled"],
        ok=result["ok"],
        dry_run=result["dry_run"],
        manifest_path=result["manifest_path"],
        entries=[ManifestEntryOut(**e) for e in result["entries"]],
    )


@router.post("/libraries/{library_id}/organize/execute", response_model=ExecutionReportOut)
def organize_execute(library_id: str, body: OrganizeExecuteIn, request: Request):
    """Execute the organize plan (or dry-run it).

    Dry-run stays a simple, unguarded read-mostly call (nothing on disk
    changes, so it can't race a scan). Real execution runs as a JobManager
    job via `run_sync` — same synchronous HTTP contract as before, but now
    visible to `running_for()`/`EXCLUSIVE_JOB_TYPES` for its whole duration
    so a concurrent scan can't race it (F8/F21). The live UI uses
    `/execute-job` below instead, for real progress/cancellation.
    """
    jm = _job_manager(request)

    if body.dry_run:
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
        try:
            _check_plan_guards(moves, body.expected_planned, body.expected_plan_hash)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        ops = [
            FileOp(source=library_root / m.source_rel, dest_folder=library_root / m.dest_folder_rel, mode="move")
            for m in moves
        ]
        manifest_path = new_manifest_path(library_data_dir(library_root), "organize")
        report = safety_execute(ops, manifest_path=manifest_path, dry_run=True)
        conn = _open_db(library_root)
        try:
            record_action(conn, kind="organize-by-person", manifest_path=str(manifest_path), report=report, dry_run=True)
        finally:
            conn.close()
        return ExecutionReportOut(
            planned=report.planned,
            handled=report.handled,
            ok=report.ok,
            dry_run=True,
            manifest_path=str(report.manifest_path) if report.manifest_path else None,
            entries=[
                ManifestEntryOut(source=e.source, action=e.action, destination=e.destination, error=e.error)
                for e in report.entries
            ],
        )

    running = jm.running_for(library_id)
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"A {running.type} scan is still running — wait for it to finish",
        )

    library_root = _get_library_root(request, library_id)
    runner = _make_organize_execute_runner(library_root, body.expected_planned, body.expected_plan_hash)
    job = jm.run_sync(library_id, "organize-execute", runner)
    if job.state == "failed":
        raise HTTPException(status_code=_execute_error_status(job.error), detail=job.error)
    return _report_out_from_job_result(job.result or {})


@router.post("/libraries/{library_id}/organize/execute-job", response_model=JobSnapshot, status_code=202)
def organize_execute_job(library_id: str, body: OrganizeExecuteIn, request: Request):
    """Real execution as a background job the caller polls/cancels — the live
    OrganizePanel uses this instead of the synchronous route above so a
    large batch shows progress and can be cancelled instead of blocking the
    confirm dialog."""
    jm = _job_manager(request)
    running = jm.running_for(library_id)
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"A {running.type} scan is still running — wait for it to finish",
        )

    library_root = _get_library_root(request, library_id)
    runner = _make_organize_execute_runner(library_root, body.expected_planned, body.expected_plan_hash)
    job = jm.start(library_id, "organize-execute", runner)
    return _snapshot(job)


@router.post("/libraries/{library_id}/organize/undo")
def organize_undo(library_id: str, request: Request):
    """Undo the most recent non-dry-run organize action."""
    running = _job_manager(request).running_for(library_id)
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"A {running.type} scan is still running — wait for it to finish",
        )

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
        # Update files.path to reflect undo moves (destination → original source dir).
        for e in report.entries:
            if e.action == "moved" and e.destination:
                try:
                    # After undo: the old "destination" is the new location on disk.
                    old_rel = Path(e.source).relative_to(library_root).as_posix()
                    new_rel = Path(e.destination).relative_to(library_root).as_posix()
                    conn.execute(
                        "UPDATE files SET path = ? WHERE path = ?",
                        (new_rel, old_rel),
                    )
                except ValueError:
                    pass

        # Reverse this action's DB side effects, not just its file moves
        # (F9) — faces-merge-into-folder and faces-materialize both create a
        # folder binding, rename the person, and record "not this person"
        # rejections for excluded/redirected files; none of that was ever
        # touched by undo before, so the very next preview would immediately
        # re-plan moving everything right back in. organize-by-person and
        # faces-prep-create-unsorted have no such side effects (undo_data is
        # NULL for them) and this block is a no-op.
        if report.ok and action["undo_data"]:
            undo_data = json.loads(action["undo_data"])
            binding_id = undo_data.get("binding_id")
            person_id = undo_data.get("person_id")
            if binding_id is not None:
                conn.execute("DELETE FROM folder_bindings WHERE id = ?", (binding_id,))
            if person_id is not None:
                conn.execute(
                    "UPDATE persons SET name = ? WHERE id = ?",
                    (undo_data.get("prior_name"), person_id),
                )
                rejected_ids = undo_data.get("rejected_file_ids") or []
                if rejected_ids:
                    placeholders = ",".join("?" * len(rejected_ids))
                    hash_rows = conn.execute(
                        f"SELECT content_hash FROM files WHERE id IN ({placeholders})", rejected_ids
                    ).fetchall()
                    provider_id = undo_data.get("provider_id", "")
                    for hr in hash_rows:
                        if hr["content_hash"]:
                            conn.execute(
                                "DELETE FROM rejected_person_files WHERE content_hash = ? AND provider_id = ? AND person_id = ?",
                                (hr["content_hash"], provider_id, person_id),
                            )

        conn.commit()
    finally:
        conn.close()

    return {
        "ok": report.ok,
        "handled": report.handled,
        "planned": report.planned,
        "errors": len(report.errors),
        "kind": action["kind"],
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
