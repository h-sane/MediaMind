"""Build an organize plan: for each scanned file with faces, determine destination.

The plan answers "where should this file go?" without touching anything on disk.
`build_organize_plan` returns a list of `PlannedMove` dataclasses that can be
converted directly to `safety.FileOp` objects for execution.

Routing rules:
  - File with exactly one assigned, NAMED person → People/<PersonName>/
  - File with multiple persons, dominant one named → that person's folder
                                                       (or route_choices override)
  - File that failed to decode                    → People/_unsorted/
  - Everything else (unnamed person, all-noise faces, an undecided
    pending-match review) stays in place — it is never silently moved into a
    developer-facing holding folder. "Everything routes somewhere" now means
    "every file has a deliberate destination or deliberately stays put", not
    "every file physically moves".

Files with zero face records are NOT included in the plan; they stay in place.

Phase B exception: a file whose current folder is inside an accepted
folder-binding's subtree (`folder_bindings` — pre-existing person/group
organization the user chose to respect, including its subfolders) is excluded
from the plan entirely and left in place, unless its file id is in that
binding's `accepted_outlier_file_ids` (the user explicitly approved moving it
despite the folder being frozen).
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class PlannedMove:
    source_rel: str          # relative to library_root (posix)
    dest_folder_rel: str     # destination folder relative to library_root (posix)
    person_id: int | None
    person_name: str | None  # display name shown to the user


def safe_folder_name(name: str) -> str:
    """Sanitize a person/label name so it's safe as a directory component."""
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name)
    name = re.sub(r'\s+', ' ', name)
    name = name.strip('. ')
    return name[:100] or '_unnamed'


def is_in_folder_subtree(file_rel: str, folder_rel: str) -> bool:
    """True if file_rel lives directly in folder_rel or in any subfolder of it.

    Used everywhere a "does this file belong to this bound folder" check
    happens, so a bound folder's own subfolders (dated albums, event
    subfolders) are respected too, not just files sitting at its top level.
    """
    return PurePosixPath(file_rel).is_relative_to(PurePosixPath(folder_rel))


def safe_dest_folder_rel(dest: str, library_root: Path) -> str:
    """Validate and sanitize a user-supplied destination folder path.

    Rejects absolute paths (POSIX or Windows-drive-letter) and `..` segments,
    sanitizes each path segment with `safe_folder_name`, and asserts the
    resolved path stays under `library_root`. Raises ValueError on anything
    that doesn't hold — callers should turn that into a 422/400 response.
    """
    raw = (dest or "").strip()
    if not raw:
        raise ValueError("Destination path is empty")
    if raw.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", raw):
        raise ValueError(f"Destination path must be relative to the library: {dest!r}")

    parts = [p for p in raw.replace("\\", "/").split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError(f"Destination path may not contain '..': {dest!r}")
    safe_parts = [safe_folder_name(p) for p in parts]
    if not safe_parts:
        raise ValueError("Destination path is empty")

    dest_rel = "/".join(safe_parts)
    root_resolved = library_root.resolve()
    resolved = (library_root / dest_rel).resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"Destination path escapes the library: {dest!r}")
    return dest_rel


