"""ADR-0007/0008 people-tree derivation — pure, no DB."""

from mediamind.store.people_tree import build_people_tree
from mediamind.store.persons import PersonSummary


def _p(id, name, folder):
    return PersonSummary(
        id=id,
        auto_label=f"person_{id}",
        name=name,
        face_count=1,
        media_count=1,
        sample_face_ids=[id],
        primary_folder_path=folder,
    )


def _find(node, path):
    if node.path == path:
        return node
    for g in node.subgroups:
        hit = _find(g, path)
        if hit:
            return hit
    return None


def test_home_group_is_parent_of_primary_location():
    root = build_people_tree([_p(1, "Nayeon", "pop/kpop/twice/nayeon")])
    twice = _find(root, "pop/kpop/twice")
    assert twice is not None
    assert [p.name for p in twice.persons] == ["Nayeon"]
    # ancestor groups exist but hold no persons directly
    assert _find(root, "pop/kpop").persons == []
    assert _find(root, "pop").persons == []


def test_top_level_person_homes_at_root():
    root = build_people_tree([_p(1, "Mom", "Mom")])
    assert [p.name for p in root.persons] == ["Mom"]
    assert root.subgroups == []


def test_unnamed_persons_included():
    root = build_people_tree([_p(1, None, "pop/kpop/twice/x")])
    assert root.total_persons == 1
    twice = _find(root, "pop/kpop/twice")
    assert twice is not None
    assert twice.persons[0].name is None


def test_unnamed_person_with_no_primary_folder_homes_at_root():
    root = build_people_tree([_p(1, None, None)])
    assert root.total_persons == 1
    assert root.persons[0].name is None
    assert root.subgroups == []


def test_no_primary_folder_homes_at_root():
    root = build_people_tree([_p(1, "Solo", None)])
    assert [p.name for p in root.persons] == ["Solo"]


def test_transitive_counts_and_sorting():
    root = build_people_tree([
        _p(1, "Sana", "pop/kpop/twice/sana"),
        _p(2, "Nayeon", "pop/kpop/twice/nayeon"),
        _p(3, "Rose", "pop/kpop/blackpink/rose"),
        _p(4, "Adele", "pop/adele"),
    ])
    assert root.total_persons == 4
    pop = _find(root, "pop")
    assert pop.total_persons == 4
    assert _find(root, "pop/kpop").total_persons == 3
    # persons sorted by name within their home group
    assert [p.name for p in _find(root, "pop/kpop/twice").persons] == ["Nayeon", "Sana"]
    # subgroups sorted by name (blackpink before twice)
    assert [g.name for g in _find(root, "pop/kpop").subgroups] == ["blackpink", "twice"]
    # a person homed directly in a group with subgroups (adele in pop)
    assert [p.name for p in pop.persons] == ["Adele"]
