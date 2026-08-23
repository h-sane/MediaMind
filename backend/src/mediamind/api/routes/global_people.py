"""Cross-library People: one identity spanning multiple registered
libraries (drives/mounts), always linked by explicit user action — see
`core/global_people.py` and `store/global_people.py`.
"""

from __future__ import annotations

import json
import time
from contextlib import ExitStack
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from mediamind.api.models import (
    GlobalLinkSuggestionOut,
    GlobalLinkSuggestionPairIn,
    GlobalMoveExecuteIn,
    GlobalMoveExecuteOut,
    GlobalMoveSuggestionDismissIn,
    GlobalMoveSuggestionGroupOut,
    GlobalMoveUndoInfoOut,
    GlobalMoveUndoOut,
    GlobalPersonCreateIn,
    GlobalPersonLinkIn,
    GlobalPersonMemberOut,
    GlobalPersonOut,
    GlobalPersonPrimaryLocationIn,
    GlobalPersonRenameIn,
)
from mediamind.core.global_people import (
    MoveRequestItem,
    execute_move_plan,
    execute_undo,
    list_aggregated,
    list_link_suggestions,
    list_move_suggestions,
    open_library_db,
    plan_undo,
    resolve_link_suggestion,
)
from mediamind.core.jobs import JobContext
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


@router.get("/move-suggestions", response_model=list[GlobalMoveSuggestionGroupOut])
def move_suggestions(request: Request):
    """Files virtually tagged to a person with a primary location set, not
    yet physically there — a live read (see `list_move_suggestions`
    docstring), nothing here moves a file. Execution lives in Phase 7's
    dedicated endpoint, always behind an explicit confirm."""
    gp_conn = gp_store.open_global_db()
    try:
        groups = list_move_suggestions(gp_conn, _registry(request))
    finally:
        gp_conn.close()
    return [GlobalMoveSuggestionGroupOut(**g) for g in groups]


@router.post("/move-suggestions/dismiss")
def dismiss_move_suggestion(body: GlobalMoveSuggestionDismissIn, request: Request):
    """Deselect one file from a person's move suggestions — durable, so it
    doesn't reappear on the next load."""
    gp_conn = gp_store.open_global_db()
    try:
        gp_store.dismiss_move_suggestion(gp_conn, body.global_person_id, body.content_hash)
    finally:
        gp_conn.close()
    return {"ok": True}


_MOVE_PLAN_GUARD_MARKERS = ("Plan changed", "Plan contents changed", "Nothing to move", "no primary location", "Unknown")


def _move_error_status(error: str) -> int:
    return 409 if any(marker in error for marker in _MOVE_PLAN_GUARD_MARKERS) else 500


@router.post("/move-suggestions/execute", response_model=GlobalMoveExecuteOut)
def execute_move_suggestions(body: GlobalMoveExecuteIn, request: Request):
    """Execute (or dry-run) a batch of cross-library physical moves — the
    ONLY endpoint that ever moves a file for the global-people feature.
    Call once with dry_run=true to get back `plan_hash`/counts, then again
    with dry_run=false and that hash to actually move (same preview ->
    execute pattern as `organize.py`).

    A real (non-dry-run) run goes through `JobManager.run_sync` so it's
    visible to `running_for()` for its whole duration; dry-run touches
    nothing on disk so it skips that guard entirely, same reasoning as
    organize.py's dry-run branch.
    """
    registry = _registry(request)
    items = [
        MoveRequestItem(global_person_id=i.global_person_id, library_id=i.library_id, file_id=i.file_id)
        for i in body.items
    ]

    if body.dry_run:
        gp_conn = gp_store.open_global_db()
        try:
            try:
                result = execute_move_plan(
                    gp_conn, registry, items,
                    dry_run=True,
                    expected_count=body.expected_count,
                    expected_plan_hash=body.expected_plan_hash,
                )
            except ValueError as exc:
                raise HTTPException(status_code=_move_error_status(str(exc)), detail=str(exc)) from exc
        finally:
            gp_conn.close()
        return GlobalMoveExecuteOut(**result)

    jm = request.app.state.job_manager
    source_libs = {i.library_id for i in body.items}
    for library_id in source_libs:
        if jm.running_for(library_id) is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Library {library_id} has a job already running — try again shortly",
            )

    def runner(ctx: JobContext) -> dict:
        gp_conn = gp_store.open_global_db()
        try:
            return execute_move_plan(
                gp_conn, registry, items,
                dry_run=False,
                expected_count=body.expected_count,
                expected_plan_hash=body.expected_plan_hash,
                on_progress=lambda done, total: ctx.report_progress(done, total, "moving"),
                should_cancel=ctx.cancelled,
            )
        finally:
            gp_conn.close()

    # Mark every source library busy for the move's whole duration so a
    # concurrent scan/organize on any of them is blocked (the job itself runs
    # under a synthetic id for progress; without these marks it would be
    # invisible to `running_for(source_lib)`, letting an organize race it).
    with ExitStack() as stack:
        for library_id in source_libs:
            stack.enter_context(jm.mark_busy(library_id, "global-move-execute"))
        job = jm.run_sync("__global_move__", "global-move-execute", runner)
    if job.state == "failed":
        error = job.error or "Move failed"
        raise HTTPException(status_code=_move_error_status(error), detail=error)

    _invalidate_cache()  # membership under primary_location changed
    return GlobalMoveExecuteOut(**job.result)


@router.get("/moves/undoable", response_model=GlobalMoveUndoInfoOut)
def undoable_move(request: Request):
    """Does a reversible cross-library move exist, and what would undoing it
    do? Drives whether the Suggestions tab shows an "Undo last move"
    affordance (mirrors organize.py's undo being offered only when there's
    something to reverse)."""
    gp_conn = gp_store.open_global_db()
    try:
        plan = plan_undo(gp_conn, _registry(request))
    finally:
        gp_conn.close()
    if plan is None:
        return GlobalMoveUndoInfoOut(available=False, file_count=0, destinations=[])
    return GlobalMoveUndoInfoOut(
        available=True,
        file_count=len(plan.ops),
        destinations=plan.undoable.dest_folders,
    )


@router.post("/moves/undo", response_model=GlobalMoveUndoOut)
def undo_move(request: Request):
    """Reverse the most recent cross-library move batch, moving every file
    back to where it came from through the same copy-then-delete `execute()`.
    Guarded on the same libraries as a forward move so it can't race a scan."""
    registry = _registry(request)
    gp_conn = gp_store.open_global_db()
    try:
        plan = plan_undo(gp_conn, registry)
        if plan is None:
            raise HTTPException(status_code=404, detail="Nothing to undo")

        jm = request.app.state.job_manager
        for library_id in plan.involved_libraries:
            if jm.running_for(library_id) is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Library {library_id} has a job already running — try again shortly",
                )

        def runner(ctx: JobContext) -> dict:
            inner = gp_store.open_global_db()
            try:
                return execute_undo(
                    inner, plan,
                    on_progress=lambda done, total: ctx.report_progress(done, total, "undoing"),
                    should_cancel=ctx.cancelled,
                )
            finally:
                inner.close()

        with ExitStack() as stack:
            for library_id in plan.involved_libraries:
                stack.enter_context(jm.mark_busy(library_id, "global-move-execute"))
            job = jm.run_sync("__global_move_undo__", "global-move-execute", runner)
    finally:
        gp_conn.close()

    if job.state == "failed":
        raise HTTPException(status_code=500, detail=job.error or "Undo failed")
    _invalidate_cache()
    return GlobalMoveUndoOut(**job.result)