def build_organize_plan(
    conn: sqlite3.Connection,
    provider_id: str,
    target_rel: str = "People",
) -> list[PlannedMove]:
    """Return one PlannedMove per file that has at least one face for this provider.

    Only files present in the `faces` table are included. Files with no face
    records (never scanned for faces, or scanned with zero detections) are left
    in place and do not appear in the plan.
    """
    # Person display names: id -> name. Unnamed (auto_label-only) persons are
    # deliberately excluded — organize only ever moves files for people the
    # user has actually named, so a first scan never bulldozes strangers and
    # one-off faces into a wall of People/Person_004…_031 folders.
    person_display: dict[int, str] = {}
    for p in conn.execute(
        "SELECT id, name FROM persons WHERE provider_id = ? AND name IS NOT NULL",
        (provider_id,),
    ):
        person_display[int(p["id"])] = p["name"]

    # Files with an undecided pending-match review (a new photo matched to a
    # named person, awaiting the user's confirm/reject) must never be routed
    # anywhere until that review happens — see store/persons.py's pending
    # logic. Excluded wholesale rather than per-face so a partially-decided
    # file still waits for the rest of its faces to be reviewed too.
    pending_file_ids: set[int] = set()
    for r in conn.execute(
        """
        SELECT DISTINCT fa.file_id
        FROM pending_matches pm
        JOIN faces fa ON fa.id = pm.face_id
        WHERE pm.decision IS NULL AND fa.provider_id = ?
        """,
        (provider_id,),
    ):
        pending_file_ids.add(int(r["file_id"]))

    # User-assigned route overrides (multi-person review)
    route_choices: dict[int, int] = {}  # file_id -> person_id
    for rc in conn.execute("SELECT file_id, person_id FROM route_choices"):
        route_choices[int(rc["file_id"])] = int(rc["person_id"])

    # Accepted folder bindings (Phase B): folder_rel -> set of file ids explicitly
    # approved to move despite the folder being frozen. Any other file inside
    # one of these folders' subtrees is excluded from the plan below.
    frozen_folders: dict[str, set[int]] = {}
    for b in conn.execute(
        "SELECT folder_rel, accepted_outlier_file_ids FROM folder_bindings WHERE provider_id = ?",
        (provider_id,),
    ):
        frozen_folders[b["folder_rel"]] = set(json.loads(b["accepted_outlier_file_ids"] or "[]"))

    # Reverse of frozen_folders: person_id -> their bound folder_rel, so a
    # bound person's stray photos found elsewhere route home instead of into
    # a fresh People/<name> (the routing gap this lookup exists to close).
    bound_folder_by_person: dict[int, str] = {}
    for r in conn.execute(
        """
        SELECT m.person_id AS pid, b.folder_rel AS folder_rel
        FROM folder_binding_members m JOIN folder_bindings b ON b.id = m.binding_id
        WHERE b.provider_id = ?
        """,
        (provider_id,),
    ):
        bound_folder_by_person[int(r["pid"])] = r["folder_rel"]

    # content_hash -> set of person_ids the user explicitly rejected for that
    # file (folder-match merge / materialize review's "not this person").
    # Keyed by content_hash, not faces.id/files.id, so it survives the
    # faces-row rebuild every rescan does.
    rejected_by_hash: dict[str, set[int]] = {}
    for r in conn.execute(
        "SELECT content_hash, person_id FROM rejected_person_files WHERE provider_id = ?",
        (provider_id,),
    ):
        rejected_by_hash.setdefault(r["content_hash"], set()).add(int(r["person_id"]))

    # Aggregate face data per file
    file_data: dict[int, dict] = {}
    for row in conn.execute(
        """
        SELECT fi.id, fi.path, fi.content_hash, fi.decoded_ok, f.person_id
        FROM files fi
        JOIN faces f ON f.file_id = fi.id
        WHERE f.provider_id = ?
        """,
        (provider_id,),
    ):
        fid = int(row["id"])
        if fid not in file_data:
            file_data[fid] = {
                "path": row["path"],
                "content_hash": row["content_hash"],
                "decoded_ok": bool(row["decoded_ok"]),
                "person_ids": set(),
            }
        if row["person_id"] is not None:
            file_data[fid]["person_ids"].add(int(row["person_id"]))

    def _frozen_accepted_outliers(source_rel: str) -> set[int] | None:
        """None if source_rel isn't inside any bound folder's subtree;
        otherwise that binding's accepted_outlier_file_ids."""
        for folder_rel, accepted in frozen_folders.items():
            if is_in_folder_subtree(source_rel, folder_rel):
                return accepted
        return None

    plans: list[PlannedMove] = []
    for fid, fd in file_data.items():
        source_rel: str = fd["path"]
        person_ids: set[int] = fd["person_ids"]
        decoded_ok: bool = fd["decoded_ok"]

        accepted_outliers = _frozen_accepted_outliers(source_rel)
        if accepted_outliers is not None and fid not in accepted_outliers:
            continue  # folder (or one of its subfolders) is a respected pre-existing binding

        if fid in pending_file_ids:
            continue  # awaiting the user's confirm/reject in the pending-match review

        # Subtract any person explicitly rejected for this exact file. A file
        # whose only candidate person was rejected is left in place, same as
        # a frozen-folder skip — the safest, least-surprising outcome for
        # "not this person".
        rejected_pids = rejected_by_hash.get(fd["content_hash"] or "", set())
        effective_person_ids = person_ids - rejected_pids
        if person_ids and not effective_person_ids:
            continue

        if not decoded_ok:
            dest_folder = "_unsorted"
            dest_pid: int | None = None
            dest_name: str | None = None
        elif not effective_person_ids:
            # Has face records but all person_id = NULL (noise cluster) —
            # nobody to route to; stays in place, same as a zero-face file.
            continue
        elif len(effective_person_ids) == 1:
            dest_pid = next(iter(effective_person_ids))
            dest_name = person_display.get(dest_pid)
            if dest_name is None:
                continue  # person not yet named — leave file in place
            dest_folder = safe_folder_name(dest_name)
        else:
            # Multiple persons in this file — use override or pick dominant
            # (excluding anyone rejected for this file from either path)
            if fid in route_choices and route_choices[fid] in effective_person_ids:
                dest_pid = route_choices[fid]
            else:
                eligible_placeholders = ",".join("?" * len(effective_person_ids))
                row = conn.execute(
                    f"""
                    SELECT person_id, COUNT(*) AS n
                    FROM faces
                    WHERE file_id = ? AND provider_id = ? AND person_id IN ({eligible_placeholders})
                    GROUP BY person_id ORDER BY n DESC LIMIT 1
                    """,
                    (fid, provider_id, *effective_person_ids),
                ).fetchone()
                dest_pid = int(row["person_id"]) if row else None
            dest_name = person_display.get(dest_pid) if dest_pid is not None else None
            if dest_name is None:
                continue  # dominant person unknown/not yet named — leave file in place
            dest_folder = safe_folder_name(dest_name)

        if dest_pid is not None and dest_pid in bound_folder_by_person:
            dest_folder_rel = bound_folder_by_person[dest_pid]
        else:
            dest_folder_rel = f"{target_rel}/{dest_folder}"

        # Skip files already in their destination folder — prevents _1 churn on re-run.
        if PurePosixPath(source_rel).parent.as_posix() == dest_folder_rel:
            continue

        plans.append(
            PlannedMove(
                source_rel=source_rel,
                dest_folder_rel=dest_folder_rel,
                person_id=dest_pid,
                person_name=dest_name,
            )
        )

    # Files that failed to decode never get a `faces` row at all — a failed
    # decode always yields zero detected faces (engine.extract_file_faces),
    # and persist_face_scan only inserts a row per detected face. So the
    # `files JOIN faces` query above can never see them; without this,
    # undecodable files would silently stay in place forever instead of
    # routing to the visible _unsorted holding area (safety invariant:
    # "everything routes somewhere").
    unsorted_dest = f"{target_rel}/_unsorted"
    for row in conn.execute("SELECT id, path FROM files WHERE decoded_ok = 0"):
        fid = int(row["id"])
        if fid in file_data:
            continue  # already planned via the faces join above
        source_rel = row["path"]

        accepted_outliers = _frozen_accepted_outliers(source_rel)
        if accepted_outliers is not None and fid not in accepted_outliers:
            continue  # folder (or one of its subfolders) is a respected pre-existing binding

        if PurePosixPath(source_rel).parent.as_posix() == unsorted_dest:
            continue
        plans.append(
            PlannedMove(
                source_rel=source_rel,
                dest_folder_rel=unsorted_dest,
                person_id=None,
                person_name=None,
            )
        )

    return sorted(plans, key=lambda m: (m.dest_folder_rel, m.source_rel))
