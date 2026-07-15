"""Tests for the Phase B folder-binding detection engine."""

from __future__ import annotations

from pathlib import Path

from mediamind.core.faces.folder_patterns import (
    FolderFileInfo,
    detect_bindings,
    detect_bindings_for_library,
    group_by_folder,
)
from mediamind.store.db import library_db_path, open_db


def _f(file_id: int, path: str, *person_ids: int) -> FolderFileInfo:
    return FolderFileInfo(file_id=file_id, path=path, person_ids=frozenset(person_ids))


# ---------------------------------------------------------------------------
# group_by_folder
# ---------------------------------------------------------------------------

def test_group_by_folder_is_non_recursive():
    files = [
        _f(1, "Laura/a.jpg", 1),
        _f(2, "Laura/sub/b.jpg", 1),
    ]
    grouped = group_by_folder(files)
    assert grouped["Laura"] == [files[0]]
    assert grouped["Laura/sub"] == [files[1]]


# ---------------------------------------------------------------------------
# Person-folder detection
# ---------------------------------------------------------------------------

def test_person_folder_detected_above_coverage_threshold():
    # 5 files, person 1 in all 5 -> coverage 1.0, well above 0.75.
    files = [_f(i, f"Laura/img{i}.jpg", 1) for i in range(5)]
    suggestions = detect_bindings({"Laura": files})
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.folder_rel == "Laura"
    assert s.kind == "person"
    assert s.person_ids == (1,)
    assert s.file_count == 5
    assert s.coverage == 1.0
    assert s.outlier_file_ids == ()


def test_person_folder_below_coverage_threshold_not_suggested():
    # person 1 in only 3 of 5 files -> coverage 0.6, below 0.75.
    files = [_f(i, f"Mixed/img{i}.jpg", 1) for i in range(3)]
    files += [_f(i, f"Mixed/img{i}.jpg", 99) for i in range(3, 5)]
    suggestions = detect_bindings({"Mixed": files})
    assert suggestions == []


def test_folder_below_min_face_files_ignored():
    # Only 4 files-with-faces (< MIN_FACE_FILES=5), even at 100% coverage.
    files = [_f(i, f"Small/img{i}.jpg", 1) for i in range(4)]
    suggestions = detect_bindings({"Small": files})
    assert suggestions == []


def test_person_folder_lenient_outliers():
    # 5 files: 4 with person 1, 1 with only person 2 (no overlap).
    # coverage for person 1 = 4/5 = 0.8 >= 0.75 -> person-folder, 1 outlier.
    files = [_f(i, f"Laura/img{i}.jpg", 1) for i in range(4)]
    files.append(_f(4, "Laura/img4.jpg", 2))
    suggestions = detect_bindings({"Laura": files})
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.kind == "person"
    assert s.person_ids == (1,)
    assert s.outlier_file_ids == (4,)


# ---------------------------------------------------------------------------
# Group-folder detection
# ---------------------------------------------------------------------------

def test_group_folder_detected():
    # 5 files: person 1 in all 5, person 2 in 3 of 5.
    # top coverage = 1.0 -> this alone would be a *person* folder for person 1,
    # so use a case where no single person crosses PERSON_MIN_COVERAGE but the
    # union of two members does.
    files = [
        _f(0, "Trip/img0.jpg", 1, 2),
        _f(1, "Trip/img1.jpg", 1, 2),
        _f(2, "Trip/img2.jpg", 1),
        _f(3, "Trip/img3.jpg", 2),
        _f(4, "Trip/img4.jpg", 1),
    ]
    # person 1: 4/5 = 0.8 -> that alone clears PERSON_MIN_COVERAGE (0.75),
    # so this becomes a person-folder for 1, not a group. Confirm that.
    suggestions = detect_bindings({"Trip": files})
    assert len(suggestions) == 1
    assert suggestions[0].kind == "person"
    assert suggestions[0].person_ids == (1,)


