"""Files a scan could not process: list them (with the reason) and label them by hand.

A file that times out or cannot be decoded is kept, never dropped: the folder view
shows it in its own section so the user can open it and tag it to a person. See
store/unprocessed.py.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from mediamind.api.models import UnprocessedOut, UnprocessedTagIn
from mediamind.store.db import open_library_db
from mediamind.store.unprocessed import list_unprocessed, tag_file, untag_file

router = APIRouter(tags=["unprocessed"])


def _library_root(request: Request, library_id: str) -> Path:
    lib = request.app.state.registry.get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    return Path(lib.path)


@router.get("/libraries/{library_id}/unprocessed", response_model=list[UnprocessedOut])
def get_unprocessed(library_id: str, request: Request, under: str | None = Query(default=None)):
    """Every file the last scan could not process; `under` narrows to one
    library-relative folder (and its subfolders)."""
    root = _library_root(request, library_id)
    conn = open_library_db(root)
    try:
        rows = list_unprocessed(conn, under)
    finally:
        conn.close()
    return [
        UnprocessedOut(
            path=u.path,
            abs_path=str(root / u.path),
            kind=u.kind,
            size=u.size,
            reason=u.reason,
            message=u.message,
            attempts=u.attempts,
            failed_at=u.failed_at,
            person_ids=u.person_ids,
        )
        for u in rows
    ]


@router.post("/libraries/{library_id}/unprocessed/tag")
def tag_unprocessed(library_id: str, body: UnprocessedTagIn, request: Request):
    """Label a file with a person by hand; it then appears in that person's view."""
    conn = open_library_db(_library_root(request, library_id))
    try:
        ok = tag_file(conn, body.path, body.person_id)
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="Unknown person")
    return {"ok": True}


@router.post("/libraries/{library_id}/unprocessed/untag")
def untag_unprocessed(library_id: str, body: UnprocessedTagIn, request: Request):
    conn = open_library_db(_library_root(request, library_id))
    try:
        untag_file(conn, body.path, body.person_id)
    finally:
        conn.close()
    return {"ok": True}
