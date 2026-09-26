"""People view: cross-library overview (Faces + Folders modes), pins and
user-made collections. See docs/PEOPLE_VIEW_V2_DESIGN.md. Every write here
changes only `people_layout.json` in app data — never a file on disk."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from mediamind.api.models import (
    PeopleCollectionNameIn,
    PeopleCollectionOut,
    PeopleDuplicateOut,
    PeopleEntryOut,
    PeopleKeysIn,
    PeopleMemberOut,
    PeopleNodeOut,
    PeopleOverviewOut,
    PeoplePinIn,
    PeoplePinOut,
)
from mediamind.core.people_overview import Entry, Node, load_overview
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
    entries, forest, collections, pin_keys = load_overview(request.app.state.registry, _layout(request))
    return PeopleOverviewOut(
        entries=[_entry_out(e) for e in entries],
        tree=[_node_out(n) for n in forest],
        collections=[PeopleCollectionOut(**c) for c in collections],
        pins=_resolve_pins(pin_keys, entries, forest),
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
