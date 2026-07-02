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
    provider_id: str | None = None  # faces scans only


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


# ---------------------------------------------------------------------------
# Providers (M5)
# ---------------------------------------------------------------------------

class LicenseOut(BaseModel):
    name: str
    url: str
    commercial_use: bool
    summary: str


class ProviderOut(BaseModel):
    id: str
    name: str
    description: str
    license: LicenseOut
    installed: bool
    size_bytes: int
    embedding_dim: int


class ProviderDownloadIn(BaseModel):
    license_accepted: bool = False


# ---------------------------------------------------------------------------
# Persons (M5)
# ---------------------------------------------------------------------------

class PersonOut(BaseModel):
    id: int
    auto_label: str
    name: str | None
    face_count: int
    media_count: int
    sample_face_ids: list[int]


class PersonsOut(BaseModel):
    scan_id: str
    scanned_at: float | None
    provider_id: str
    persons: list[PersonOut]
    unassigned_faces: int
    no_face_files: int
    unreadable_files: int


class PersonRenameIn(BaseModel):
    name: str | None


class PersonMergeIn(BaseModel):
    source_id: int
    target_id: int


class PersonMediaItemOut(BaseModel):
    file_id: int
    path: str
    kind: str
    face_id: int
    bbox: tuple[float, float, float, float]
