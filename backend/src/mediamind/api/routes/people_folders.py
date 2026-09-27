"""People folders: counts, primary folders, moving a person's files, group pictures, auto-filing.

  GET  /v1/libraries/{id}/teach/stats?under=                 {total, sorted, unsorted, no_faces}
  PUT  /v1/libraries/{id}/teach/people/{pid}/primary-location  {path | null}
  GET  /v1/libraries/{id}/teach/people/{pid}/move-plan       what "Move files" would do
  POST /v1/libraries/{id}/teach/people/{pid}/move            {expected_plan_hash} -> job
  GET  /v1/libraries/{id}/teach/groups                       group pictures waiting for a choice
  POST /v1/libraries/{id}/teach/groups/place                 answer one (and maybe remember it)
  GET  /v1/auto-file                                         {library_ids} opted in
  GET  /v1/libraries/{id}/auto-file                          {enabled}
  PUT  /v1/libraries/{id}/auto-file                          {enabled}

See core/placement.py and docs/PEOPLE_FOLDERS_AUTOFILE_PLAN.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from mediamind.core import placement
from mediamind.core.organize_plan import safe_folder_name
from mediamind.store import global_people as gp_store
from mediamind.store.db import open_library_db

router = APIRouter(tags=["people-folders"])


class PrimaryLocationIn(BaseModel):
    path: str | None = None


class MoveIn(BaseModel):
    expected_plan_hash: str


class PlaceIn(BaseModel):
    file_id: int
    choice: Literal["person", "new", "stay"]
    person: str | None = None       # name, for "person"
    folder_name: str | None = None  # for "new"
    remember: bool = True           # also for every picture of exactly these people


class AutoFileIn(BaseModel):
    enabled: bool


def _library(request: Request, library_id: str):
    lib = request.app.state.registry.get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    return lib


def _person(request: Request, library_id: str, person_id: int) -> tuple[str, str]:
    conn = open_library_db(Path(_library(request, library_id).path))
    try:
        row = conn.execute("SELECT name, provider_id FROM persons WHERE id = ?", (person_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown person")
    if not row["name"]:
        raise HTTPException(status_code=422, detail="Name this person first.")
    return row["name"], row["provider_id"]


def _invalidate_people_cache() -> None:
    from mediamind.api.routes.global_people import _invalidate_cache

    _invalidate_cache()


@router.get("/libraries/{library_id}/teach/stats")
def stats(library_id: str, request: Request, under: str | None = Query(default=None)):
    conn = open_library_db(Path(_library(request, library_id).path))
    try:
        return placement.file_stats(conn, under)
    finally:
        conn.close()


@router.put("/libraries/{library_id}/teach/people/{person_id}/primary-location")
def set_primary_location(library_id: str, person_id: int, body: PrimaryLocationIn, request: Request):
    """The person's physical folder, for everyone of that name in every folder. Moves nothing."""
    name, provider_id = _person(request, library_id, person_id)
    gp = gp_store.open_global_db()
    try:
        path = placement.set_primary_folder(gp, library_id, person_id, name, provider_id, body.path)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        gp.close()
    _invalidate_people_cache()
    return {"ok": True, "primary_location": path}


def _question_out(q: placement.GroupQuestion) -> dict:
    f = q.file
    return {
        "library_id": f.library_id, "file_id": f.file_id, "path": f.path, "abs_path": str(f.abs_path),
        "people": sorted(f.names.values(), key=str.casefold),
        "folders": [{"name": f.names[k], "path": p} for k, p in sorted(q.primaries.items())],
        "new_folder_parent": str(q.new_folder_parent),
    }


@router.get("/libraries/{library_id}/teach/people/{person_id}/move-plan")
def move_plan(library_id: str, person_id: int, request: Request):
    """Every picture and video of this person, in every folder, that isn't in their folder yet.
    Group pictures without a rule are counted but not moved: they wait for a choice."""
    name, _ = _person(request, library_id, person_id)
    gp = gp_store.open_global_db()
    try:
        primary = placement.primary_folders(gp).get(placement.name_key(name))
        if not primary:
            raise HTTPException(status_code=422, detail="Choose this person's folder first.")
        moves, questions = placement.person_plan(gp, request.app.state.registry, name)
    finally:
        gp.close()
    return {
        "name": name, "primary_location": primary, "moves": len(moves),
        "to_group_folders": sum(1 for m in moves if m.dest != primary),
        "groups_waiting": len(questions), "plan_hash": placement.plan_hash(moves),
    }


