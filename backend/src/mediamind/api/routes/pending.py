"""Pending face-match review: list unresolved matches and record decisions.

Pending matches are created during face scans when a face's best-matching
person clears SUGGEST_MATCH_THRESHOLD but not the higher AUTO_MATCH_THRESHOLD
(`store.persons.gate_face_match`), in a file that hasn't been scanned before.
The user reviews each suggestion and either confirms (face gets assigned to
the person), reassigns it to a different person, or rejects (face keeps
whatever identity it already had — see `gate_face_match`'s docstring).

Routes:
  GET  /v1/libraries/{id}/pending               -> list[PendingMatchOut]
  POST /v1/libraries/{id}/pending/decisions     -> {updated: int}
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from mediamind.api.models import PendingDecisionsIn, PendingMatchOut
from mediamind.core.libraries import LibraryRegistry
from mediamind.store import face_assignments
from mediamind.store.bindings import placement_confirmed_pending_ids
from mediamind.store.db import open_library_db

router = APIRouter(tags=["pending"])


def _registry(request: Request) -> LibraryRegistry:
    return request.app.state.registry


def _get_library_root(request: Request, library_id: str) -> Path:
    lib = _registry(request).get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    return Path(lib.path)


def _open_db(library_root: Path):
    return open_library_db(library_root)


@router.get("/libraries/{library_id}/pending", response_model=list[PendingMatchOut])
def list_pending(library_id: str, request: Request):
    """Return all pending matches that haven't been decided yet, highest confidence first."""
    library_root = _get_library_root(request, library_id)
    conn = _open_db(library_root)
    try:
        rows = conn.execute(
            """
            SELECT pm.id, pm.face_id, pm.person_id, pm.confidence,
                   p.auto_label, p.name, fi.path, fi.kind
            FROM pending_matches pm
            JOIN persons p ON p.id = pm.person_id
            JOIN faces f ON f.id = pm.face_id
            JOIN files fi ON fi.id = f.file_id
            WHERE pm.decision IS NULL
            ORDER BY pm.confidence DESC
            """
        ).fetchall()
        # ADR-0010: a file inside a person's bound folder is confirmed by
        # placement, so drop any pending match for that folder's own person.
        suppressed = placement_confirmed_pending_ids(conn)
    finally:
        conn.close()

    return [
        PendingMatchOut(
            id=r["id"],
            face_id=r["face_id"],
            person_id=r["person_id"],
            person_name=r["name"] or r["auto_label"],
            confidence=r["confidence"],
            path=r["path"],
            abs_path=str(library_root / r["path"]),
            kind=r["kind"],
        )
        for r in rows
        if r["id"] not in suppressed
    ]


@router.post("/libraries/{library_id}/pending/decisions")
def decide_pending(library_id: str, body: PendingDecisionsIn, request: Request):
    """Confirm or reject a batch of pending face matches.

    confirmed → assigns the face to the suggested person, or to
                `reassign_to_person_id` if given (the swipe-review "this is a
                different person" action) — either way, UPDATE faces SET person_id.
    rejected  → face keeps whatever person_id it already had (its own cluster
                identity, if any) — the suggestion is simply dismissed.
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
                """
                SELECT pm.face_id, pm.person_id, f.provider_id,
                       f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, fi.content_hash
                FROM pending_matches pm
                JOIN faces f ON f.id = pm.face_id
                JOIN files fi ON fi.id = f.file_id
                WHERE pm.id = ?
                """,
                (item.pending_id,),
            ).fetchone()
            if row is None:
                continue  # already decided or doesn't exist; skip silently

            if item.decision == "confirmed":
                target_person_id = item.reassign_to_person_id or row["person_id"]
                conn.execute(
                    "UPDATE faces SET person_id = ? WHERE id = ?",
                    (target_person_id, row["face_id"]),
                )
                # Durably record it — a user-confirmed match must never be
                # un-named by re-clustering on a later rescan.
                if row["content_hash"]:
                    bbox = (row["bbox_x1"], row["bbox_y1"], row["bbox_x2"], row["bbox_y2"])
                    face_assignments.record_assignment(
                        conn, row["content_hash"], row["provider_id"], bbox, target_person_id, source="user",
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
