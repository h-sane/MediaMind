"""Shared Pydantic request/response models for the MediaMind API.

Freeze this module before starting frontend work — it is the API contract
between backend and the TypeScript client.
"""

from __future__ import annotations

from typing import Any, Literal

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
    triggered_by: str = "user"  # "user" | "watcher" (Phase 8 auto-scan)


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
    auto_scan_mode: Literal["off", "libraries", "system"]
    auto_scan_enabled: bool  # computed: True iff auto_scan_mode != "off" — kept for back-compat
    active_provider_id: str | None  # None → auto-pick first installed pack


class SettingsUpdateIn(BaseModel):
    # All optional so each toggle can be PATCHed independently — only the
    # fields present in the body are applied.
    recent_files_enabled: bool | None = None
    auto_scan_mode: Literal["off", "libraries", "system"] | None = None
    auto_scan_enabled: bool | None = None
    active_provider_id: str | None = None  # "" clears to auto-pick; omit to leave unchanged


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
    guidance: str
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
    primary_folder_path: str | None = None


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


class RecurringUnnamedOut(BaseModel):
    """ADR-0001 recurring-unnamed-faces surface. `total_unnamed` counts every
    unnamed cluster regardless of the floor, so the UI can show how many
    singletons sit below `min_appearances` behind a "show all" hatch."""
    persons: list[PersonOut]
    min_appearances: int
    total_unnamed: int


class GroupOut(BaseModel):
    """A node in the person-centric People tree (ADR-0007/0008). Groups mirror
    folder nesting and hold only sub-Groups and Persons — never media directly.
    `path` is posix, library-relative ("" is the root); `total_persons` is the
    transitive count for the "show everything below" toggle."""
    path: str
    name: str
    subgroups: list["GroupOut"] = []
    persons: list[PersonOut] = []
    total_persons: int = 0


class PeopleTreeOut(BaseModel):
    scan_id: str
    scanned_at: float | None
    root: GroupOut


class PersonRenameIn(BaseModel):
    name: str | None


class PersonMergeIn(BaseModel):
    source_id: int
    target_id: int


class PersonPrimaryFolderIn(BaseModel):
    path: str | None


class FaceReassignIn(BaseModel):
    person_id: int


class MergeSuggestionOut(BaseModel):
    person_a: int
    person_b: int
    similarity: float


class MergeSuggestionDismissIn(BaseModel):
    person_a_id: int
    person_b_id: int


class PersonMediaItemOut(BaseModel):
    file_id: int
    path: str          # library-relative (posix)
    abs_path: str      # absolute on-disk path, so the Explorer content grid can browse it library-free
    kind: str
    # Placement-attributed files (ADR-0010) have no matching face for this
    # person, so face_id/bbox are null; `via_placement` flags them so the view
    # can mark that they're here because they sit in the person's folder.
    face_id: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    via_placement: bool = False


# ---------------------------------------------------------------------------
# Organize (M6)
# ---------------------------------------------------------------------------

class PlannedMoveOut(BaseModel):
    source_rel: str
    dest_folder_rel: str
    person_id: int | None
    person_name: str | None
    reason: str


class OrganizePreviewOut(BaseModel):
    planned: int
    by_person: dict[str, int]   # display label -> file count
    moves: list[PlannedMoveOut]
    plan_hash: str  # re-verified by execute against a freshly-rebuilt plan
    stayed_unrecognized: int  # files with faces that stay in place, nobody named


class OrganizeExecuteIn(BaseModel):
    dry_run: bool = False
    expected_planned: int | None = None  # safety guard: reject if plan size changed
    expected_plan_hash: str | None = None  # content guard: reject if plan contents changed
    excluded_sources: list[str] = []  # source_rel values the user unchecked in the review UI
    mode: str = "move"  # "move" (organize, changes originals) | "copy" (export, leaves originals)
    group_scope: str = "prominent"  # "prominent" (dominant person) | "all" (copy into every person's folder)
    person_id: int | None = None  # scope to one person's primary folder; server resolves the destination


