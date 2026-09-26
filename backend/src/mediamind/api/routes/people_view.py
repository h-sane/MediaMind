"""People view: cross-library overview (Faces + Folders modes), pins and
user-made collections. See docs/PEOPLE_VIEW_V2_DESIGN.md. Every write here
changes only `people_layout.json` in app data — never a file on disk."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from mediamind.api.models import (
    PeopleCollectionNameIn,
    PeopleCollectionOut,
    PeopleDuplicateOut,
    PeopleEntryOut,
    PeopleKeysIn,
    PeopleMergeIn,
    PeopleMemberOut,
    PeopleNodeOut,
    PeopleOverviewOut,
    PeoplePinIn,
    PeoplePinOut,
)
from mediamind.core.global_people import open_library_db, resolve_link_suggestion
from mediamind.core.people_overview import Entry, Node, load_entries, load_overview
from mediamind.store import global_people as gp_store
from mediamind.api.routes.persons import render_face_thumb
from mediamind.store.persons import get_face, latest_faces_scan, merge_persons
from mediamind.store.people_layout import PeopleLayoutStore

router = APIRouter(tags=["people-view"], prefix="/people-view")


def _layout(request: Request) -> PeopleLayoutStore:
    store = getattr(request.app.state, "people_layout", None)
    if store is None:
        store = request.app.state.people_layout = PeopleLayoutStore()
    return store


def _entry_out(e: Entry) -> PeopleEntryOut:
    return PeopleEntryOut(
        id=e.id,
        name=e.name,
        auto_label=e.auto_label,
        face_count=e.face_count,
        media_count=e.media_count,
        members=[PeopleMemberOut(**vars(m)) for m in e.members],
        keys=e.keys,
        folder_path=e.folder_path,
        pinned=e.pinned,
        collection_id=e.collection_id,
        duplicates=[PeopleDuplicateOut(entry_id=i, similarity=s) for i, s in e.duplicates],
    )


def _node_out(n: Node) -> PeopleNodeOut:
    return PeopleNodeOut(
        kind=n.kind,  # type: ignore[arg-type]
        id=n.id,
        path=n.path,
        name=n.name,
        person_ids=n.person_ids,
        subgroups=[_node_out(g) for g in n.subgroups],
        total_persons=n.total_persons,
        pinned=n.pinned,
    )


def _walk(nodes: list[Node]):
    for n in nodes:
        yield n
        yield from _walk(n.subgroups)


def _resolve_pins(pin_keys: list[str], entries: list[Entry], forest: list[Node]) -> list[PeoplePinOut]:
    entry_of_key = {k: e for e in entries for k in e.keys}
    folder_nodes = {n.path: n for n in _walk(forest) if n.kind == "group"}
    coll_nodes = {n.id: n for n in _walk(forest) if n.kind == "collection"}
    out: list[PeoplePinOut] = []
    seen: set[str] = set()
    for key in pin_keys:
        if key.startswith("p:"):
            e = entry_of_key.get(key)
            if e is not None:
                if e.id in seen:
                    continue  # several keys of one identity pin it once
                seen.add(e.id)
            out.append(
                PeoplePinOut(
                    key=key,
                    kind="person",
                    ref_id=e.id if e else None,
                    label=(e.name or e.auto_label) if e else None,
                    available=e is not None,
                )
            )
        elif key.startswith("f:"):
            n = folder_nodes.get(key[2:])
            out.append(
                PeoplePinOut(
                    key=key,
                    kind="folder",
                    ref_id=n.id if n else None,
                    label=n.name if n else key[2:].replace("\\", "/").rsplit("/", 1)[-1],
                    available=n is not None,
                )
            )
        elif key.startswith("c:"):
            n = coll_nodes.get(key[2:])
            out.append(
                PeoplePinOut(
                    key=key,
                    kind="collection",
                    ref_id=n.id if n else None,
                    label=n.name if n else None,
                    available=n is not None,
                )
            )
    return out


@router.get("/overview", response_model=PeopleOverviewOut)
def overview(request: Request):
    entries, forest, collections, pin_keys, hidden = load_overview(request.app.state.registry, _layout(request))
    return PeopleOverviewOut(
        entries=[_entry_out(e) for e in entries],
        tree=[_node_out(n) for n in forest],
        collections=[PeopleCollectionOut(**c) for c in collections],
        pins=_resolve_pins(pin_keys, entries, forest),
        hidden=[_entry_out(e) for e in hidden],
    )


@router.post("/pins")
def pin(body: PeoplePinIn, request: Request):
    _layout(request).pin(body.key)
    return {"ok": True}


@router.post("/unpin")
def unpin(body: PeopleKeysIn, request: Request):
    _layout(request).unpin(body.keys)
    return {"ok": True}


@router.put("/pins/order")
def reorder_pins(body: PeopleKeysIn, request: Request):
    _layout(request).reorder_pins(body.keys)
    return {"ok": True}


@router.post("/collections", response_model=PeopleCollectionOut)
def create_collection(body: PeopleCollectionNameIn, request: Request):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="A collection needs a name")
    return PeopleCollectionOut(**_layout(request).create_collection(body.name))


@router.patch("/collections/{collection_id}")
def rename_collection(collection_id: str, body: PeopleCollectionNameIn, request: Request):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="A collection needs a name")
    if not _layout(request).rename_collection(collection_id, body.name):
        raise HTTPException(status_code=404, detail="Unknown collection")
    return {"ok": True}


@router.delete("/collections/{collection_id}")
def delete_collection(collection_id: str, request: Request):
    if not _layout(request).delete_collection(collection_id):
        raise HTTPException(status_code=404, detail="Unknown collection")
    return {"ok": True}


@router.post("/collections/{collection_id}/members")
def add_collection_members(collection_id: str, body: PeopleKeysIn, request: Request):
    """Drag-drop target: moves (never copies) these people/folders into the
    collection, out of any other."""
    if not _layout(request).add_members(collection_id, body.keys):
        raise HTTPException(status_code=404, detail="Unknown collection")
    return {"ok": True}


@router.post("/collections/remove-members")
def remove_collection_members(body: PeopleKeysIn, request: Request):
    """Returns these people/folders to their automatic place."""
    _layout(request).remove_members(body.keys)
    return {"ok": True}


@router.post("/hide")
def hide(body: PeopleKeysIn, request: Request):
    """"Remove this person": ignored in the People view from now on, including
    after rescans (keyed by person id). Nothing on disk or in scan data changes."""
    _layout(request).hide(body.keys)
    return {"ok": True}


@router.post("/unhide")
def unhide(body: PeopleKeysIn, request: Request):
    _layout(request).unhide(body.keys)
    return {"ok": True}


def _parse_person_key(key: str) -> tuple[str, int]:
    _, library_id, person_id = key.split(":", 2)
    return library_id, int(person_id)


@router.post("/merge")
def merge(body: PeopleMergeIn, request: Request):
    """Merge one identity into another. Members in the same library are merged
    outright (faces move, centroid recomputed); a member from a library the
    target has no person in is linked into the target's global identity."""
    registry = request.app.state.registry
    try:
        sources = [_parse_person_key(k) for k in body.source_keys if k.startswith("p:")]
        targets = [_parse_person_key(k) for k in body.target_keys if k.startswith("p:")]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Malformed person key") from exc
    if not sources or not targets or set(sources) & set(targets):
        raise HTTPException(status_code=422, detail="Nothing to merge")

    target_in_lib = {lib_id: pid for lib_id, pid in targets}
    for lib_id, pid in sources:
        if lib_id not in target_in_lib:
            continue
        lib = registry.get(lib_id)
        if lib is None:
            raise HTTPException(status_code=404, detail="Unknown library")
        conn = open_library_db(lib)
        try:
            if not merge_persons(conn, pid, target_in_lib[lib_id]):
                raise HTTPException(status_code=422, detail="Cannot merge these two people")
        finally:
            conn.close()

    cross = [(lib_id, pid) for lib_id, pid in sources if lib_id not in target_in_lib]
    if cross:
        t_lib, t_pid = targets[0]
        gp_conn = gp_store.open_global_db()
        try:
            if gp_store.global_for_local(gp_conn, t_lib, t_pid) is None:
                entry = next((e for e in load_entries(registry)[0] if f"p:{t_lib}:{t_pid}" in e.keys), None)
                gid = gp_store.create_global_person(gp_conn, (entry.name if entry else None) or "Person")
                gp_store.link(gp_conn, gid, t_lib, t_pid, _provider_id(registry, t_lib))
            for lib_id, pid in cross:
                resolve_link_suggestion(gp_conn, t_lib, t_pid, lib_id, pid, _provider_id(registry, lib_id))
        finally:
            gp_conn.close()
    return {"ok": True}


