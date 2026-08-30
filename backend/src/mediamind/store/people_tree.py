"""Person-centric People-tab projection (ADR-0007, ADR-0008).

The People tab is a projection *by identity*, not a mirror of the filesystem.
Groups form a nested tree that mirrors the user's folder nesting; a named Person
is homed in exactly one Group — the folder that *contains* their Primary
Location (ADR-0008). Files never sit under a Group directly (ADR-0007): to reach
media you drill to a Person, which the existing person-media endpoint serves.

This module is a pure derivation over `PersonSummary` rows — no schema, no DB.
Unnamed persons never appear here (ADR-0007: they belong to the recurring-unnamed
surface); named persons with no Primary Location are homed at the root Group.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .persons import PersonSummary


@dataclass
class PersonNode:
    id: int
    auto_label: str
    name: str | None
    face_count: int
    media_count: int
    sample_face_ids: list[int]
    primary_folder_path: str | None


@dataclass
class GroupNode:
    path: str  # posix, library-relative; "" is the root
    name: str  # leaf segment; "" for the root
    subgroups: list["GroupNode"] = field(default_factory=list)
    persons: list[PersonNode] = field(default_factory=list)
    total_persons: int = 0  # transitive: this group's persons + all descendants'


def _home_group_path(primary_folder_path: str | None) -> str:
    """The folder that *contains* a person's Primary Location (ADR-0008).

    `a/b/twice/nayeon` -> `a/b/twice`; a top-level `mom` -> "" (root)."""
    pf = (primary_folder_path or "").strip("/")
    return pf.rpartition("/")[0] if "/" in pf else ""


def build_people_tree(persons: list[PersonSummary]) -> GroupNode:
    """Derive the nested Group -> Person tree from persons' Primary Locations."""
    root = GroupNode(path="", name="")
    nodes: dict[str, GroupNode] = {"": root}

    def ensure(path: str) -> GroupNode:
        node = nodes.get(path)
        if node is not None:
            return node
        parent_path, _, leaf = path.rpartition("/")
        parent = ensure(parent_path)
        node = GroupNode(path=path, name=leaf)
        parent.subgroups.append(node)
        nodes[path] = node
        return node

    for p in persons:
        if not p.name:  # unnamed -> recurring-unnamed surface, not the tree
            continue
        home = ensure(_home_group_path(p.primary_folder_path))
        home.persons.append(
            PersonNode(
                id=p.id,
                auto_label=p.auto_label,
                name=p.name,
                face_count=p.face_count,
                media_count=p.media_count,
                sample_face_ids=list(p.sample_face_ids),
                primary_folder_path=p.primary_folder_path,
            )
        )

    _finalize(root)
    return root


def _finalize(node: GroupNode) -> int:
    """Sort children and persons by name and compute transitive person counts."""
    node.subgroups.sort(key=lambda g: g.name.casefold())
    node.persons.sort(key=lambda p: (p.name or "").casefold())
    total = len(node.persons)
    for g in node.subgroups:
        total += _finalize(g)
    node.total_persons = total
    return total
