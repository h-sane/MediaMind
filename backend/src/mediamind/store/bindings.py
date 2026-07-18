"""Persist folder-binding suggestions and accepted bindings (Phase B).

Bridges the pure detection engine (`core/faces/folder_patterns.py`) to the
`binding_suggestions` / `folder_bindings` / `folder_binding_members` tables:
run detection and cache results, accept/dismiss a suggestion, list current
state for a provider.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import PurePosixPath

from mediamind.core.faces.folder_patterns import (
    detect_bindings_for_library,
    group_by_folder,
    load_folder_files,
)


class BindingConflictError(Exception):
    """A suggestion can't be accepted because a member person is already bound elsewhere."""


@dataclass(frozen=True)
class SuggestionRecord:
    id: int
    folder_rel: str
    kind: str
    provider_id: str
    file_count: int
    coverage: float
    person_ids: list[int]
    outlier_file_ids: list[int]
    status: str
    created_at: float


@dataclass(frozen=True)
class OutlierFile:
    """One file in a bound folder that doesn't match any bound person.

    `accepted` mirrors whether the file's id is currently in the binding's
    `accepted_outlier_file_ids` — the only files the organize sweep will
    actually route despite the folder being frozen.
    """

    file_id: int
    path: str
    kind: str
    accepted: bool


@dataclass(frozen=True)
class BindingRecord:
    id: int
    folder_rel: str
    kind: str
    provider_id: str
    person_ids: list[int]
    accepted_outlier_file_ids: list[int]
    outliers: list[OutlierFile]
    created_at: float


@dataclass(frozen=True)
class SuggestionMovePlan:
    """What a merge would move, computed read-only from a pending suggestion."""

    suggestion_id: int
    folder_rel: str
    person_id: int | None
    leaf_name: str
    moves: list[tuple[int, str, str, str]]  # (file_id, source_rel, dest_folder_rel, kind)


def _suggestion_from_row(row: sqlite3.Row) -> SuggestionRecord:
    return SuggestionRecord(
        id=row["id"],
        folder_rel=row["folder_rel"],
        kind=row["kind"],
        provider_id=row["provider_id"],
        file_count=row["file_count"],
        coverage=row["coverage"],
        person_ids=json.loads(row["person_ids"]),
        outlier_file_ids=json.loads(row["outlier_file_ids"]),
        status=row["status"],
        created_at=row["created_at"],
    )


def _outliers_from_folder_files(
    conn: sqlite3.Connection,
    folder_files: list,
    person_ids: list[int],
    accepted_ids: list[int],
) -> list[OutlierFile]:
    """Resolve the folder's non-matching files to path/kind for display.

    A file already routes normally once its id is in `accepted_ids` — that's
    reflected per-file as `accepted` rather than dropped from the list, so
    the UI can still show it (as approved) instead of it just vanishing.
    """
    member_set = set(person_ids)
    accepted_set = set(accepted_ids)
    outlier_ids = [f.file_id for f in folder_files if not (f.person_ids & member_set)]
    if not outlier_ids:
        return []
    placeholders = ",".join("?" * len(outlier_ids))
    rows = conn.execute(
        f"SELECT id, path, kind FROM files WHERE id IN ({placeholders})", outlier_ids
    ).fetchall()
    by_id = {r["id"]: r for r in rows}
    return sorted(
        (
            OutlierFile(file_id=fid, path=by_id[fid]["path"], kind=by_id[fid]["kind"], accepted=fid in accepted_set)
            for fid in outlier_ids
            if fid in by_id
        ),
        key=lambda o: o.path,
    )


