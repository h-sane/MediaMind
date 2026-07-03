"""Multi-person file review: list ambiguous files and record routing decisions.

When a file contains faces from multiple distinct persons, the organizer must
pick one person's folder to put it in. The user can override this via
route_choices. These routes expose that workflow.

Routes:
  GET  /v1/libraries/{id}/multi-person          -> list[MultiPersonFileOut]
  POST /v1/libraries/{id}/route-choices         -> {updated: int}
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from mediamind.api.models import MultiPersonFileOut, PersonOptionOut, RouteChoicesIn
from mediamind.config import library_data_dir
from mediamind.core.libraries import LibraryRegistry
from mediamind.store.db import library_db_path, open_db
from mediamind.store.persons import latest_faces_scan

router = APIRouter(tags=["multi-person"])


def _registry(request: Request) -> LibraryRegistry:
    return request.app.state.registry


def _get_library_root(request: Request, library_id: str) -> Path:
    lib = _registry(request).get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    return Path(lib.path)


def _open_db(library_root: Path):
    return open_db(library_db_path(library_data_dir(library_root)))


def _require_provider_id(conn, library_root: Path) -> str:
    scan = latest_faces_scan(conn)
    if scan is None:
        raise HTTPException(
            status_code=422,
            detail="No face scan found — run a face scan first",
        )
    params = json.loads(scan["params"] or "{}")
    return params.get("provider_id", "")


@router.get(
    "/libraries/{library_id}/multi-person",
    response_model=list[MultiPersonFileOut],
)
def list_multi_person_files(library_id: str, request: Request):
    """Return files that have faces from 2+ distinct persons.

    Each entry includes per-person face counts and sample face IDs for
    thumbnails, plus the current route_choice override (if any).
    """
    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        provider_id = _require_provider_id(conn, library_root)

        # Files with >= 2 distinct assigned persons
        ambiguous_rows = conn.execute(
            """
            SELECT fi.id, fi.path, fi.kind
            FROM files fi
            JOIN faces f ON f.file_id = fi.id
            WHERE f.provider_id = ? AND f.person_id IS NOT NULL
            GROUP BY fi.id
            HAVING COUNT(DISTINCT f.person_id) >= 2
            ORDER BY fi.path
            """,
            (provider_id,),
        ).fetchall()

        # Current route choices: file_id -> person_id
        choices = {
            int(r["file_id"]): int(r["person_id"])
            for r in conn.execute("SELECT file_id, person_id FROM route_choices")
        }

        result: list[MultiPersonFileOut] = []
        for row in ambiguous_rows:
            fid = int(row["id"])

            # Per-person face counts + sample face id for thumbnails
            person_rows = conn.execute(
                """
                SELECT f.person_id, p.auto_label, p.name,
                       COUNT(*) AS face_count, MIN(f.id) AS sample_face_id
                FROM faces f
                JOIN persons p ON p.id = f.person_id
                WHERE f.file_id = ? AND f.provider_id = ? AND f.person_id IS NOT NULL
                GROUP BY f.person_id
                ORDER BY face_count DESC
                """,
                (fid, provider_id),
            ).fetchall()

            persons = [
                PersonOptionOut(
                    person_id=int(pr["person_id"]),
                    person_name=pr["name"] or pr["auto_label"],
                    face_count=int(pr["face_count"]),
                    sample_face_id=int(pr["sample_face_id"]),
                )
                for pr in person_rows
            ]

            result.append(
                MultiPersonFileOut(
                    file_id=fid,
                    path=row["path"],
                    kind=row["kind"],
                    persons=persons,
                    current_choice=choices.get(fid),
                )
            )
    finally:
        conn.close()

    return result


@router.post("/libraries/{library_id}/route-choices")
def set_route_choices(library_id: str, body: RouteChoicesIn, request: Request):
    """Set or update route_choices for a batch of files.

    Each choice says "when organizing, put file X into person Y's folder".
    Overwrites any previous choice for the same file.
    Passing person_id = 0 clears the choice (reverts to auto-pick).
    """
    if not body.choices:
        return {"updated": 0}

    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        now = time.time()
        updated = 0
        for choice in body.choices:
            if choice.person_id == 0:
                conn.execute(
                    "DELETE FROM route_choices WHERE file_id = ?",
                    (choice.file_id,),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO route_choices (file_id, person_id, decided_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(file_id) DO UPDATE SET
                        person_id = excluded.person_id,
                        decided_at = excluded.decided_at
                    """,
                    (choice.file_id, choice.person_id, now),
                )
            updated += 1
        conn.commit()
    finally:
        conn.close()

    return {"updated": updated}
