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
    pending_count: int = 0
    multi_person_count: int = 0


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


# ---------------------------------------------------------------------------
# Organize (M6)
# ---------------------------------------------------------------------------

class PlannedMoveOut(BaseModel):
    source_rel: str
    dest_folder_rel: str
    person_id: int | None
    person_name: str | None


class OrganizePreviewOut(BaseModel):
    planned: int
    by_person: dict[str, int]   # display label -> file count
    moves: list[PlannedMoveOut]


class OrganizeExecuteIn(BaseModel):
    dry_run: bool = False
    expected_planned: int | None = None  # safety guard: reject if plan size changed


class OrganizeActionOut(BaseModel):
    id: int
    kind: str
    created_at: float
    planned: int
    handled: int
    ok: bool
    dry_run: bool
    undone: bool


# ---------------------------------------------------------------------------
# Pending matches (M6)
# ---------------------------------------------------------------------------

class PendingMatchOut(BaseModel):
    id: int
    face_id: int
    person_id: int
    person_name: str
    confidence: float


class PendingDecisionItem(BaseModel):
    pending_id: int
    decision: str   # "confirmed" | "rejected"


class PendingDecisionsIn(BaseModel):
    decisions: list[PendingDecisionItem]


# ---------------------------------------------------------------------------
# Multi-person review (M6 remainder)
# ---------------------------------------------------------------------------

class PersonOptionOut(BaseModel):
    person_id: int
    person_name: str
    face_count: int
    sample_face_id: int  # first face of this person in this file (for thumbnail)


class MultiPersonFileOut(BaseModel):
    file_id: int
    path: str
    kind: str
    persons: list[PersonOptionOut]
    current_choice: int | None  # person_id from route_choices if already decided


class RouteChoiceIn(BaseModel):
    file_id: int
    person_id: int


class RouteChoicesIn(BaseModel):
    choices: list[RouteChoiceIn]
