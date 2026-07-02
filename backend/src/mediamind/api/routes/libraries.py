"""Library management routes: register, list, unregister folders."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mediamind.core.libraries import LibraryRegistry

router = APIRouter(tags=["libraries"])
_registry: LibraryRegistry | None = None


def get_registry() -> LibraryRegistry:
    global _registry
    if _registry is None:
        _registry = LibraryRegistry()
    return _registry


class LibraryIn(BaseModel):
    path: str


class LibraryOut(BaseModel):
    id: str
    path: str
    name: str


@router.get("/libraries", response_model=list[LibraryOut])
def list_libraries():
    return [LibraryOut(**lib.__dict__) for lib in get_registry().list()]


@router.post("/libraries", response_model=LibraryOut, status_code=201)
def add_library(body: LibraryIn):
    try:
        lib = get_registry().add(Path(body.path))
    except NotADirectoryError as e:
        raise HTTPException(status_code=400, detail=f"Not a folder: {e}")
    return LibraryOut(**lib.__dict__)


@router.delete("/libraries/{library_id}", status_code=204)
def remove_library(library_id: str):
    # Unregisters the folder from MediaMind only — never deletes user files.
    if not get_registry().remove(library_id):
        raise HTTPException(status_code=404, detail="Unknown library")
