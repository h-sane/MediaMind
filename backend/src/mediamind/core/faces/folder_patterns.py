"""Detect pre-existing person/group folder organization (Phase B).

Users often already sort media into folders per person (or per group of
people) before ever opening MediaMind. This module looks at the faces already
recorded for a scan and asks, per folder, "does this folder's contents already
represent one person, or a fixed group of people?" — so the organize step can
respect that structure instead of bulldozing it into a fresh People/ tree.

Detection is **non-recursive**: each folder is judged only by the files
directly inside it (not its subfolders), so a person-folder containing dated
subfolders isn't mistaken for a group-folder of the union of everyone in it.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath

# Thresholds locked in the Phase B plan (see project memory
# project_facial_recognition_v2_plan.md) — do not retune without re-reading it.
MIN_FACE_FILES = 5           # folder needs at least this many files-with-faces to be judged
PERSON_MIN_COVERAGE = 0.75   # dominant person must appear in >= this fraction of the folder's files
GROUP_MEMBER_MIN_COVERAGE = 0.5   # each group member must appear in >= this fraction
GROUP_UNION_MIN_COVERAGE = 0.8    # the group's combined coverage must reach this fraction
MAX_GROUP_SIZE = 8


@dataclass(frozen=True)
class FolderFileInfo:
    """One file-with-faces, as seen by the detection engine."""

    file_id: int
    path: str                       # relative to library root (posix)
    person_ids: frozenset[int]      # non-noise persons detected in this file


@dataclass(frozen=True)
class BindingSuggestion:
    folder_rel: str                 # folder path relative to library root (posix)
    kind: str                       # 'person' | 'group'
    person_ids: tuple[int, ...]     # single id for 'person', ranked members for 'group'
    file_count: int                 # files-with-faces directly in this folder
    coverage: float                 # dominant coverage ('person') or union coverage ('group')
    outlier_file_ids: tuple[int, ...]  # files matching none of person_ids (lenient outlier rule)


def group_by_folder(files: list[FolderFileInfo]) -> dict[str, list[FolderFileInfo]]:
    """Group files by their immediate parent folder (posix-relative path)."""
    by_folder: dict[str, list[FolderFileInfo]] = defaultdict(list)
    for f in files:
        parent = PurePosixPath(f.path).parent.as_posix()
        by_folder[parent].append(f)
    return dict(by_folder)


def detect_bindings(
    files_by_folder: dict[str, list[FolderFileInfo]],
    *,
    exclude_prefixes: tuple[str, ...] = ("People",),
) -> list[BindingSuggestion]:
    """Pure detection core: given files already grouped by folder, return
    person-folder and group-folder suggestions.

    `exclude_prefixes` skips folders MediaMind itself manages (the organize
    destination tree) so a prior organize run's own People/<Name>/ folders
    are never re-suggested as "pre-existing" organization.
    """
    suggestions: list[BindingSuggestion] = []

    for folder_rel, files in files_by_folder.items():
        if folder_rel == "." or folder_rel == "":
            continue  # library root itself is never a binding target
        if any(folder_rel == p or folder_rel.startswith(p + "/") for p in exclude_prefixes):
            continue
        if len(files) < MIN_FACE_FILES:
            continue

        total = len(files)
        person_counts: dict[int, int] = defaultdict(int)
        for f in files:
            for pid in f.person_ids:
                person_counts[pid] += 1
        if not person_counts:
            continue

        ranked = sorted(person_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        top_pid, top_count = ranked[0]
        top_coverage = top_count / total

        if top_coverage >= PERSON_MIN_COVERAGE:
            outliers = tuple(f.file_id for f in files if top_pid not in f.person_ids)
            suggestions.append(BindingSuggestion(
                folder_rel=folder_rel, kind="person", person_ids=(top_pid,),
                file_count=total, coverage=top_coverage, outlier_file_ids=outliers,
            ))
            continue

        members = [pid for pid, count in ranked if count / total >= GROUP_MEMBER_MIN_COVERAGE]
        members = members[:MAX_GROUP_SIZE]
        if len(members) < 2:
            continue

        member_set = set(members)
        union_count = sum(1 for f in files if f.person_ids & member_set)
        union_coverage = union_count / total
        if union_coverage >= GROUP_UNION_MIN_COVERAGE:
            outliers = tuple(f.file_id for f in files if not (f.person_ids & member_set))
            suggestions.append(BindingSuggestion(
                folder_rel=folder_rel, kind="group", person_ids=tuple(members),
                file_count=total, coverage=union_coverage, outlier_file_ids=outliers,
            ))

    return sorted(suggestions, key=lambda s: s.folder_rel)


def load_folder_files(conn: sqlite3.Connection, provider_id: str) -> list[FolderFileInfo]:
    """Load one FolderFileInfo per file that has at least one face record
    (person_id may be NULL for noise, which contributes no person to the set)."""
    rows = conn.execute(
        """
        SELECT fi.id AS file_id, fi.path AS path, f.person_id AS person_id
        FROM files fi
        JOIN faces f ON f.file_id = fi.id
        WHERE f.provider_id = ?
        """,
        (provider_id,),
    ).fetchall()

    by_file: dict[int, dict] = {}
    for row in rows:
        fid = int(row["file_id"])
        entry = by_file.setdefault(fid, {"path": row["path"], "person_ids": set()})
        if row["person_id"] is not None:
            entry["person_ids"].add(int(row["person_id"]))

    return [
        FolderFileInfo(file_id=fid, path=e["path"], person_ids=frozenset(e["person_ids"]))
        for fid, e in by_file.items()
    ]


def detect_bindings_for_library(
    conn: sqlite3.Connection,
    provider_id: str,
    *,
    exclude_prefixes: tuple[str, ...] = ("People",),
) -> list[BindingSuggestion]:
    """DB-facing entry point: load this provider's faces, group by folder,
    and run detection. Read-only — does not touch binding_suggestions."""
    files = load_folder_files(conn, provider_id)
    by_folder = group_by_folder(files)
    return detect_bindings(by_folder, exclude_prefixes=exclude_prefixes)