def test_group_folder_detected_when_no_single_dominant_person():
    # 5 files: person 1 in 3/5 (0.6), person 2 in 3/5 (0.6) — neither alone
    # clears 0.75, but the union covers 5/5 = 1.0 >= 0.8.
    files = [
        _f(0, "Duo/img0.jpg", 1),
        _f(1, "Duo/img1.jpg", 1),
        _f(2, "Duo/img2.jpg", 1, 2),
        _f(3, "Duo/img3.jpg", 2),
        _f(4, "Duo/img4.jpg", 2),
    ]
    suggestions = detect_bindings({"Duo": files})
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.kind == "group"
    assert set(s.person_ids) == {1, 2}
    assert s.coverage == 1.0
    assert s.outlier_file_ids == ()


def test_group_folder_below_union_coverage_not_suggested():
    # 7 files: person 1 and 2 fully overlap in the first 4 (coverage 4/7=0.57,
    # clears the 0.5 member bar); person 99 only in 3/7=0.43, below the member
    # bar so it's excluded. Union of {1,2} = 4/7 = 0.57, below 0.8 -> no group.
    files = [_f(i, f"Weak/img{i}.jpg", 1, 2) for i in range(4)]
    files += [_f(i, f"Weak/img{i}.jpg", 99) for i in range(4, 7)]
    suggestions = detect_bindings({"Weak": files})
    assert suggestions == []


def test_group_folder_lenient_outliers():
    # 6 files: person1 in 0-2, person2 in 2-4 (overlap at 2), file5 is an
    # unrelated outlier. Union = {0,1,2,3,4} = 5/6 = 0.833 >= 0.8.
    files = [
        _f(0, "Group/img0.jpg", 1),
        _f(1, "Group/img1.jpg", 1),
        _f(2, "Group/img2.jpg", 1, 2),
        _f(3, "Group/img3.jpg", 2),
        _f(4, "Group/img4.jpg", 2),
        _f(5, "Group/img5.jpg", 99),
    ]
    suggestions = detect_bindings({"Group": files})
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.kind == "group"
    assert set(s.person_ids) == {1, 2}
    assert s.outlier_file_ids == (5,)


def test_exclude_prefixes_skips_managed_folders():
    files = [_f(i, f"People/Laura/img{i}.jpg", 1) for i in range(5)]
    suggestions = detect_bindings({"People/Laura": files}, exclude_prefixes=("People",))
    assert suggestions == []


def test_library_root_never_suggested():
    files = [_f(i, f"img{i}.jpg", 1) for i in range(5)]
    suggestions = detect_bindings({".": files})
    assert suggestions == []


# ---------------------------------------------------------------------------
# DB-facing wrapper
# ---------------------------------------------------------------------------

def test_detect_bindings_for_library_from_db(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    provider_id = "test-provider"

    conn.execute(
        "INSERT INTO persons (auto_label, name, provider_id) VALUES ('Person_001', NULL, ?)",
        (provider_id,),
    )
    person_id = conn.execute("SELECT id FROM persons").fetchone()["id"]

    for i in range(5):
        conn.execute(
            "INSERT INTO files (path, kind, size, mtime, content_hash, decoded_ok) "
            "VALUES (?, 'image', 100, 0, ?, 1)",
            (f"Laura/img{i}.jpg", f"hash{i}"),
        )
        file_id = conn.execute("SELECT id FROM files WHERE path = ?", (f"Laura/img{i}.jpg",)).fetchone()["id"]
        conn.execute(
            "INSERT INTO faces (file_id, provider_id, embedding, person_id, confidence) "
            "VALUES (?, ?, X'00', ?, 1.0)",
            (file_id, provider_id, person_id),
        )
    conn.commit()

    suggestions = detect_bindings_for_library(conn, provider_id)
    assert len(suggestions) == 1
    assert suggestions[0].folder_rel == "Laura"
    assert suggestions[0].kind == "person"
    assert suggestions[0].person_ids == (person_id,)
