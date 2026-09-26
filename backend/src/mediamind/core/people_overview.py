"""Cross-library People projection for the People view (design:
docs/PEOPLE_VIEW_V2_DESIGN.md).

Two shapes are served from one read:
  - a flat list of identities ("Faces" mode) — one entry per person, with a
    cross-library link collapsing several libraries' persons into one entry;
  - a folder forest ("Folders" mode) built from *absolute* folder paths, so
    `kpop/twice` and `kpop/ive`, scanned as separate libraries, share a `kpop`
    group without either scan knowing about the other.

`build_forest` is pure (no DB, no filesystem) so it is unit-tested directly;
`load_overview` does the reads.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from mediamind.core.global_people import _load_all_lib_face_data, list_link_suggestions
from mediamind.core.libraries import LibraryRegistry
from mediamind.store import global_people as gp_store
from mediamind.store.people_layout import PeopleLayoutStore, folder_key, person_key


@dataclass
class MemberRef:
    library_id: str
    library_name: str
    local_person_id: int
    sample_face_ids: list[int]


@dataclass
class Entry:
    id: str
    name: str | None
    auto_label: str
    face_count: int
    media_count: int
    members: list[MemberRef]
    keys: list[str]
    folder_path: str  # absolute folder that *contains* this person's home
    pinned: bool = False
    collection_id: str | None = None
    duplicates: list[tuple[str, float]] = field(default_factory=list)  # (entry id, similarity)


@dataclass
class Node:
    kind: str  # "group" | "collection"
    id: str  # normalised absolute path for a group, collection id for a collection
    path: str  # display absolute path ("" for a collection)
    name: str
    subgroups: list["Node"] = field(default_factory=list)
    person_ids: list[str] = field(default_factory=list)
    total_persons: int = 0
    pinned: bool = False


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _display_name(p: Path) -> str:
    return p.name or p.drive or str(p)


def build_forest(entries: list[Entry], collections: list[dict], pins: set[str]) -> list[Node]:
    """Group entries by containing folder into a forest, then overlay the user's
    collections. Empty groups are pruned; a chain of single-child, person-less
    ancestors at the top is collapsed so the tree starts where the user's
    scanned folders start to differ (never a bare `C:\\Users\\...` chain)."""
    by_id = {e.id: e for e in entries}
    in_collection: dict[str, str] = {}
    for c in collections:
        member_set = set(c["members"])
        for e in entries:
            if e.id not in in_collection and member_set.intersection(e.keys):
                in_collection[e.id] = c["id"]
                e.collection_id = c["id"]

    groups: dict[str, Node] = {}
    parent_of: dict[str, str | None] = {}

    def ensure(path: str) -> Node:
        nid = _norm(path)
        node = groups.get(nid)
        if node is not None:
            return node
        p = Path(path)
        node = Node(kind="group", id=nid, path=str(p), name=_display_name(p), pinned=folder_key(str(p)) in pins)
        groups[nid] = node
        parent = p.parent
        if parent != p:
            parent_node = ensure(str(parent))
            parent_node.subgroups.append(node)
            parent_of[nid] = parent_node.id
        else:
            parent_of[nid] = None
        return node

    for e in entries:
        if e.id in in_collection:
            continue
        ensure(e.folder_path).person_ids.append(e.id)

    coll_nodes: list[Node] = []
    moved: set[str] = set()
    for c in collections:
        node = Node(kind="collection", id=c["id"], path="", name=c["name"], pinned=f"c:{c['id']}" in pins)
        node.person_ids = [eid for eid, cid in in_collection.items() if cid == c["id"]]
        for key in c["members"]:
            if not key.startswith("f:"):
                continue
            target = groups.get(_norm(key[2:]))
            if target is None or target.id in moved:
                continue
            up = parent_of.get(target.id)
            if up is not None and target in groups[up].subgroups:
                groups[up].subgroups.remove(target)
            parent_of[target.id] = None
            moved.add(target.id)
            node.subgroups.append(target)
        coll_nodes.append(node)

    forest: list[Node] = []
    for gid, root in groups.items():
        if parent_of.get(gid) is not None or gid in moved:
            continue
        node = root
        while not node.person_ids and len(node.subgroups) == 1:
            node = node.subgroups[0]
        forest.append(node)

    for node in forest + coll_nodes:
        _finalize(node, by_id)
    forest = [n for n in forest if n.total_persons > 0]
    forest.sort(key=lambda n: n.name.casefold())
    return coll_nodes + forest  # the user's own collections lead


def _finalize(node: Node, by_id: dict[str, Entry]) -> int:
    node.person_ids.sort(
        key=lambda i: (by_id[i].name is None, -by_id[i].media_count, (by_id[i].name or "").casefold())
    )
    total = len(node.person_ids)
    for g in node.subgroups:
        total += _finalize(g, by_id)
    node.subgroups = [g for g in node.subgroups if g.total_persons > 0]
    node.subgroups.sort(key=lambda g: g.name.casefold())
    node.total_persons = total
    return total


def load_entries(registry: LibraryRegistry) -> tuple[list[Entry], dict[tuple[str, int], str]]:
    """Every person from every reachable, face-scanned library as an entry.
    Returns the entries plus a (library_id, local_person_id) -> entry id map."""
    lib_data = _load_all_lib_face_data(registry)
    libs = {lib.id: lib for lib in registry.list()}
    gp_conn = gp_store.open_global_db()
    try:
        link_of = {(link.library_id, link.local_person_id): gid for gid, link in gp_store.all_links(gp_conn)}
    finally:
        gp_conn.close()

    grouped: dict[str, list[tuple[str, int]]] = {}
    for lib_id, data in lib_data.items():
        for pid in data.summaries:
            gid = link_of.get((lib_id, pid))
            grouped.setdefault(f"g:{gid}" if gid is not None else f"l:{lib_id}:{pid}", []).append((lib_id, pid))

    entries: list[Entry] = []
    entry_of: dict[tuple[str, int], str] = {}
    for members in grouped.values():
        members.sort()
        summaries = [(lib_id, pid, lib_data[lib_id].summaries[pid]) for lib_id, pid in members]
        lib_id0, _, s0 = summaries[0]
        rel = (s0.primary_folder_path or "").strip("/")
        # ADR-0008: a person's home group is the folder containing their Primary
        # Location; a person with none sits in their library's root folder.
        lib0_path = libs[lib_id0].path
        folder = str(Path(lib0_path, rel).parent) if rel else lib0_path
        keys = [person_key(lib_id, pid) for lib_id, pid, _ in summaries]
        entry = Entry(
            id=keys[0],
            name=next((s.name for _, _, s in summaries if s.name), None),
            auto_label=s0.auto_label,
            face_count=sum(s.face_count for _, _, s in summaries),
            media_count=sum(s.media_count for _, _, s in summaries),
            members=[
                MemberRef(lib_id, libs[lib_id].name, pid, list(s.sample_face_ids))
                for lib_id, pid, s in summaries
            ],
            keys=keys,
            folder_path=folder,
        )
        entries.append(entry)
        for lib_id, pid, _ in summaries:
            entry_of[(lib_id, pid)] = entry.id
    return entries, entry_of


def load_overview(registry: LibraryRegistry, layout: PeopleLayoutStore):
    entries, entry_of = load_entries(registry)
    by_id = {e.id: e for e in entries}

    gp_conn = gp_store.open_global_db()
    try:
        suggestions = list_link_suggestions(gp_conn, registry)
    finally:
        gp_conn.close()
    for s in suggestions:
        a = entry_of.get((s["library_id_a"], s["local_person_id_a"]))
        b = entry_of.get((s["library_id_b"], s["local_person_id_b"]))
        if a and b and a != b:
            by_id[a].duplicates.append((b, s["similarity"]))
            by_id[b].duplicates.append((a, s["similarity"]))

    pin_list = layout.pins()
    pin_set = set(pin_list)
    for e in entries:
        e.pinned = bool(pin_set.intersection(e.keys))
    collections = layout.collections()
    forest = build_forest(entries, collections, pin_set)
    return entries, forest, collections, pin_list