class OrganizeActionOut(BaseModel):
    id: int
    kind: str
    created_at: float
    planned: int
    handled: int
    ok: bool
    dry_run: bool
    undone: bool


class DuplicateLocationOut(BaseModel):
    path: str            # library-relative
    kind: str             # image | video | gif | ...
    is_source: bool       # the original vs. an export copy


class DuplicateLocationGroupOut(BaseModel):
    source: str           # library-relative path of the original (group key)
    locations: list[DuplicateLocationOut]


class DuplicateLocationsPruneIn(BaseModel):
    paths: list[str]      # library-relative paths to trash
    dry_run: bool = False
    permanent: bool = False


# ---------------------------------------------------------------------------
# Pending matches (M6)
# ---------------------------------------------------------------------------

class PendingMatchOut(BaseModel):
    id: int
    face_id: int
    person_id: int
    person_name: str
    confidence: float
    path: str          # library-relative (posix) — the candidate's source file
    abs_path: str       # absolute on-disk path, so PendingReviewPage can browse it library-free
    kind: str


class PendingDecisionItem(BaseModel):
    pending_id: int
    decision: str   # "confirmed" | "rejected"
    reassign_to_person_id: int | None = None  # "confirmed" only — assign to a different person than suggested


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


# ---------------------------------------------------------------------------
# Folder bindings (Phase B — respect pre-existing person/group folders)
# ---------------------------------------------------------------------------

class BindingSuggestionOut(BaseModel):
    id: int
    folder_rel: str
    kind: str  # "person" | "group"
    file_count: int
    coverage: float
    person_ids: list[int]
    person_names: list[str]
    outlier_file_ids: list[int]
    move_count: int
    status: str
    created_at: float


class BindingSuggestionsOut(BaseModel):
    provider_id: str
    suggestions: list[BindingSuggestionOut]


class RefreshSuggestionsOut(BaseModel):
    suggested: int
    removed_stale: int


class OutlierFileOut(BaseModel):
    file_id: int
    path: str
    kind: str
    accepted: bool
    likely_person_name: str | None = None


class BindingOut(BaseModel):
    id: int
    folder_rel: str
    kind: str
    person_ids: list[int]
    person_names: list[str]
    accepted_outlier_file_ids: list[int]
    outliers: list[OutlierFileOut]
    created_at: float


class BindingsOut(BaseModel):
    provider_id: str
    bindings: list[BindingOut]


class MovePreviewItemOut(BaseModel):
    file_id: int
    source_rel: str
    dest_folder_rel: str
    kind: str


class SuggestionMergePreviewOut(BaseModel):
    suggestion_id: int
    folder_rel: str
    person_names: list[str]
    leaf_name: str
    move_count: int
    moves: list[MovePreviewItemOut]
    folder_outliers: list[OutlierFileOut]
    duplicate_file_ids: list[int] = []


class ReassignItemIn(BaseModel):
    file_id: int
    dest_folder_rel: str


class SuggestionMergeIn(BaseModel):
    dry_run: bool = False
    expected_move_count: int | None = None  # safety guard: reject if plan size changed
    excluded_file_ids: list[int] = []
    reassignments: list[ReassignItemIn] = []
    confirmed_outlier_file_ids: list[int] = []  # in-folder outliers user confirmed ARE this person
    rejected_outlier_file_ids: list[int] = []  # in-folder outliers user confirmed are NOT this person


class AcceptOutliersIn(BaseModel):
    file_ids: list[int]


# ---------------------------------------------------------------------------
# Faces pre-scan folder prep (recommend Unsorted/ before scanning)
# ---------------------------------------------------------------------------

class FacesPrepOut(BaseModel):
    has_subfolders: bool
    top_level_loose_count: int
    named_subfolder_count: int
    already_has_unsorted: bool
    recommend_unsorted: bool


