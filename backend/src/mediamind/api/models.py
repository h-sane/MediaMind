"""Shared Pydantic request/response models for the MediaMind API.

Freeze this module before starting frontend work — it is the API contract
between backend and the TypeScript client.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Scan jobs
# ---------------------------------------------------------------------------

class JobSnapshot(BaseModel):
    id: str
    library_id: str
    type: str
    state: str  # queued | running | succeeded | failed | cancelled
    phase: str
    done: int
    total: int
    error: str
    result: dict[str, Any] | None
    created_at: float
    finished_at: float | None


class ScanIn(BaseModel):
    type: str = "dedupe"
    near_threshold: int = 5


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------

class DuplicateFileOut(BaseModel):
    id: int
    path: str        # relative to library root, forward-slash
    size: int
    mtime: float
    kind: str
    width: int
    height: int
    suggested_keep: bool
    resolution: str | None  # None | "keep" | "trash" | "trashed"


class DuplicateGroupOut(BaseModel):
    id: int
    match: str       # "exact" | "near"
    files: list[DuplicateFileOut]


class DuplicatesSummary(BaseModel):
    groups: int
    files: int
    reclaimable_bytes: int


class DuplicatesOut(BaseModel):
    scan_id: str
    scanned_at: float | None
    summary: DuplicatesSummary
    groups: list[DuplicateGroupOut]


# ---------------------------------------------------------------------------
# Resolutions & execution
# ---------------------------------------------------------------------------

class ResolutionItem(BaseModel):
    file_id: int
    action: str  # "keep" | "trash"


class ResolutionsIn(BaseModel):
    resolutions: list[ResolutionItem]


class ExecuteIn(BaseModel):
    dry_run: bool = False
    expected_trash_count: int


class ManifestEntryOut(BaseModel):
    source: str
    action: str
    destination: str
    error: str


class ExecutionReportOut(BaseModel):
    planned: int
    handled: int
    ok: bool
    dry_run: bool
    manifest_path: str | None
    entries: list[ManifestEntryOut]