def _provider_id(registry, library_id: str) -> str:
    lib = registry.get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    conn = open_library_db(lib)
    try:
        scan = latest_faces_scan(conn)
        if scan is None:
            raise HTTPException(status_code=422, detail="Library has no face scan")
        return json.loads(scan["params"] or "{}").get("provider_id", "")
    finally:
        conn.close()


_THUMB_FACES_TRIED = 8
_THUMB_TIME_BUDGET_S = 25.0  # a hung video decode must not stall a card forever
_VERIFY_BATCH_BUDGET_S = 40.0


def _probe_person(request: Request, library_id: str, person_id: int, size: int, deadline: float | None = None):
    """Try a person's largest faces, in turn, until one can be cropped.
    Returns ("ok", response), ("unusable", None) or ("unknown", None).

    "unusable": the person has no faces, or every face's file is present but cannot
    be decoded — not a person, a recognition mistake; it is recorded so it leaves the
    People view for good. "unknown": missing files or a slow decode are not evidence
    (drive unplugged, file moved), so nothing is recorded."""
    lib = request.app.state.registry.get(library_id)
    if lib is None:
        return "unknown", None
    root = Path(lib.path)
    conn = open_library_db(lib)
    try:
        face_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM faces WHERE person_id = ? "
                "ORDER BY (bbox_x2 - bbox_x1) * (bbox_y2 - bbox_y1) DESC LIMIT ?",
                (person_id, _THUMB_FACES_TRIED),
            ).fetchall()
        ]
        infos = [i for i in (get_face(conn, fid) for fid in face_ids) if i is not None]
    finally:
        conn.close()

    started = time.monotonic()
    inconclusive = False
    for info in infos:
        if time.monotonic() - started > _THUMB_TIME_BUDGET_S or (deadline is not None and time.monotonic() > deadline):
            inconclusive = True
            break
        status, response = render_face_thumb(library_id, root, info, size)
        if response is not None:
            return "ok", response
        if status == "missing":
            inconclusive = True
    if inconclusive:
        return "unknown", None

    _layout(request).mark_unusable(f"p:{library_id}:{person_id}")
    return "unusable", None


