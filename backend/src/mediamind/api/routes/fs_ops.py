"""Explorer shell: file operations (new folder / rename / move / copy /
delete / undo), independent of the `Library` concept.

Every path arrives as a raw string and must be checked for symlinks *before*
`resolve_os_path` runs — `resolve_os_path` follows a symlink to its real
target, so by the time a resolved `Path` comes back there is no way to tell
it was ever a link. Symlinks are rejected outright (422) rather than given
special-cased handling — the safer, simpler choice for a first pass; revisit
if a real workflow needs it.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from mediamind.api.models import ExecutionReportOut, ManifestEntryOut
from mediamind.api.models_archive import FsCompressIn, FsExtractIn
from mediamind.api.models_fs_ops import (
    FsCopyIn,
    FsCreateShortcutIn,
    FsCreateShortcutOut,
    FsDeleteIn,
    FsMoveIn,
    FsNewFolderIn,
    FsNewFolderOut,
    FsRedoOut,
    FsRenameIn,
    FsRenameOut,
    FsUndoOut,
    RecentDeletionOut,
    RecentDeletionsOut,
)
from mediamind.core import archive, fsops, oplog
from mediamind.core.fsops import FsNameCollisionError, FsOpError
from mediamind.core.pathsafe import resolve_os_path

router = APIRouter(prefix="/fs", tags=["fs-ops"])


def _reject_symlink(raw: str) -> None:
    if os.path.islink(raw):
        raise HTTPException(status_code=422, detail="Symlinks are not supported")


def _resolve_dir(raw: str) -> Path:
    _reject_symlink(raw)
    resolved = resolve_os_path(raw)
    if resolved is None or not resolved.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")
    return resolved


def _resolve_existing(raw: str) -> Path:
    _reject_symlink(raw)
    resolved = resolve_os_path(raw)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Path not found")
    return resolved


def _report_out(report, dry_run: bool) -> ExecutionReportOut:
    return ExecutionReportOut(
        planned=report.planned,
        handled=report.handled,
        ok=report.ok,
        dry_run=dry_run,
        manifest_path=str(report.manifest_path) if report.manifest_path else None,
        entries=[
            ManifestEntryOut(source=e.source, action=e.action, destination=e.destination, error=e.error)
            for e in report.entries
        ],
    )


@router.post("/new-folder", response_model=FsNewFolderOut)
def new_folder(body: FsNewFolderIn):
    parent = _resolve_dir(body.parent)
    try:
        path = fsops.new_folder(parent, body.name)
    except FsOpError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return FsNewFolderOut(path=str(path))


@router.post("/rename", response_model=FsRenameOut)
def rename(body: FsRenameIn):
    path = _resolve_existing(body.path)
    try:
        new_path = fsops.rename(path, body.new_name)
    except FsNameCollisionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except FsOpError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return FsRenameOut(path=str(new_path))


@router.post("/delete", response_model=ExecutionReportOut)
def delete(body: FsDeleteIn):
    if not body.paths:
        raise HTTPException(status_code=422, detail="No paths given")
    paths = [_resolve_existing(p) for p in body.paths]
    report = fsops.delete_entries(paths, permanent=body.permanent, dry_run=body.dry_run)
    return _report_out(report, body.dry_run)


@router.post("/move", response_model=ExecutionReportOut)
def move(body: FsMoveIn):
    if not body.sources:
        raise HTTPException(status_code=422, detail="No sources given")
    dest = _resolve_dir(body.dest)
    sources = [_resolve_existing(p) for p in body.sources]
    report = fsops.move_entries(sources, dest, dry_run=body.dry_run)
    return _report_out(report, body.dry_run)


@router.post("/copy", response_model=ExecutionReportOut)
def copy(body: FsCopyIn):
    if not body.sources:
        raise HTTPException(status_code=422, detail="No sources given")
    dest = _resolve_dir(body.dest)
    sources = [_resolve_existing(p) for p in body.sources]
    report = fsops.copy_entries(sources, dest, dry_run=body.dry_run)
    return _report_out(report, body.dry_run)


@router.post("/undo", response_model=FsUndoOut)
def undo():
    result = oplog.undo_last()
    return FsUndoOut(ok=result.ok, kind=result.kind, message=result.message)


@router.post("/redo", response_model=FsRedoOut)
def redo():
    result = oplog.redo_last()
    return FsRedoOut(ok=result.ok, kind=result.kind, message=result.message)


@router.get("/recent-deletions", response_model=RecentDeletionsOut)
def recent_deletions():
    """Read-only history for the "Recent deletions" panel (Phase P item 4) —
    see `core/oplog.py::list_deletions`'s docstring for why this never
    attempts to restore anything itself."""
    return RecentDeletionsOut(
        deletions=[
            RecentDeletionOut(path=d.path, permanent=d.permanent, ts=d.ts)
            for d in oplog.list_deletions()
        ]
    )


@router.post("/create-shortcut", response_model=FsCreateShortcutOut)
def create_shortcut(body: FsCreateShortcutIn):
    target = _resolve_existing(body.target)
    dest_folder = _resolve_dir(body.dest_folder)
    try:
        path = fsops.create_shortcut(target, dest_folder, body.name)
    except FsOpError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return FsCreateShortcutOut(path=str(path))


@router.post("/compress", response_model=ExecutionReportOut)
def compress(body: FsCompressIn):
    if not body.paths:
        raise HTTPException(status_code=422, detail="No paths given")
    sources = [_resolve_existing(p) for p in body.paths]

    dest_raw = Path(body.dest)
    parent = _resolve_dir(str(dest_raw.parent))
    try:
        name = fsops.validate_leaf_name(dest_raw.name)
    except FsOpError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    report = archive.compress(sources, parent / name, dry_run=body.dry_run)
    return _report_out(report, body.dry_run)


@router.post("/extract", response_model=ExecutionReportOut)
def extract(body: FsExtractIn):
    zip_path = _resolve_existing(body.zip_path)
    if zip_path.suffix.lower() != ".zip":
        raise HTTPException(status_code=422, detail="Not a .zip file")

    dest_raw = Path(body.dest)
    parent = _resolve_dir(str(dest_raw.parent))
    try:
        name = fsops.validate_leaf_name(dest_raw.name)
    except FsOpError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    report = archive.extract(zip_path, parent / name, dry_run=body.dry_run)
    return _report_out(report, body.dry_run)
