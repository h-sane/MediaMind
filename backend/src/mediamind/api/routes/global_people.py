"""Cross-library People: one identity spanning multiple registered
libraries (drives/mounts), always linked by explicit user action — see
`core/global_people.py` and `store/global_people.py`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from mediamind.api.models import (
    GlobalLinkSuggestionOut,
    GlobalLinkSuggestionPairIn,
    GlobalPersonCreateIn,
    GlobalPersonLinkIn,
    GlobalPersonMemberOut,
    GlobalPersonOut,
    GlobalPersonPrimaryLocationIn,
    GlobalPersonRenameIn,
)
from mediamind.core.global_people import list_aggregated, list_link_suggestions, open_library_db, resolve_link_suggestion
from mediamind.core.libraries import LibraryRegistry
from mediamind.store import global_people as gp_store
from mediamind.store.persons import latest_faces_scan

router = APIRouter(tags=["global-people"], prefix="/global")

# Aggregation opens every registered library's DB; a short in-process TTL
# cache avoids paying that cost on every keystroke/poll of the Global People
# view without the complexity of a materialized table (Phase 3 ceiling —
# revisit only if measured slow at real scale).
_CACHE_TTL_SECONDS = 5.0
_cache: dict[str, tuple[float, list[dict]]] = {}


def _registry(request: Request) -> LibraryRegistry:
    return request.app.state.registry


def _invalidate_cache() -> None:
    _cache.clear()


def _aggregated(request: Request) -> list[dict]:
    now = time.time()
    cached = _cache.get("all")
    if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    gp_conn = gp_store.open_global_db()
    try:
        result = list_aggregated(gp_conn, _registry(request))
    finally:
        gp_conn.close()
    _cache["all"] = (now, result)
    return result


def _to_out(entry: dict) -> GlobalPersonOut:
    return GlobalPersonOut(
        id=entry["id"],
        name=entry["name"],
        primary_location=entry["primary_location"],
        media_count=entry["media_count"],
        members=[GlobalPersonMemberOut(**m) for m in entry["members"]],
    )


@router.get("/people", response_model=list[GlobalPersonOut])
def list_global_people(request: Request):
    return [_to_out(e) for e in _aggregated(request)]


@router.get("/people/{global_person_id}", response_model=GlobalPersonOut)
def get_global_person(global_person_id: int, request: Request):
    for entry in _aggregated(request):
        if entry["id"] == global_person_id:
            return _to_out(entry)
    raise HTTPException(status_code=404, detail="Unknown global person")


@router.post("/people", response_model=GlobalPersonOut)
def create_global_person(body: GlobalPersonCreateIn, request: Request):
    gp_conn = gp_store.open_global_db()
    try:
        gid = gp_store.create_global_person(gp_conn, body.name)
    finally:
        gp_conn.close()
    _invalidate_cache()
    return _to_out({"id": gid, "name": body.name, "primary_location": None, "media_count": 0, "members": []})


@router.patch("/people/{global_person_id}")
def rename_global_person(global_person_id: int, body: GlobalPersonRenameIn, request: Request):
    gp_conn = gp_store.open_global_db()
    try:
        ok = gp_store.rename_global_person(gp_conn, global_person_id, body.name)
    finally:
        gp_conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="Unknown global person")
    _invalidate_cache()
    return {"ok": True}


@router.delete("/people/{global_person_id}")
def delete_global_person(global_person_id: int, request: Request):
    gp_conn = gp_store.open_global_db()
    try:
        ok = gp_store.delete_global_person(gp_conn, global_person_id)
    finally:
        gp_conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="Unknown global person")
    _invalidate_cache()
    return {"ok": True}


@router.put("/people/{global_person_id}/primary-location")
def set_primary_location(global_person_id: int, body: GlobalPersonPrimaryLocationIn, request: Request):
    """Absolute destination folder for this person's future physical-move
    suggestions (Phase 6/7). Deliberately NOT run through
    `organize_plan.safe_dest_folder_rel` — that helper only accepts paths
    relative to one library's root, and a global person's destination is
    meant to live in a different library/drive entirely. Setting this moves
    nothing by itself."""
    path = body.path
    if path is not None:
        p = Path(path).expanduser()
        if not p.is_dir():
            raise HTTPException(status_code=422, detail="Primary location must be an existing folder")
        path = str(p.resolve())
    gp_conn = gp_store.open_global_db()
    try:
        ok = gp_store.set_primary_location(gp_conn, global_person_id, path)
    finally:
        gp_conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="Unknown global person")
    _invalidate_cache()
    return {"ok": True, "primary_location": path}


@router.post("/people/{global_person_id}/link")
def link_local_person(global_person_id: int, body: GlobalPersonLinkIn, request: Request):
    """Link a local (per-library) person to this global identity — always an
    explicit user action (right from a suggestion, Phase 4, or by hand),
    never automatic regardless of similarity score."""
    registry = _registry(request)
    lib = registry.get(body.library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")

    conn = open_library_db(lib)
    try:
        scan = latest_faces_scan(conn)
        if scan is None:
            raise HTTPException(status_code=422, detail="Library has no face scan")
        provider_id = json.loads(scan["params"] or "{}").get("provider_id", "")
    finally:
        conn.close()

    gp_conn = gp_store.open_global_db()
    try:
        if gp_store.get_global_person(gp_conn, global_person_id) is None:
            raise HTTPException(status_code=404, detail="Unknown global person")
        gp_store.link(gp_conn, global_person_id, body.library_id, body.local_person_id, provider_id)
    finally:
        gp_conn.close()
    _invalidate_cache()
    return {"ok": True}


@router.post("/people/unlink")
def unlink_local_person(body: GlobalPersonLinkIn, request: Request):
    gp_conn = gp_store.open_global_db()
    try:
        ok = gp_store.unlink(gp_conn, body.library_id, body.local_person_id)
    finally:
        gp_conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="Link not found")
    _invalidate_cache()
    return {"ok": True}


@router.get("/link-suggestions", response_model=list[GlobalLinkSuggestionOut])
def link_suggestions(request: Request):
    """"Are these the same person, in two different libraries?" pairs — never
    auto-linked, regardless of similarity (see `resolve_link_suggestion`
    docstring)."""
    gp_conn = gp_store.open_global_db()
    try:
        suggestions = list_link_suggestions(gp_conn, _registry(request))
    finally:
        gp_conn.close()
    return [GlobalLinkSuggestionOut(**s) for s in suggestions]


@router.post("/link-suggestions/link")
def accept_link_suggestion(body: GlobalLinkSuggestionPairIn, request: Request):
    """Explicit accept — the only way two libraries' persons ever become one
    global identity."""
    registry = _registry(request)
    lib_b = registry.get(body.library_id_b)
    if lib_b is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    conn = open_library_db(lib_b)
    try:
        scan = latest_faces_scan(conn)
        if scan is None:
            raise HTTPException(status_code=422, detail="Library has no face scan")
        provider_id = json.loads(scan["params"] or "{}").get("provider_id", "")
    finally:
        conn.close()

    gp_conn = gp_store.open_global_db()
    try:
        try:
            resolve_link_suggestion(
                gp_conn,
                body.library_id_a,
                body.local_person_id_a,
                body.library_id_b,
                body.local_person_id_b,
                provider_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        gp_conn.close()
    _invalidate_cache()
    return {"ok": True}


@router.post("/link-suggestions/dismiss")
def dismiss_link_suggestion(body: GlobalLinkSuggestionPairIn, request: Request):
    """"Not the same person" — durably suppress this pair from future
    link-suggestion results."""
    gp_conn = gp_store.open_global_db()
    try:
        gp_store.dismiss_link_suggestion(
            gp_conn,
            body.library_id_a,
            body.local_person_id_a,
            body.library_id_b,
            body.local_person_id_b,
        )
    finally:
        gp_conn.close()
    return {"ok": True}
