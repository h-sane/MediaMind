"""Folder-binding routes (Phase B): detect, list, accept/dismiss, release.

Folder bindings let MediaMind respect pre-existing person/group subfolders
instead of bulldozing them into a fresh People/ tree on organize.

Routes:
  POST /v1/libraries/{id}/bindings/refresh                    -> RefreshSuggestionsOut
  GET  /v1/libraries/{id}/bindings/suggestions?status=pending  -> BindingSuggestionsOut
  POST /v1/libraries/{id}/bindings/suggestions/{sid}/accept   -> BindingOut
  POST /v1/libraries/{id}/bindings/suggestions/{sid}/dismiss  -> {ok: bool}
  GET  /v1/libraries/{id}/bindings                            -> BindingsOut
  POST /v1/libraries/{id}/bindings/{bid}/release              -> {ok: bool}
  POST /v1/libraries/{id}/bindings/{bid}/outliers             -> BindingOut
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from mediamind.api.models import (
    AcceptOutliersIn,
    BindingOut,
    BindingSuggestionOut,
    BindingSuggestionsOut,
    BindingsOut,
    ExecutionReportOut,
    ManifestEntryOut,
    MovePreviewItemOut,
    OutlierFileOut,
    RefreshSuggestionsOut,
    SuggestionMergeIn,
    SuggestionMergePreviewOut,
)
from mediamind.config import library_data_dir
from mediamind.core.jobs import JobManager
from mediamind.core.libraries import LibraryRegistry
from mediamind.core.organize_plan import safe_dest_folder_rel
from mediamind.core.safety import FileOp, execute as safety_execute, new_manifest_path
from mediamind.store import bindings as bindings_store
from mediamind.store import rejected_persons
from mediamind.store.audit import record_action
from mediamind.store.bindings import BindingConflictError
from mediamind.store.db import library_db_path, open_db
from mediamind.store.persons import latest_faces_scan

router = APIRouter(tags=["bindings"])


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


def _outliers_out(record) -> list[OutlierFileOut]:
    return [
        OutlierFileOut(file_id=o.file_id, path=o.path, kind=o.kind, accepted=o.accepted)
        for o in record.outliers
    ]


def _resolve_outliers(conn, file_ids: list[int]) -> list[OutlierFileOut]:
    """Resolve suggestion.outlier_file_ids to path/kind for display.

    Pre-accept, there's no `accepted_outlier_file_ids` concept yet — every
    entry is just unresolved (accepted=False) until a merge folds it in.
    """
    if not file_ids:
        return []
    placeholders = ",".join("?" * len(file_ids))
    rows = conn.execute(
        f"SELECT id, path, kind FROM files WHERE id IN ({placeholders})", file_ids
    ).fetchall()
    by_id = {r["id"]: r for r in rows}
    return sorted(
        (
            OutlierFileOut(file_id=fid, path=by_id[fid]["path"], kind=by_id[fid]["kind"], accepted=False)
            for fid in file_ids
            if fid in by_id
        ),
        key=lambda o: o.path,
    )


def _person_names(conn, person_ids: list[int]) -> list[str]:
    names: list[str] = []
    for pid in person_ids:
        row = conn.execute(
            "SELECT auto_label, name FROM persons WHERE id = ?", (pid,)
        ).fetchone()
        names.append((row["name"] or row["auto_label"]) if row else f"#{pid}")
    return names


@router.post("/libraries/{library_id}/bindings/refresh", response_model=RefreshSuggestionsOut)
def refresh_bindings(library_id: str, request: Request):
    """Re-run folder-pattern detection and refresh the suggestion cache."""
    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        provider_id = _require_provider_id(conn, library_root)
        result = bindings_store.refresh_suggestions(conn, provider_id)
    finally:
        conn.close()
    return RefreshSuggestionsOut(**result)


@router.get("/libraries/{library_id}/bindings/suggestions", response_model=BindingSuggestionsOut)
def list_binding_suggestions(library_id: str, request: Request, status: str = "pending"):
    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        provider_id = _require_provider_id(conn, library_root)
        records = bindings_store.list_suggestions(conn, provider_id, status=status)
        out = [
            BindingSuggestionOut(
                id=r.id, folder_rel=r.folder_rel, kind=r.kind, file_count=r.file_count,
                coverage=r.coverage, person_ids=r.person_ids,
                person_names=_person_names(conn, r.person_ids),
                outlier_file_ids=r.outlier_file_ids,
                # Group suggestions have no single owning person, so a merge
                # plans no reverse moves for them — 0 without the extra query.
                move_count=(
                    len(bindings_store.build_suggestion_merge_moves(conn, r.id).moves)
                    if r.kind == "person" and r.status == "pending"
                    else 0
                ),
                status=r.status, created_at=r.created_at,
            )
            for r in records
        ]
    finally:
        conn.close()
    return BindingSuggestionsOut(provider_id=provider_id, suggestions=out)


@router.post(
    "/libraries/{library_id}/bindings/suggestions/{suggestion_id}/accept",
    response_model=BindingOut,
)
def accept_binding_suggestion(library_id: str, suggestion_id: int, request: Request):
    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        try:
            record = bindings_store.accept_suggestion(conn, suggestion_id)
        except BindingConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return BindingOut(
            id=record.id, folder_rel=record.folder_rel, kind=record.kind,
            person_ids=record.person_ids, person_names=_person_names(conn, record.person_ids),
            accepted_outlier_file_ids=record.accepted_outlier_file_ids,
            outliers=_outliers_out(record),
            created_at=record.created_at,
        )
    finally:
        conn.close()


@router.get(
    "/libraries/{library_id}/bindings/suggestions/{suggestion_id}/merge/preview",
    response_model=SuggestionMergePreviewOut,
)
def preview_suggestion_merge(library_id: str, suggestion_id: int, request: Request):
    """Read-only: what a merge-into-folder would move, for review before committing."""
    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        row = conn.execute(
            "SELECT * FROM binding_suggestions WHERE id = ?", (suggestion_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        try:
            plan = bindings_store.build_suggestion_merge_moves(conn, suggestion_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        person_ids = json.loads(row["person_ids"])
        outlier_ids = json.loads(row["outlier_file_ids"])

        return SuggestionMergePreviewOut(
            suggestion_id=suggestion_id,
            folder_rel=plan.folder_rel,
            person_names=_person_names(conn, person_ids),
            leaf_name=plan.leaf_name,
            move_count=len(plan.moves),
            moves=[
                MovePreviewItemOut(file_id=fid, source_rel=src, dest_folder_rel=dest, kind=kind)
                for fid, src, dest, kind in plan.moves
            ],
            folder_outliers=_resolve_outliers(conn, outlier_ids),
        )
    finally:
        conn.close()


@router.post(
    "/libraries/{library_id}/bindings/suggestions/{suggestion_id}/merge",
    response_model=ExecutionReportOut,
)
def merge_suggestion(library_id: str, suggestion_id: int, body: SuggestionMergeIn, request: Request):
    """Merge a suggestion into its folder in one operation: move the person's
    other photos in (minus any excluded/reassigned by the review modal),
    create the binding, and rename the person to the folder's name.

    Mirrors organize_execute's safety posture exactly (concurrency guard,
    expected-count guard, copy-then-delete via safety_execute, audit trail,
    files.path rewrite) so a partial failure never loses data or diverges
    the DB from disk — it just leaves some files unmoved and reports them.
    """
    running = _job_manager(request).running_for(library_id)
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"A {running.type} scan is still running — wait for it to finish",
        )

    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        provider_id = _require_provider_id(conn, library_root)

        try:
            reassignments = {
                r.file_id: safe_dest_folder_rel(r.dest_folder_rel, library_root) for r in body.reassignments
            }
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        try:
            plan = bindings_store.build_suggestion_merge_moves(
                conn, suggestion_id, extra_reassignments=reassignments,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        excluded = set(body.excluded_file_ids)
        moves = [m for m in plan.moves if m[0] not in excluded]

        if body.expected_move_count is not None and len(moves) != body.expected_move_count:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Plan changed: expected {body.expected_move_count} moves but "
                    f"server computed {len(moves)}. Refresh and re-confirm."
                ),
            )

        # Bind before move: a partial move against a correctly-created binding
        # self-heals on the next organize plan (the file just gets picked up
        # again); files moved without a binding do not. Doing this first also
        # means an IntegrityError (person already bound elsewhere) is caught
        # as a clean 409 before any file is touched.
        if not body.dry_run:
            try:
                bindings_store.accept_suggestion(conn, suggestion_id)
            except (BindingConflictError, ValueError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        ops = [
            FileOp(source=library_root / src, dest_folder=library_root / dest, mode="move")
            for _fid, src, dest, _kind in moves
        ]

        manifest_path = new_manifest_path(library_data_dir(library_root), "faces-merge")
        report = safety_execute(ops, manifest_path=manifest_path, dry_run=body.dry_run)

        if not body.dry_run:
            record_action(
                conn,
                kind="faces-merge-into-folder",
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

            if plan.person_id is not None:
                # Record "not this person" durably for everything the user kept
                # out of the move (excluded, sent elsewhere, or rejected as an
                # in-folder outlier) so a later organize run never silently
                # re-files it under this person — see rejected_persons.py.
                rejected_ids = (
                    list(excluded) + [r.file_id for r in body.reassignments] + list(body.rejected_outlier_file_ids)
                )
                rejected_persons.reject_person_files(conn, provider_id, plan.person_id, rejected_ids)

                # Outlier files the user confirmed ARE this person get assigned
                # directly — otherwise the review the user just did is dropped
                # on the floor and the same files resurface as outliers forever.
                if body.confirmed_outlier_file_ids:
                    placeholders = ",".join("?" * len(body.confirmed_outlier_file_ids))
                    conn.execute(
                        f"UPDATE faces SET person_id = ? WHERE provider_id = ? AND file_id IN ({placeholders})",
                        (plan.person_id, provider_id, *body.confirmed_outlier_file_ids),
                    )

            conn.commit()

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


@router.post("/libraries/{library_id}/bindings/suggestions/{suggestion_id}/dismiss")
def dismiss_binding_suggestion(library_id: str, suggestion_id: int, request: Request):
    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        ok = bindings_store.dismiss_suggestion(conn, suggestion_id)
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="Suggestion not found or not pending")
    return {"ok": True}


@router.get("/libraries/{library_id}/bindings", response_model=BindingsOut)
def list_bindings(library_id: str, request: Request):
    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        provider_id = _require_provider_id(conn, library_root)
        records = bindings_store.list_bindings(conn, provider_id)
        out = [
            BindingOut(
                id=r.id, folder_rel=r.folder_rel, kind=r.kind, person_ids=r.person_ids,
                person_names=_person_names(conn, r.person_ids),
                accepted_outlier_file_ids=r.accepted_outlier_file_ids,
                outliers=_outliers_out(r), created_at=r.created_at,
            )
            for r in records
        ]
    finally:
        conn.close()
    return BindingsOut(provider_id=provider_id, bindings=out)


@router.post("/libraries/{library_id}/bindings/{binding_id}/release")
def release_binding(library_id: str, binding_id: int, request: Request):
    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        ok = bindings_store.release_binding(conn, binding_id)
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="Binding not found")
    return {"ok": True}


@router.post("/libraries/{library_id}/bindings/{binding_id}/outliers", response_model=BindingOut)
def set_binding_outliers(library_id: str, binding_id: int, body: AcceptOutliersIn, request: Request):
    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        record = bindings_store.set_accepted_outliers(conn, binding_id, body.file_ids)
        if record is None:
            raise HTTPException(status_code=404, detail="Binding not found")
        return BindingOut(
            id=record.id, folder_rel=record.folder_rel, kind=record.kind,
            person_ids=record.person_ids, person_names=_person_names(conn, record.person_ids),
            accepted_outlier_file_ids=record.accepted_outlier_file_ids,
            outliers=_outliers_out(record),
            created_at=record.created_at,
        )
    finally:
        conn.close()