class CreateUnsortedIn(BaseModel):
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Materialize a not-yet-foldered person into a brand-new sibling folder
# ---------------------------------------------------------------------------

class MaterializeCandidateOut(BaseModel):
    file_id: int
    path: str
    kind: str


class MaterializePreviewOut(BaseModel):
    person_id: int
    candidates: list[MaterializeCandidateOut]


class MaterializeIn(BaseModel):
    name: str
    dry_run: bool = False
    expected_move_count: int | None = None  # safety guard: reject if plan size changed
    excluded_file_ids: list[int] = []
    reassignments: list[ReassignItemIn] = []


# ---------------------------------------------------------------------------
# Global (cross-library) people
# ---------------------------------------------------------------------------

class GlobalPersonMemberOut(BaseModel):
    library_id: str
    library_name: str
    library_path: str
    local_person_id: int
    provider_id: str
    name: str | None
    face_count: int
    media_count: int
    sample_face_ids: list[int]


class GlobalPersonOut(BaseModel):
    id: int
    name: str
    primary_location: str | None
    media_count: int
    members: list[GlobalPersonMemberOut]


class GlobalPersonCreateIn(BaseModel):
    name: str


class GlobalPersonRenameIn(BaseModel):
    name: str


class GlobalPersonLinkIn(BaseModel):
    library_id: str
    local_person_id: int


class GlobalPersonPrimaryLocationIn(BaseModel):
    path: str | None


class GlobalLinkSuggestionOut(BaseModel):
    library_id_a: str
    local_person_id_a: int
    library_id_b: str
    local_person_id_b: int
    similarity: float


class GlobalMoveSuggestionItemOut(BaseModel):
    library_id: str
    file_id: int
    abs_path: str
    content_hash: str | None


class GlobalMoveSuggestionGroupOut(BaseModel):
    global_person_id: int
    global_person_name: str
    primary_location: str
    items: list[GlobalMoveSuggestionItemOut]


class GlobalMoveSuggestionDismissIn(BaseModel):
    global_person_id: int
    content_hash: str


class GlobalMoveExecuteItemIn(BaseModel):
    global_person_id: int
    library_id: str
    file_id: int


class GlobalMoveExecuteIn(BaseModel):
    items: list[GlobalMoveExecuteItemIn]
    dry_run: bool = False
    expected_count: int | None = None
    expected_plan_hash: str | None = None


class GlobalMoveExecuteOut(ExecutionReportOut):
    """Same shape as ExecutionReportOut plus the resolved batch's plan hash
    — a dry-run call returns this so the client can pass it back as
    expected_plan_hash on the follow-up real execute, same pattern as
    organize.py's preview -> execute."""

    plan_hash: str


class GlobalLinkSuggestionPairIn(BaseModel):
    """Identifies a cross-library suggestion pair — same shape used by both
    the dismiss ("not the same person") and link (accept) actions."""

    library_id_a: str
    local_person_id_a: int
    library_id_b: str
    local_person_id_b: int


class GlobalMoveUndoInfoOut(BaseModel):
    """Whether the last cross-library move can be undone, for the UI to
    decide if it shows an "Undo last move" affordance."""

    available: bool
    file_count: int
    destinations: list[str]


class GlobalMoveUndoOut(ExecutionReportOut):
    """Result of reversing the last move batch — same shape as a move's own
    report (no plan_hash: undo replays a fixed manifest, it isn't re-planned)."""


# ---------------------------------------------------------------------------
# Folder faces (Explorer folder icons show the named people inside)
# ---------------------------------------------------------------------------

class FolderPersonOut(BaseModel):
    person_id: int
    name: str
    sample_face_id: int


class FolderFacesOut(BaseModel):
    """Named people detected inside a folder. `library_id` is null when the
    folder is outside any registered/scanned library — the caller then shows
    the plain folder icon. `total_persons` is the true distinct count so the
    UI can render "+N" beyond the capped `persons` list."""

    library_id: str | None
    persons: list[FolderPersonOut]
    total_persons: int
