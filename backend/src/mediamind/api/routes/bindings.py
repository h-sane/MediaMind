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
    OutlierFileOut,
    RefreshSuggestionsOut,
)
from mediamind.config import library_data_dir
from mediamind.core.libraries import LibraryRegistry
from mediamind.store import bindings as bindings_store
from mediamind.store.bindings import BindingConflictError
from mediamind.store.db import library_db_path, open_db
from mediamind.store.persons import latest_faces_scan

router = APIRouter(tags=["bindings"])


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


def _outliers_out(record) -> list[OutlierFileOut]:
    return [
        OutlierFileOut(file_id=o.file_id, path=o.path, kind=o.kind, accepted=o.accepted)
        for o in record.outliers
    ]


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
                outlier_file_ids=r.outlier_file_ids, status=r.status, created_at=r.created_at,
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
