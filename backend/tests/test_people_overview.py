"""People view V2: absolute-path grouping across libraries, collections overlay,
pins/collections store. Pure — no DB, no real filesystem."""

from __future__ import annotations

from pathlib import Path

from mediamind.core.people_overview import Entry, MemberRef, build_forest
from mediamind.store.people_layout import PeopleLayoutStore, folder_key, person_key

ROOT = Path("C:/media") if Path("C:/").exists() else Path("/media")


def _entry(lib: str, pid: int, folder: Path, name: str | None = None, media: int = 1) -> Entry:
    key = person_key(lib, pid)
    return Entry(
        id=key,
        name=name,
        auto_label=f"Person {pid}",
        face_count=media,
        media_count=media,
        members=[MemberRef(lib, lib, pid, [])],
        keys=[key],
        folder_path=str(folder),
    )


def _names(nodes):
    return [n.name for n in nodes]


def test_separately_scanned_siblings_share_their_parent_group():
    entries = [
        _entry("A", 1, ROOT / "kpop" / "twice", "Nayeon"),
        _entry("B", 1, ROOT / "kpop" / "ive", "Wonyoung"),
        _entry("C", 1, ROOT / "kpop" / "blackpink", "Jisoo"),
    ]
    forest = build_forest(entries, [], set())
    assert _names(forest) == ["kpop"]
    assert _names(forest[0].subgroups) == ["blackpink", "ive", "twice"]
    assert forest[0].total_persons == 3


def test_single_scanned_folder_is_not_buried_under_ancestors():
    forest = build_forest([_entry("A", 1, ROOT / "kpop" / "twice", "Nayeon")], [], set())
    assert _names(forest) == ["twice"]
    assert forest[0].person_ids == [person_key("A", 1)]


def test_persons_sort_named_first_then_by_media_count():
    entries = [
        _entry("A", 1, ROOT / "x", None, media=50),
        _entry("A", 2, ROOT / "x", "Zed", media=2),
        _entry("A", 3, ROOT / "x", "Amy", media=9),
    ]
    forest = build_forest(entries, [], set())
    assert forest[0].person_ids == [person_key("A", 3), person_key("A", 2), person_key("A", 1)]


def test_collection_takes_a_person_out_of_their_folder_group():
    entries = [
        _entry("A", 1, ROOT / "kpop" / "twice", "Nayeon"),
        _entry("A", 2, ROOT / "kpop" / "twice", "Jihyo"),
    ]
    coll = [{"id": "c1", "name": "Favourites", "members": [person_key("A", 1)]}]
    forest = build_forest(entries, coll, set())
    assert _names(forest) == ["Favourites", "twice"]
    assert forest[0].kind == "collection" and forest[0].person_ids == [person_key("A", 1)]
    assert forest[1].person_ids == [person_key("A", 2)]
    assert entries[0].collection_id == "c1"


def test_collection_matches_a_linked_identity_by_any_of_its_keys():
    e = _entry("A", 1, ROOT / "x", "Nayeon")
    e.keys.append(person_key("B", 7))
    coll = [{"id": "c1", "name": "Fav", "members": [person_key("B", 7)]}]
    forest = build_forest([e], coll, set())
    assert forest[0].kind == "collection" and forest[0].person_ids == [e.id]


def test_folder_can_be_moved_into_a_collection():
    entries = [_entry("A", 1, ROOT / "kpop" / "twice", "A"), _entry("B", 1, ROOT / "kpop" / "ive", "B")]
    coll = [{"id": "c1", "name": "Girl groups", "members": [folder_key(str(ROOT / "kpop" / "ive"))]}]
    forest = build_forest(entries, coll, set())
    assert _names(forest) == ["Girl groups", "twice"]  # kpop collapses once ive left it
    assert _names(forest[0].subgroups) == ["ive"]


def test_emptied_group_is_pruned():
    entries = [_entry("A", 1, ROOT / "kpop" / "twice", "A")]
    coll = [{"id": "c1", "name": "All", "members": [person_key("A", 1)]}]
    forest = build_forest(entries, coll, set())
    assert _names(forest) == ["All"]


def test_pinned_folder_and_collection_are_flagged():
    entries = [_entry("A", 1, ROOT / "kpop" / "twice", "A"), _entry("B", 1, ROOT / "kpop" / "ive", "B")]
    coll = [{"id": "c1", "name": "Fav", "members": []}]
    pins = {folder_key(str(ROOT / "kpop" / "twice")), "c:c1"}
    forest = build_forest(entries, coll, pins)
    kpop = next(n for n in forest if n.name == "kpop")
    assert {g.name: g.pinned for g in kpop.subgroups} == {"ive": False, "twice": True}
    assert next(n for n in forest if n.kind == "collection").pinned is True


def test_layout_store_round_trip_and_move_semantics(tmp_path):
    path = tmp_path / "layout.json"
    s = PeopleLayoutStore(path)
    c1 = s.create_collection("One")
    c2 = s.create_collection("Two")
    s.add_members(c1["id"], ["p:A:1", "p:A:2"])
    s.add_members(c2["id"], ["p:A:1"])  # a drag moves, never copies
    s.pin("p:A:1")
    s.pin("p:A:1")  # idempotent
    s.pin("c:" + c2["id"])

    again = PeopleLayoutStore(path)
    members = {c["name"]: c["members"] for c in again.collections()}
    assert members == {"One": ["p:A:2"], "Two": ["p:A:1"]}
    assert again.pins() == ["p:A:1", "c:" + c2["id"]]

    again.reorder_pins(["c:" + c2["id"], "p:A:1", "p:ghost"])
    assert again.pins() == ["c:" + c2["id"], "p:A:1"]

    again.delete_collection(c2["id"])
    assert again.pins() == ["p:A:1"]  # its pin goes with it
    assert [c["name"] for c in again.collections()] == ["One"]


def test_layout_store_survives_a_corrupt_file(tmp_path):
    path = tmp_path / "layout.json"
    path.write_text("{not json", encoding="utf-8")
    s = PeopleLayoutStore(path)
    assert s.pins() == [] and s.collections() == []
    s.pin("p:A:1")
    assert PeopleLayoutStore(path).pins() == ["p:A:1"]
