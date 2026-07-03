"""Pending face-match review: list unresolved matches and record decisions.

Pending matches are created during face scans when a named person is recognised
in a file that hasn't been scanned before (`pending_for_named=True`). The user
reviews each suggestion and either confirms (face gets assigned to the person)
or rejects (face stays unassigned).

Routes:
  GET  /v1/libraries/{id}/pending               -> list[PendingMatchOut]
  POST /v1/libraries/{id}/pending/decisions     -> {updated: int}
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from mediamind.api.models import PendingDecisionsIn, PendingMatchOut
from mediamind.config import library_data_dir
from mediamind.core.libraries import LibraryRegistry
from mediamind.store.db import library_db_path, open_db

router = APIRouter(tags=["pending"])


def _registry(request: Request) -> LibraryRegistry:
    return request.app.state.registry


def _get_library_root(request: Request, library_id: str) -> Path:
    lib = _registry(request).get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    return Path(lib.path)


def _open_db(library_root: Path):
    return open_db(library_db_path(library_data_dir(library_root)))


@router.get("/libraries/{library_id}/pending", response_model=list[PendingMatchOut])
def list_pending(library_id: str, request: Request):
    """Return all pending matches that haven't been decided yet, highest confidence first."""
    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        rows = conn.execute(
            """
            SELECT pm.id, pm.face_id, pm.person_id, pm.confidence,
                   p.auto_label, p.name
            FROM pending_matches pm
            JOIN persons p ON p.id = pm.person_id
            WHERE pm.decision IS NULL
            ORDER BY pm.confidence DESC
            """
        ).fetchall()
    finally:
        conn.close()

    return [
        PendingMatchOut(
            id=r["id"],
            face_id=r["face_id"],
            person_id=r["person_id"],
            person_name=r["name"] or r["auto_label"],
            confidence=r["confidence"],
        )
        for r in rows
    ]


@router.post("/libraries/{library_id}/pending/decisions")
def decide_pending(library_id: str, body: PendingDecisionsIn, request: Request):
    """Confirm or reject a batch of pending face matches.

    confirmed → assigns the face to the suggested person (UPDATE faces SET person_id).
    rejected  → face stays unassigned (person_id remains NULL).
    """
    if not body.decisions:
        return {"updated": 0}

    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        updated = 0
        for item in body.decisions:
            if item.decision not in ("confirmed", "rejected"):
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid decision '{item.decision}' — must be 'confirmed' or 'rejected'",
                )

            row = conn.execute(
                "SELECT face_id, person_id FROM pending_matches WHERE id = ?",
                (item.pending_id,),
            ).fetchone()
            if row is None:
                continue  # already decided or doesn't exist; skip silently

            if item.decision == "confirmed":
                conn.execute(
                    "UPDATE faces SET person_id = ? WHERE id = ?",
                    (row["person_id"], row["face_id"]),
                )

            conn.execute(
                "UPDATE pending_matches SET decision = ? WHERE id = ?",
                (item.decision, item.pending_id),
            )
            updated += 1

        conn.commit()
    finally:
        conn.close()

    return {"updated": updated}
