"""Teach who's who: pick clear faces, name them, re-sort the library.

  GET  /v1/libraries/{id}/teach/faces       face tiles to pick examples from
  GET  /v1/libraries/{id}/teach/people      people with example counts (here + other libraries)
  PUT  /v1/libraries/{id}/teach/people/{person_id}/membership   {membership: member | guest | null}
  POST /v1/libraries/{id}/teach/examples    {face_ids, person_id | name}
  POST /v1/libraries/{id}/teach/examples/remove   {face_ids}
  POST /v1/libraries/{id}/teach/apply       re-sort against every library's examples
  POST /v1/libraries/{id}/files/forget-missing   drop index rows of files gone from disk

See core/faces/teach.py.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from mediamind.api.models import (
    TeachApplyOut,
    TeachExamplesIn,
    TeachExamplesRemoveIn,
    TeachFaceOut,
    TeachFacesOut,
    TeachMembershipIn,
    TeachPersonOut,
)
from mediamind.core.faces import teach
from mediamind.store.db import open_library_db
from mediamind.store.persons import latest_faces_scan

router = APIRouter(tags=["teach"])

# A face narrower than this share of its frame's largest face, or not among the
# frame's two largest, is treated as a background face (bystander, crowd).
BACKGROUND_WIDTH_RATIO = 0.5

# A person in fewer files than 1/GUEST_SHARE of this folder's most-seen person is a guest here
# (someone from another group in a few shared pictures), unless the user says otherwise.
# ponytail: one share for every folder; a folder of one person plus many one-off friends is the
# case the manual switch covers.
GUEST_SHARE = 20


def _library_root(request: Request, library_id: str) -> Path:
    lib = request.app.state.registry.get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    return Path(lib.path)


def _provider(conn) -> str:
    scan = latest_faces_scan(conn)
    if scan is None:
        raise HTTPException(status_code=409, detail="Scan this folder for people first.")
    row = conn.execute("SELECT provider_id FROM faces LIMIT 1").fetchone()
    if row is None:
        raise HTTPException(status_code=409, detail="The last scan found no faces here.")
    return row["provider_id"]


def _other_library_openers(request: Request, library_id: str):
    for lib in request.app.state.registry.list():
        if lib.id != library_id:
            yield lambda p=Path(lib.path): open_library_db(p)


@router.get("/libraries/{library_id}/teach/faces", response_model=TeachFacesOut)
def teach_faces(
    library_id: str,
    request: Request,
    under: str | None = Query(default=None, description="library-relative folder"),
    person_id: int | None = Query(default=None),
    unnamed: bool = Query(default=False, description="only faces not on a named person"),
    include_background: bool = Query(default=False),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=300, ge=1, le=20000),
):
    root = _library_root(request, library_id)
    conn = open_library_db(root)
    try:
        provider_id = _provider(conn)
        rows = conn.execute(
            """
            SELECT f.id, f.file_id, f.frame_no, f.bbox_x2 - f.bbox_x1 AS w, f.person_id,
                   p.name, fi.path, fi.kind
            FROM faces f JOIN files fi ON fi.id = f.file_id
            LEFT JOIN persons p ON p.id = f.person_id
            WHERE f.provider_id = ?
            """,
            (provider_id,),
        ).fetchall()
        example_ids = {e.face_id for e in teach.library_examples(conn, provider_id)}
    finally:
        conn.close()

    frames = defaultdict(list)
    for r in rows:
        frames[(r["file_id"], r["frame_no"])].append(r["w"])
    for ws in frames.values():
        ws.sort(reverse=True)

    prefix = under.strip("/").replace("\\", "/") + "/" if under and under.strip("/") else None
    out = []
    for r in rows:
        ws = frames[(r["file_id"], r["frame_no"])]
        background = r["w"] < BACKGROUND_WIDTH_RATIO * ws[0] or (len(ws) > 2 and r["w"] < ws[1])
        path = r["path"].replace("\\", "/")
        if prefix and not path.startswith(prefix):
            continue
        if person_id is not None and r["person_id"] != person_id:
            continue
        if unnamed and r["name"]:
            continue
        if background and not include_background and r["id"] not in example_ids:
            continue
        out.append(TeachFaceOut(
            face_id=r["id"], file_id=r["file_id"], path=path, abs_path=str(root / path),
            kind=r["kind"], frame_no=r["frame_no"], width=r["w"], person_id=r["person_id"],
            person_name=r["name"], is_example=r["id"] in example_ids, background=background,
        ))
    # Examples first, then biggest (clearest) faces.
    out.sort(key=lambda f: (not f.is_example, -f.width))
    return TeachFacesOut(total=len(out), faces=out[offset:offset + limit])


@router.get("/libraries/{library_id}/teach/people", response_model=list[TeachPersonOut])
def teach_people(library_id: str, request: Request):
    root = _library_root(request, library_id)
    conn = open_library_db(root)
    try:
        provider_id = _provider(conn)
        here = defaultdict(int)
        for e in teach.library_examples(conn, provider_id):
            here[e.person_id] += 1
        persons = conn.execute(
            """SELECT p.id, p.name, p.membership, COUNT(DISTINCT f.file_id) AS n FROM persons p
               LEFT JOIN faces f ON f.person_id = p.id
               WHERE p.provider_id = ? AND (p.name IS NOT NULL OR p.id IN (%s))
               GROUP BY p.id""" % ",".join(str(i) for i in here) if here else
            """SELECT p.id, p.name, p.membership, COUNT(DISTINCT f.file_id) AS n FROM persons p
               LEFT JOIN faces f ON f.person_id = p.id
               WHERE p.provider_id = ? AND p.name IS NOT NULL GROUP BY p.id""",
            (provider_id,),
        ).fetchall()
    finally:
        conn.close()
    elsewhere, display = teach.pool_foreign_examples(_other_library_openers(request, library_id), provider_id)

    top = max((p["n"] for p in persons), default=0)
    out, seen = [], set()
    for p in persons:
        key = teach.name_key(p["name"]) if p["name"] else None
        seen.add(key)
        out.append(TeachPersonOut(
            person_id=p["id"], name=p["name"] or "Unnamed person",
            examples_here=here.get(p["id"], 0),
            examples_elsewhere=len(elsewhere.get(key, [])) if key else 0, files=p["n"],
            guest=p["membership"] == "guest" or (p["membership"] is None and p["n"] * GUEST_SHARE < top),
            membership=p["membership"],
        ))
    for key, embs in elsewhere.items():
        if key not in seen:
            out.append(TeachPersonOut(person_id=None, name=display.get(key, key), examples_here=0,
                                      examples_elsewhere=len(embs), files=0, guest=True))
    out.sort(key=lambda p: p.name.casefold())
    return out


@router.put("/libraries/{library_id}/teach/people/{person_id}/membership")
def set_membership(library_id: str, person_id: int, body: TeachMembershipIn, request: Request):
    """Say whether a person belongs to this folder or is only a guest in it. Only changes how
    Who's who lists them; sorting and their files are untouched."""
    conn = open_library_db(_library_root(request, library_id))
    try:
        cur = conn.execute("UPDATE persons SET membership = ? WHERE id = ?", (body.membership, person_id))
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Unknown person")
    return {"person_id": person_id, "membership": body.membership}