def _binding_from_row(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    folder_files_by_folder: dict[str, list] | None = None,
) -> BindingRecord:
    members = conn.execute(
        "SELECT person_id FROM folder_binding_members WHERE binding_id = ? ORDER BY person_id",
        (row["id"],),
    ).fetchall()
    person_ids = [m["person_id"] for m in members]
    accepted_ids = json.loads(row["accepted_outlier_file_ids"])

    if folder_files_by_folder is not None:
        folder_files = folder_files_by_folder.get(row["folder_rel"], [])
    else:
        folder_files = group_by_folder(load_folder_files(conn, row["provider_id"])).get(row["folder_rel"], [])
    outliers = _outliers_from_folder_files(conn, folder_files, person_ids, accepted_ids)

    return BindingRecord(
        id=row["id"],
        folder_rel=row["folder_rel"],
        kind=row["kind"],
        provider_id=row["provider_id"],
        person_ids=person_ids,
        accepted_outlier_file_ids=accepted_ids,
        outliers=outliers,
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# Detection + suggestion cache
# ---------------------------------------------------------------------------

def refresh_suggestions(
    conn: sqlite3.Connection,
    provider_id: str,
    *,
    target_rel: str = "People",
) -> dict:
    """Run detection for `provider_id` and upsert results into `binding_suggestions`.

    Folders that already have an accepted binding are never re-suggested.
    Existing 'accepted'/'dismissed' suggestion rows are left untouched (a
    dismissed suggestion doesn't reappear just because detection reran);
    only 'pending' rows are refreshed or removed if their folder no longer
    qualifies.
    """
    detected = detect_bindings_for_library(conn, provider_id, exclude_prefixes=(target_rel,))
    now = time.time()

    bound_folders = {
        r["folder_rel"]
        for r in conn.execute(
            "SELECT folder_rel FROM folder_bindings WHERE provider_id = ?", (provider_id,)
        )
    }

    detected_folders: set[str] = set()
    for s in detected:
        if s.folder_rel in bound_folders:
            continue  # already accepted; nothing to suggest
        detected_folders.add(s.folder_rel)
        conn.execute(
            """
            INSERT INTO binding_suggestions
              (folder_rel, kind, provider_id, file_count, coverage,
               person_ids, outlier_file_ids, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            ON CONFLICT(folder_rel, provider_id) DO UPDATE SET
                kind=excluded.kind, file_count=excluded.file_count,
                coverage=excluded.coverage, person_ids=excluded.person_ids,
                outlier_file_ids=excluded.outlier_file_ids, created_at=excluded.created_at
            WHERE binding_suggestions.status = 'pending'
            """,
            (
                s.folder_rel, s.kind, provider_id, s.file_count, s.coverage,
                json.dumps(list(s.person_ids)), json.dumps(list(s.outlier_file_ids)), now,
            ),
        )

    stale = conn.execute(
        "SELECT id, folder_rel FROM binding_suggestions WHERE provider_id = ? AND status = 'pending'",
        (provider_id,),
    ).fetchall()
    removed = 0
    for row in stale:
        if row["folder_rel"] not in detected_folders:
            conn.execute("DELETE FROM binding_suggestions WHERE id = ?", (row["id"],))
            removed += 1

    conn.commit()
    return {"suggested": len(detected_folders), "removed_stale": removed}


def list_suggestions(
    conn: sqlite3.Connection, provider_id: str, *, status: str = "pending"
) -> list[SuggestionRecord]:
    rows = conn.execute(
        "SELECT * FROM binding_suggestions WHERE provider_id = ? AND status = ? ORDER BY folder_rel",
        (provider_id, status),
    ).fetchall()
    return [_suggestion_from_row(r) for r in rows]


def build_suggestion_merge_moves(
    conn: sqlite3.Connection,
    suggestion_id: int,
    *,
    extra_reassignments: dict[int, str] | None = None,
) -> SuggestionMovePlan:
    """Read-only: compute the file moves a merge-into-folder would perform.

    `coverage` on a suggestion only measures the folder->person direction
    (what fraction of the folder matches the person). This computes the
    reverse: for a lone-person suggestion, this person's other photos
    elsewhere in the library that a merge would bring into `folder_rel`,
    using the same face data `folder_patterns.load_folder_files` already
    loads for detection so the two stay consistent. Group suggestions have
    no single owning person, so they plan no reverse moves.

    `extra_reassignments` (file_id -> dest_folder_rel) layers in ad hoc
    corrections from the review modal — e.g. sending a misclassified folder
    outlier to a different folder entirely — on top of the computed set.
    """
    row = conn.execute(
        "SELECT * FROM binding_suggestions WHERE id = ?", (suggestion_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Suggestion {suggestion_id} not found")
    if row["status"] != "pending":
        raise ValueError(f"Suggestion {suggestion_id} is already {row['status']}")

    folder_rel = row["folder_rel"]
    person_ids = json.loads(row["person_ids"])
    leaf_name = PurePosixPath(folder_rel).name

    moves: dict[int, tuple[str, str]] = {}  # file_id -> (source_rel, dest_folder_rel)
    person_id: int | None = None
    if row["kind"] == "person" and len(person_ids) == 1:
        person_id = person_ids[0]
        for f in load_folder_files(conn, row["provider_id"]):
            if person_id in f.person_ids and PurePosixPath(f.path).parent.as_posix() != folder_rel:
                moves[f.file_id] = (f.path, folder_rel)

    if extra_reassignments:
        placeholders = ",".join("?" * len(extra_reassignments))
        rows = conn.execute(
            f"SELECT id, path FROM files WHERE id IN ({placeholders})",
            list(extra_reassignments.keys()),
        ).fetchall()
        by_id = {r["id"]: r["path"] for r in rows}
        for fid, dest_folder_rel in extra_reassignments.items():
            if fid in by_id:
                moves[fid] = (by_id[fid], dest_folder_rel)

    kind_by_id: dict[int, str] = {}
    if moves:
        placeholders = ",".join("?" * len(moves))
        kind_by_id = {
            r["id"]: r["kind"]
            for r in conn.execute(
                f"SELECT id, kind FROM files WHERE id IN ({placeholders})", list(moves.keys())
            ).fetchall()
        }

    return SuggestionMovePlan(
        suggestion_id=suggestion_id,
        folder_rel=folder_rel,
        person_id=person_id,
        leaf_name=leaf_name,
        moves=[
            (fid, src, dest, kind_by_id.get(fid, "other"))
            for fid, (src, dest) in sorted(moves.items())
        ],
    )


def accept_suggestion(conn: sqlite3.Connection, suggestion_id: int) -> BindingRecord:
    """Accept a pending suggestion: create the binding, bind its members,
    auto-name a lone person from the folder's leaf name.

    Raises BindingConflictError if a member is already bound to another
    folder (structurally shouldn't happen since detection skips bound
    folders, but a person could theoretically appear in two still-pending
    suggestions — first accept wins, the second must be re-detected).
    """
    row = conn.execute(
        "SELECT * FROM binding_suggestions WHERE id = ?", (suggestion_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Suggestion {suggestion_id} not found")
    if row["status"] != "pending":
        raise ValueError(f"Suggestion {suggestion_id} is already {row['status']}")

    person_ids = json.loads(row["person_ids"])
    now = time.time()

    cur = conn.execute(
        "INSERT INTO folder_bindings (folder_rel, kind, provider_id, created_at) VALUES (?, ?, ?, ?)",
        (row["folder_rel"], row["kind"], row["provider_id"], now),
    )
    binding_id = cur.lastrowid

    for pid in person_ids:
        try:
            conn.execute(
                "INSERT INTO folder_binding_members (binding_id, person_id) VALUES (?, ?)",
                (binding_id, pid),
            )
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise BindingConflictError(
                f"Person {pid} is already bound to another folder"
            ) from exc

    if row["kind"] == "person" and len(person_ids) == 1:
        leaf = PurePosixPath(row["folder_rel"]).name
        conn.execute(
            "UPDATE persons SET name = ? WHERE id = ? AND name IS NULL",
            (leaf, person_ids[0]),
        )

    conn.execute(
        "UPDATE binding_suggestions SET status = 'accepted' WHERE id = ?", (suggestion_id,)
    )
    conn.commit()

    binding_row = conn.execute(
        "SELECT * FROM folder_bindings WHERE id = ?", (binding_id,)
    ).fetchone()
    return _binding_from_row(conn, binding_row)


def dismiss_suggestion(conn: sqlite3.Connection, suggestion_id: int) -> bool:
    cur = conn.execute(
        "UPDATE binding_suggestions SET status = 'dismissed' WHERE id = ? AND status = 'pending'",
        (suggestion_id,),
    )
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Accepted bindings
# ---------------------------------------------------------------------------

def list_bindings(conn: sqlite3.Connection, provider_id: str) -> list[BindingRecord]:
    rows = conn.execute(
        "SELECT * FROM folder_bindings WHERE provider_id = ? ORDER BY folder_rel",
        (provider_id,),
    ).fetchall()
    # Load once and share across every binding rather than re-scanning the
    # whole provider's faces per row.
    by_folder = group_by_folder(load_folder_files(conn, provider_id))
    return [_binding_from_row(conn, r, folder_files_by_folder=by_folder) for r in rows]


def release_binding(conn: sqlite3.Connection, binding_id: int) -> bool:
    """Un-freeze a folder: delete the binding (cascades to its members).

    The organize sweep will route the folder's files normally again on the
    next preview/execute. Any suggestion cache entry stays 'accepted' (it's
    historical); a fresh `refresh_suggestions` call will re-suggest the
    folder if it still qualifies.
    """
    cur = conn.execute("DELETE FROM folder_bindings WHERE id = ?", (binding_id,))
    conn.commit()
    return cur.rowcount > 0


def set_accepted_outliers(
    conn: sqlite3.Connection, binding_id: int, file_ids: list[int]
) -> BindingRecord | None:
    """Mark specific outlier files in a bound folder as approved to move.

    These files are excluded from the freeze and route normally in the next
    organize plan, while every other file in the folder stays in place.
    """
    conn.execute(
        "UPDATE folder_bindings SET accepted_outlier_file_ids = ? WHERE id = ?",
        (json.dumps(sorted(set(file_ids))), binding_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM folder_bindings WHERE id = ?", (binding_id,)).fetchone()
    return _binding_from_row(conn, row) if row is not None else None
