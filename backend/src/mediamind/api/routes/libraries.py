"""Library management routes: register, list, unregister folders."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["libraries"])


class LibraryIn(BaseModel):
    path: str


class LibraryOut(BaseModel):
    id: str
    path: str
    name: str


@router.get("/libraries", response_model=list[LibraryOut])
def list_libraries(request: Request):
    return [LibraryOut(**lib.__dict__) for lib in request.app.state.registry.list()]


@router.post("/libraries", response_model=LibraryOut, status_code=201)
def add_library(body: LibraryIn, request: Request):
    try:
        lib = request.app.state.registry.add(Path(body.path))
    except NotADirectoryError as e:
        raise HTTPException(status_code=400, detail=f"Not a folder: {e}")
    return LibraryOut(**lib.__dict__)


@router.delete("/libraries/{library_id}", status_code=204)
def remove_library(library_id: str, request: Request):
    # Unregisters the folder from MediaMind only — never deletes user files.
    if not request.app.state.registry.remove(library_id):
        raise HTTPException(status_code=404, detail="Unknown library")
