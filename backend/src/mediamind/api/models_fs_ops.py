"""Request/response models for the Explorer shell's file operations
(new folder / rename / move / copy / delete / undo / redo / create-shortcut).

Split out of `api/models.py` (M12 Phase L) for the same reason
`models_archive.py` was split out earlier: that file was already at
CLAUDE.md's ~300-400-line size-smell threshold. Response shapes for the
batch write ops (`ExecutionReportOut`/`ManifestEntryOut`) stay in
`api/models.py` — they're shared with `models_archive.py`'s compress/extract
too, not specific to this module.
"""

from __future__ import annotations

from pydantic import BaseModel


class FsNewFolderIn(BaseModel):
    parent: str
    name: str | None = None


class FsNewFolderOut(BaseModel):
    path: str


class FsRenameIn(BaseModel):
    path: str
    new_name: str


class FsRenameOut(BaseModel):
    path: str


class FsDeleteIn(BaseModel):
    paths: list[str]
    permanent: bool = False
    dry_run: bool = False


class FsMoveIn(BaseModel):
    sources: list[str]
    dest: str
    dry_run: bool = False


class FsCopyIn(BaseModel):
    sources: list[str]
    dest: str
    dry_run: bool = False


class FsUndoOut(BaseModel):
    ok: bool
    kind: str | None
    message: str


class FsRedoOut(BaseModel):
    ok: bool
    kind: str | None
    message: str


class FsCreateShortcutIn(BaseModel):
    target: str
    dest_folder: str
    name: str | None = None


class FsCreateShortcutOut(BaseModel):
    path: str


class RecentDeletionOut(BaseModel):
    path: str
    permanent: bool  # True = gone for good; False = sent to the OS Recycle Bin
    ts: float


class RecentDeletionsOut(BaseModel):
    deletions: list[RecentDeletionOut]