@router.get("/persons/{library_id}/{person_id}/thumbnail")
def person_thumbnail(
    library_id: str,
    person_id: int,
    request: Request,
    size: int = Query(default=160, ge=48, le=512),
):
    """The face to show on a person's card: the largest face that can be cropped.
    A face that cannot be decoded is skipped for the next, within this one request.
    410 means the engine found this is not a person (see `_probe_person`); 404 means
    no face is available right now."""
    if request.app.state.registry.get(library_id) is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    status, response = _probe_person(request, library_id, person_id, size)
    if response is not None:
        return response
    if status == "unusable":
        raise HTTPException(status_code=410, detail="Not a usable person")
    raise HTTPException(status_code=404, detail="No face is available right now")


@router.post("/verify")
def verify(body: PeopleKeysIn, request: Request):
    """Background sweep, in small batches from the People page: run the card
    thumbnail check for these persons now (which also warms the thumbnail cache)
    and report the ones found not to be people. Persons not reached inside the batch
    time budget are simply left for the next sweep."""
    deadline = time.monotonic() + _VERIFY_BATCH_BUDGET_S
    unusable: list[str] = []
    for key in body.keys:
        if time.monotonic() > deadline:
            break
        try:
            _, library_id, person_id = key.split(":", 2)
            status, _ = _probe_person(request, library_id, int(person_id), 160, deadline)
        except (ValueError, OSError):
            continue
        if status == "unusable":
            unusable.append(key)
    return {"unusable": unusable}