@router.post("/libraries/{library_id}/teach/examples")
def add_examples(library_id: str, body: TeachExamplesIn, request: Request):
    if not body.face_ids:
        raise HTTPException(status_code=422, detail="Pick at least one face.")
    conn = open_library_db(_library_root(request, library_id))
    try:
        try:
            pid = teach.add_examples(conn, body.face_ids, person_id=body.person_id, name=body.name)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    finally:
        conn.close()
    return {"person_id": pid, "added": len(body.face_ids)}


@router.post("/libraries/{library_id}/teach/examples/remove")
def remove_examples(library_id: str, body: TeachExamplesRemoveIn, request: Request):
    conn = open_library_db(_library_root(request, library_id))
    try:
        teach.remove_examples(conn, body.face_ids)
    finally:
        conn.close()
    return {"removed": len(body.face_ids)}


@router.post("/libraries/{library_id}/teach/apply", response_model=TeachApplyOut)
def apply(library_id: str, request: Request):
    conn = open_library_db(_library_root(request, library_id))
    try:
        return teach.apply_in_registry(request.app.state.registry, library_id, conn, _provider(conn))
    finally:
        conn.close()


@router.get("/libraries/{library_id}/teach/faces/{face_id}/frame")
def face_frame(
    library_id: str,
    face_id: int,
    request: Request,
    size: int = Query(default=1600, ge=256, le=4096),
):
    """The whole photo (or the sampled video frame) a face came from, with that face
    outlined — the yes/no review needs the real picture, not a small crop. Disk-cached
    beside the face crops, keyed like them, so it still shows while the drive is offline."""
    from mediamind.api.routes.persons import _face_thumb_cache_key, _THUMB_CACHE_HEADERS
    from mediamind.config import face_thumb_cache_dir
    from mediamind.core.faces.engine import load_frame
    from mediamind.store.persons import get_face

    root = _library_root(request, library_id)
    conn = open_library_db(root)
    try:
        info = get_face(conn, face_id)
    finally:
        conn.close()
    if info is None:
        raise HTTPException(status_code=404, detail="Unknown face id")

    cache_path = face_thumb_cache_dir() / library_id / (
        "frame-" + _face_thumb_cache_key(info.path, info.frame_no, info.bbox, size) + ".jpg")
    if not cache_path.exists():
        abs_path = root / info.path
        if not abs_path.exists():
            raise HTTPException(status_code=409, detail="The file isn't reachable right now. Is its drive connected?")
        frame = load_frame(abs_path, "image" if info.kind == "photo" else info.kind, info.frame_no)
        if frame is None:
            raise HTTPException(status_code=422, detail="This file couldn't be decoded.")
        import cv2

        h, w = frame.shape[:2]
        scale = min(1.0, size / max(h, w))
        if scale < 1.0:
            frame = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
        x1, y1, x2, y2 = (int(v * scale) for v in info.bbox)
        thick = max(2, int(max(frame.shape[:2]) / 300))
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 0), thick + 2)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (80, 220, 255), thick)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not ok:
            raise HTTPException(status_code=422, detail="This file couldn't be decoded.")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_bytes(buf.tobytes())
        tmp.replace(cache_path)
    return FileResponse(cache_path, media_type="image/jpeg", headers=_THUMB_CACHE_HEADERS)


@router.post("/libraries/{library_id}/files/forget-missing")
def forget_missing_files(library_id: str, request: Request) -> dict:
    """Drop index rows (and their faces and review questions) of files that are gone from
    disk, so no screen offers a deleted file. Never touches a file; see store/missing_files.py."""
    from mediamind.store.missing_files import forget_missing

    root = _library_root(request, library_id)
    conn = open_library_db(root)
    try:
        return {"removed": forget_missing(conn, root)}
    finally:
        conn.close()
