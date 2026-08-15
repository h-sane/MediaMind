"""Incremental duplicate-flag routes: list + dismiss (Performance & Ingest
V4 Phase 3). Registered in api/app.py."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from mediamind.config import library_data_dir
from mediamind.core.libraries import LibraryRegistry
from mediamind.store.db import library_db_path, open_db
from mediamind.store.duplicate_flags import dismiss_flag, list_flags

router = APIRouter(tags=["duplicate-flags"])


class DuplicateFlagOut(BaseModel):
    id: int
    path: str
    match_path: str
    match_type: str
    flagged_at: float


def _registry(request: Request) -> LibraryRegistry:
    return request.app.state.registry


def _get_library_root(request: Request, library_id: str) -> Path:
    lib = _registry(request).get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    return Path(lib.path)


def _open_library_db(library_root: Path):
    return open_db(library_db_path(library_data_dir(library_root)))


@router.get("/libraries/{library_id}/duplicate-flags", response_model=list[DuplicateFlagOut])
def list_duplicate_flags(library_id: str, request: Request):
    library_root = _get_library_root(request, library_id)
    conn = _open_library_db(library_root)
    try:
        flags = list_flags(conn, library_root)
    finally:
        conn.close()
    return [
        DuplicateFlagOut(
            id=f.id, path=f.path, match_path=f.match_path, match_type=f.match_type, flagged_at=f.flagged_at
        )
        for f in flags
    ]


@router.post("/libraries/{library_id}/duplicate-flags/{flag_id}/dismiss")
def dismiss_duplicate_flag(library_id: str, flag_id: int, request: Request):
    library_root = _get_library_root(request, library_id)
    conn = _open_library_db(library_root)
    try:
        ok = dismiss_flag(conn, flag_id)
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="Unknown duplicate flag")
    return {"status": "dismissed"}
