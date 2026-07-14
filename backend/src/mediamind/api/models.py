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
# Library file browser (live, filesystem-first)
# ---------------------------------------------------------------------------

class FileEntryOut(BaseModel):
    path: str    # relative to library root, forward-slash
    kind: str    # "image" | "gif" | "video" | "audio" | "other"
    size: int
    mtime: float


class LibraryFilesOut(BaseModel):
    library_id: str
    root: str    # absolute library root path (display only)
    total: int
    files: list[FileEntryOut]


# ---------------------------------------------------------------------------
# Explorer shell (whole-filesystem browsing, library-free)
# ---------------------------------------------------------------------------

class DriveOut(BaseModel):
    path: str    # e.g. "C:\\"
    label: str   # e.g. "Local Disk (C:)"


class BrowseFolderOut(BaseModel):
    name: str
    path: str            # absolute
    has_media: bool | None    # None = not yet known, checking in background
    mtime: float              # from the same stat() the attribute facts below use
    created: float | None            # epoch seconds; None if the OS can't report it
    accessed: float | None
    read_only: bool | None
    hidden: bool | None
    system: bool | None


class BrowseFileOut(BaseModel):
    name: str
    path: str            # absolute
    kind: str             # "image" | "gif" | "video" | "audio"
    size: int
    mtime: float
    created: float | None            # epoch seconds; None if the OS can't report it
    accessed: float | None
    read_only: bool | None
    hidden: bool | None
    system: bool | None


class BrowseDirOut(BaseModel):
    path: str             # absolute, the listed directory
    folders: list[BrowseFolderOut]
    files: list[BrowseFileOut]


# ---------------------------------------------------------------------------
# Explorer shell — file operations (M12 Phase B): see api/models_fs_ops.py
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Explorer shell — metadata + Quick Access (M12 Phase C)
# ---------------------------------------------------------------------------

class BrowseMetadataOut(BaseModel):
    path: str
    name: str
    kind: str              # "image" | "gif" | "video" | "audio"
    size: int
    mtime: float
    width: int | None      # None if dimensions could not be read (always None for audio)
    height: int | None
    duration_seconds: float | None   # video only; always None for image/gif/audio
    created: float | None            # epoch seconds; None if the OS can't report it
    accessed: float | None
    read_only: bool | None
    hidden: bool | None
    system: bool | None
    owner: str | None                # "DOMAIN\\user" on Windows, None if lookup fails


class FolderStatsOut(BaseModel):
    path: str
    item_count: int | None    # None = not yet known, computing in background
    total_bytes: int | None


class DiskUsageOut(BaseModel):
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int


class QuickAccessEntryOut(BaseModel):
    path: str
    name: str


class QuickAccessOut(BaseModel):
    pins: list[QuickAccessEntryOut]


class QuickAccessPinIn(BaseModel):
    path: str


class QuickAccessReorderIn(BaseModel):
    paths: list[str]  # full desired pin order


class RecentFileEntryOut(BaseModel):
    path: str
    name: str
    kind: str          # "image" | "gif" | "video" | "audio"
    size: int
    mtime: float
    opened_at: float    # epoch seconds, when MediaMind last opened it


class RecentFilesOut(BaseModel):
    files: list[RecentFileEntryOut]


class RecentFileRecordIn(BaseModel):
    path: str


class SettingsOut(BaseModel):
    recent_files_enabled: bool


class SettingsUpdateIn(BaseModel):
    recent_files_enabled: bool


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
    permanent: bool = False


class ExecuteJobIn(BaseModel):
    expected_trash_count: int
    permanent: bool = False


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


class ConfirmOut(BaseModel):
    confirmed_groups: int
    skipped_pending: int


class ResetConfigOut(BaseModel):
    cleared_dismissals: int
    restored_groups: int


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