@router.post("/libraries/{library_id}/teach/people/{person_id}/move", status_code=202)
def move_person_files(library_id: str, person_id: int, body: MoveIn, request: Request):
    from mediamind.api.routes.organize import _snapshot

    name, _ = _person(request, library_id, person_id)
    registry, jm = request.app.state.registry, request.app.state.job_manager
    running = jm.running_for(library_id)
    if running:
        raise HTTPException(status_code=409, detail=f"A {running.type} job is still running here. Try again when it's done.")

    def runner(ctx) -> dict:
        gp = gp_store.open_global_db()
        try:
            moves, _ = placement.person_plan(gp, registry, name)
            if placement.plan_hash(moves) != body.expected_plan_hash:
                raise ValueError("The files changed since you looked. Open Move files again.")
            if not moves:
                return {"planned": 0, "moved": 0, "errors": []}
            return placement.execute_moves(
                gp, registry, moves, label=f"move-{placement.name_key(name)}",
                on_progress=lambda d, t: ctx.report_progress(d, t, "moving"), should_cancel=ctx.cancelled)
        finally:
            gp.close()

    job = jm.start(library_id, "people-move", runner)
    _invalidate_people_cache()
    return _snapshot(job)


@router.get("/libraries/{library_id}/teach/groups")
def group_pictures(library_id: str, request: Request):
    lib = _library(request, library_id)
    conn = open_library_db(Path(lib.path))
    gp = gp_store.open_global_db()
    try:
        return [_question_out(q) for q in placement.library_questions(gp, conn, library_id, Path(lib.path))]
    finally:
        gp.close()
        conn.close()


@router.post("/libraries/{library_id}/teach/groups/place")
def place_group_picture(library_id: str, body: PlaceIn, request: Request):
    """Put a group picture in one person's folder, a new group folder, or leave it. With
    `remember`, the choice becomes the rule for every picture of exactly these people, here and
    in watched folders, and this folder's other such pictures move now too."""
    lib = _library(request, library_id)
    root = Path(lib.path)
    registry, jm = request.app.state.registry, request.app.state.job_manager
    if jm.running_for(library_id):
        raise HTTPException(status_code=409, detail="A job is still running here. Try again when it's done.")
    conn = open_library_db(root)
    gp = gp_store.open_global_db()
    try:
        questions = {q.file.file_id: q for q in placement.library_questions(gp, conn, library_id, root)}
        q = questions.get(body.file_id)
        if q is None:
            raise HTTPException(status_code=404, detail="This picture doesn't need a choice any more.")
        if body.choice == "person":
            dest = next((p for k, p in q.primaries.items() if k == placement.name_key(body.person or "")), None)
            if dest is None:
                raise HTTPException(status_code=422, detail="That person has no folder yet.")
        elif body.choice == "new":
            if not body.folder_name or not body.folder_name.strip():
                raise HTTPException(status_code=422, detail="Type a name for the new folder.")
            dest = str(q.new_folder_parent / safe_folder_name(body.folder_name))
        else:
            dest = None

        same = [q]
        if body.remember:
            placement.set_group_rule(gp, list(q.file.names.values()), dest)
            key = placement.group_key(set(q.file.names))
            same = [o for o in questions.values() if placement.group_key(set(o.file.names)) == key]
        if dest is None:
            return {"moved": 0, "remembered": body.remember}
        moves = [placement.Placement(o.file, dest) for o in same]
    finally:
        gp.close()
        conn.close()

    def runner(ctx) -> dict:
        g = gp_store.open_global_db()
        try:
            return placement.execute_moves(g, registry, moves, label="group",
                                           on_progress=lambda d, t: ctx.report_progress(d, t, "moving"))
        finally:
            g.close()

    job = jm.run_sync(library_id, "people-move", runner)
    if job.state == "failed":
        raise HTTPException(status_code=500, detail=job.error or "The move failed.")
    return {**job.result, "remembered": body.remember, "dest": dest}


@router.get("/auto-file")
def auto_file_libraries():
    """Every watched folder that files new pictures into people's folders."""
    gp = gp_store.open_global_db()
    try:
        return {"library_ids": [r["library_id"] for r in gp.execute("SELECT library_id FROM auto_file_libraries")]}
    finally:
        gp.close()


@router.get("/libraries/{library_id}/auto-file")
def get_auto_file(library_id: str, request: Request):
    _library(request, library_id)
    gp = gp_store.open_global_db()
    try:
        return {"enabled": placement.auto_file_enabled(gp, library_id)}
    finally:
        gp.close()


@router.put("/libraries/{library_id}/auto-file")
def set_auto_file(library_id: str, body: AutoFileIn, request: Request):
    """Opt a watched folder in (or out) of filing new pictures into people's folders by itself."""
    _library(request, library_id)
    gp = gp_store.open_global_db()
    try:
        placement.set_auto_file(gp, library_id, body.enabled)
    finally:
        gp.close()
    return {"enabled": body.enabled}
