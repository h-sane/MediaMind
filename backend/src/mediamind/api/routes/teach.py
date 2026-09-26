"""Teach who's who: pick clear faces, name them, re-sort the library.

  GET  /v1/libraries/{id}/teach/faces       face tiles to pick examples from
  GET  /v1/libraries/{id}/teach/people      people with example counts (here + other libraries)
  POST /v1/libraries/{id}/teach/examples    {face_ids, person_id | name}
  POST /v1/libraries/{id}/teach/examples/remove   {face_ids}
  POST /v1/libraries/{id}/teach/apply       re-sort against every library's examples

See core/faces/teach.py.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from mediamind.api.models import (
    TeachApplyOut,
    TeachExamplesIn,
    TeachExamplesRemoveIn,
    TeachFaceOut,
    TeachFacesOut,
    TeachPersonOut,
)
from mediamind.core.faces import teach
from mediamind.store.db import open_library_db
from mediamind.store.persons import latest_faces_scan

router = APIRouter(tags=["teach"])

# A face narrower than this share of its frame's largest face, or not among the
# frame's two largest, is treated as a background face (bystander, crowd).
BACKGROUND_WIDTH_RATIO = 0.5


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
            """SELECT p.id, p.name, COUNT(DISTINCT f.file_id) AS n FROM persons p
               LEFT JOIN faces f ON f.person_id = p.id
               WHERE p.provider_id = ? AND (p.name IS NOT NULL OR p.id IN (%s))
               GROUP BY p.id""" % ",".join(str(i) for i in here) if here else
            """SELECT p.id, p.name, COUNT(DISTINCT f.file_id) AS n FROM persons p
               LEFT JOIN faces f ON f.person_id = p.id
               WHERE p.provider_id = ? AND p.name IS NOT NULL GROUP BY p.id""",
            (provider_id,),
        ).fetchall()
    finally:
        conn.close()
    elsewhere, display = teach.pool_foreign_examples(_other_library_openers(request, library_id), provider_id)

    out, seen = [], set()
    for p in persons:
        key = teach.name_key(p["name"]) if p["name"] else None
        seen.add(key)
        out.append(TeachPersonOut(
            person_id=p["id"], name=p["name"] or "Unnamed person",
            examples_here=here.get(p["id"], 0),
            examples_elsewhere=len(elsewhere.get(key, [])) if key else 0, files=p["n"],
        ))
    for key, embs in elsewhere.items():
        if key not in seen:
            out.append(TeachPersonOut(person_id=None, name=display.get(key, key), examples_here=0,
                                      examples_elsewhere=len(embs), files=0))
    out.sort(key=lambda p: p.name.casefold())
    return out


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
