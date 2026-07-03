"""Person management routes: list, rename, merge, media, face thumbnail."""

from __future__ import annotations

import io
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from mediamind.api.models import (
    PersonMediaItemOut,
    PersonMergeIn,
    PersonOut,
    PersonRenameIn,
    PersonsOut,
)
from mediamind.config import library_data_dir
from mediamind.core.faces.engine import load_frame
from mediamind.core.libraries import LibraryRegistry
from mediamind.store.db import library_db_path, open_db
from mediamind.store.persons import (
    get_face,
    list_person_summaries,
    merge_persons,
    person_media,
    rename_person,
    latest_faces_scan,
)

router = APIRouter(tags=["persons"])


def _registry(request: Request) -> LibraryRegistry:
    return request.app.state.registry


def _get_library_and_root(request: Request, library_id: str) -> tuple:
    lib = _registry(request).get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    return lib, Path(lib.path)


def _open_library_db(library_root: Path):
    data_dir = library_data_dir(library_root)
    return open_db(library_db_path(data_dir))


@router.get("/libraries/{library_id}/persons", response_model=PersonsOut)
def list_persons(library_id: str, request: Request):
    _, library_root = _get_library_and_root(request, library_id)
    conn = _open_library_db(library_root)
    try:
        scan = latest_faces_scan(conn)
        if scan is None:
            raise HTTPException(
                status_code=404,
                detail="No face scan found — run a scan first",
            )

        params = json.loads(scan["params"] or "{}")
        summary = json.loads(scan["summary"] or "{}")
        provider_id: str = params.get("provider_id", "")

        summaries = list_person_summaries(conn, provider_id)
        persons = [
            PersonOut(
                id=s.id,
                auto_label=s.auto_label,
                name=s.name,
                face_count=s.face_count,
                media_count=s.media_count,
                sample_face_ids=s.sample_face_ids,
            )
            for s in summaries
        ]

        unassigned = conn.execute(
            "SELECT COUNT(*) FROM faces WHERE person_id IS NULL AND provider_id = ?",
            (provider_id,),
        ).fetchone()[0]

        pending_count = conn.execute(
            "SELECT COUNT(*) FROM pending_matches WHERE decision IS NULL",
        ).fetchone()[0]

        multi_person_count = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT file_id FROM faces
                WHERE provider_id = ? AND person_id IS NOT NULL
                GROUP BY file_id
                HAVING COUNT(DISTINCT person_id) >= 2
            )
            """,
            (provider_id,),
        ).fetchone()[0]

    finally:
        conn.close()

    return PersonsOut(
        scan_id=scan["id"],
        scanned_at=scan["finished_at"],
        provider_id=provider_id,
        persons=persons,
        unassigned_faces=unassigned,
        no_face_files=summary.get("no_face_files", 0),
        unreadable_files=summary.get("unreadable_files", 0),
        pending_count=pending_count,
        multi_person_count=multi_person_count,
    )


@router.patch("/libraries/{library_id}/persons/{person_id}")
def rename_person_endpoint(
    library_id: str, person_id: int, body: PersonRenameIn, request: Request
):
    _, library_root = _get_library_and_root(request, library_id)
    conn = _open_library_db(library_root)
    try:
        ok = rename_person(conn, person_id, body.name)
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="Unknown person")
    return {"ok": True}


@router.post("/libraries/{library_id}/persons/merge")
def merge_persons_endpoint(
    library_id: str, body: PersonMergeIn, request: Request
):
    _, library_root = _get_library_and_root(request, library_id)
    conn = _open_library_db(library_root)
    try:
        ok = merge_persons(conn, body.source_id, body.target_id)
    finally:
        conn.close()
    if not ok:
        raise HTTPException(
            status_code=422,
            detail="Cannot merge: unknown persons, same person, or provider mismatch",
        )
    return {"ok": True}


@router.get(
    "/libraries/{library_id}/persons/{person_id}/media",
    response_model=list[PersonMediaItemOut],
)
def list_person_media(library_id: str, person_id: int, request: Request):
    _, library_root = _get_library_and_root(request, library_id)
    conn = _open_library_db(library_root)
    try:
        items = person_media(conn, person_id)
    finally:
        conn.close()
    return [
        PersonMediaItemOut(
            file_id=fi.file_id,
            path=fi.path,
            kind=fi.kind,
            face_id=fi.id,
            bbox=fi.bbox,
        )
        for fi in items
    ]


@router.get("/libraries/{library_id}/faces/{face_id}/thumbnail")
def face_thumbnail(
    library_id: str,
    face_id: int,
    request: Request,
    size: int = Query(default=192, ge=48, le=512),
):
    """Return a cropped JPEG thumbnail of a face.

    Keyed by faces.id — the endpoint cannot read arbitrary files; only faces
    from a scan are accessible (same rationale as duplicates thumbnail).
    """
    _, library_root = _get_library_and_root(request, library_id)
    conn = _open_library_db(library_root)
    try:
        info = get_face(conn, face_id)
    finally:
        conn.close()

    if info is None:
        raise HTTPException(status_code=404, detail="Unknown face id")

    abs_path = library_root / info.path
    frame = load_frame(abs_path, info.kind, info.frame_no)
    if frame is None:
        raise HTTPException(status_code=422, detail="Could not decode frame for thumbnail")

    try:
        import cv2
        import numpy as np

        h, w = frame.shape[:2]
        x1, y1, x2, y2 = info.bbox

        # Expand bbox 25% each side for context
        fw = x2 - x1
        fh = y2 - y1
        pad_w = fw * 0.25
        pad_h = fh * 0.25
        x1 = max(0.0, x1 - pad_w)
        y1 = max(0.0, y1 - pad_h)
        x2 = min(float(w), x2 + pad_w)
        y2 = min(float(h), y2 + pad_h)

        crop = frame[int(y1):int(y2), int(x1):int(x2)]
        if crop.size == 0:
            raise ValueError("Empty crop")

        # Resize so the longest edge is `size`
        ch, cw = crop.shape[:2]
        scale = size / max(ch, cw)
        new_w = max(1, int(cw * scale))
        new_h = max(1, int(ch * scale))
        crop = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_AREA)

        ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise ValueError("JPEG encode failed")

        return StreamingResponse(io.BytesIO(bytes(buf)), media_type="image/jpeg")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Thumbnail error: {exc}")
