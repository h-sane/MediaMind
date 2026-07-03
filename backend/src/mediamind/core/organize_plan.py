"""Build an organize plan: for each scanned file with faces, determine destination.

The plan answers "where should this file go?" without touching anything on disk.
`build_organize_plan` returns a list of `PlannedMove` dataclasses that can be
converted directly to `safety.FileOp` objects for execution.

Routing rules (mirrors V0 invariant — every file routes somewhere):
  - File with exactly one assigned person  → People/<PersonName>/
  - File with multiple persons             → most-faces-count person's folder
                                             (or route_choices override)
  - File with faces but all noise          → People/_noise/
  - File that failed to decode             → People/_unsorted/

Files with zero face records are NOT included in the plan; they stay in place.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


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
    # Person display names: id -> name or auto_label
    person_display: dict[int, str] = {}
    for p in conn.execute(
        "SELECT id, auto_label, name FROM persons WHERE provider_id = ?",
        (provider_id,),
    ):
        person_display[int(p["id"])] = p["name"] or p["auto_label"]

    # User-assigned route overrides (multi-person review)
    route_choices: dict[int, int] = {}  # file_id -> person_id
    for rc in conn.execute("SELECT file_id, person_id FROM route_choices"):
        route_choices[int(rc["file_id"])] = int(rc["person_id"])

    # Aggregate face data per file
    file_data: dict[int, dict] = {}
    for row in conn.execute(
        """
        SELECT fi.id, fi.path, fi.decoded_ok, f.person_id
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
                "decoded_ok": bool(row["decoded_ok"]),
                "person_ids": set(),
            }
        if row["person_id"] is not None:
            file_data[fid]["person_ids"].add(int(row["person_id"]))

    plans: list[PlannedMove] = []
    for fid, fd in file_data.items():
        source_rel: str = fd["path"]
        person_ids: set[int] = fd["person_ids"]
        decoded_ok: bool = fd["decoded_ok"]

        if not decoded_ok:
            dest_folder = "_unsorted"
            dest_pid: int | None = None
            dest_name: str | None = None
        elif not person_ids:
            # Has face records but all person_id = NULL (noise cluster)
            dest_folder = "_noise"
            dest_pid = None
            dest_name = None
        elif len(person_ids) == 1:
            dest_pid = next(iter(person_ids))
            dest_name = person_display.get(dest_pid)
            dest_folder = safe_folder_name(dest_name) if dest_name else "_other"
        else:
            # Multiple persons in this file — use override or pick dominant
            if fid in route_choices:
                dest_pid = route_choices[fid]
            else:
                row = conn.execute(
                    """
                    SELECT person_id, COUNT(*) AS n
                    FROM faces
                    WHERE file_id = ? AND provider_id = ? AND person_id IS NOT NULL
                    GROUP BY person_id ORDER BY n DESC LIMIT 1
                    """,
                    (fid, provider_id),
                ).fetchone()
                dest_pid = int(row["person_id"]) if row else None
            if dest_pid is not None:
                dest_name = person_display.get(dest_pid)
                dest_folder = safe_folder_name(dest_name) if dest_name else "_other"
            else:
                dest_folder = "_noise"
                dest_name = None

        dest_folder_rel = f"{target_rel}/{dest_folder}"
        plans.append(
            PlannedMove(
                source_rel=source_rel,
                dest_folder_rel=dest_folder_rel,
                person_id=dest_pid,
                person_name=dest_name,
            )
        )

    return sorted(plans, key=lambda m: (m.dest_folder_rel, m.source_rel))
