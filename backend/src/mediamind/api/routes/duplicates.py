"""Duplicate review routes: list groups, set resolutions, execute, thumbnail.

Safety-critical section — every function that touches user files goes through
safety.trash() and the manifest system. Read the inline safety comments before
editing the execute endpoint.
"""

from __future__ import annotations

import io
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from mediamind.api.models import (
    ConfirmOut,
    DuplicateFileOut,
    DuplicateGroupOut,
    DuplicatesOut,
    DuplicatesSummary,
    ExecuteIn,
    ExecutionReportOut,
    ManifestEntryOut,
    ResetConfigOut,
    ResolutionsIn,
)
from mediamind.config import library_data_dir
from mediamind.core.dedupe import group_signature
from mediamind.core.jobs import JobManager
from mediamind.core.libraries import LibraryRegistry
from mediamind.core.safety import new_manifest_path, recycle_bin_supported, trash
from mediamind.store.db import library_db_path, open_db
from mediamind.store.duplicates import (
    add_dismissals,
    clear_dismissals,
    get_trash_set,
    load_scan,
    mark_groups_ignored,
    mark_members_trashed,
    unignore_all_groups,
    upsert_resolution,
    validate_no_empty_groups,
)

router = APIRouter(tags=["duplicates"])


def _registry(request: Request) -> LibraryRegistry:
    return request.app.state.registry


def _job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


def _get_library_and_root(request: Request, library_id: str) -> tuple:
    lib = _registry(request).get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    return lib, Path(lib.path)


def _open_library_db(library_root: Path):
    data_dir = library_data_dir(library_root)
    return open_db(library_db_path(data_dir))


# ---------------------------------------------------------------------------
# List duplicates
# ---------------------------------------------------------------------------

@router.get("/libraries/{library_id}/duplicates", response_model=DuplicatesOut)
def list_duplicates(library_id: str, request: Request):
    _, library_root = _get_library_and_root(request, library_id)
    conn = _open_library_db(library_root)
    try:
        scan = load_scan(conn)
    finally:
        conn.close()

    if scan is None:
        raise HTTPException(status_code=404, detail="No duplicate scan found — run a scan first")

    groups = [
        DuplicateGroupOut(
            id=g.id,
            match=g.match,
            files=[
                DuplicateFileOut(
                    id=m.id,
                    path=m.path,
                    size=m.size,
                    mtime=m.mtime,
                    kind=m.kind,
                    width=m.width,
                    height=m.height,
                    suggested_keep=m.suggested_keep,
                    resolution=m.resolution,
                )
                for m in g.files
                # Already-executed files are gone from disk — never show them
                # again, or a re-click on a "gone" tile reports a confusing
                # "already deleted" error from the execute endpoint.
                if m.resolution != "trashed"
            ],
        )
        for g in scan.groups
    ]
    # A group needs 2+ files to still be a "duplicate" — once execute() has
    # trashed enough members that only the keeper (or nothing) is left, the
    # group is resolved and drops out of the review list entirely.
    groups = [g for g in groups if len(g.files) >= 2]

    summary = DuplicatesSummary(
        groups=len(groups),
        files=sum(len(g.files) for g in groups),
        reclaimable_bytes=sum(f.size for g in groups for f in g.files if not f.suggested_keep),
    )

    return DuplicatesOut(
        scan_id=scan.id,
        scanned_at=scan.scanned_at,
        summary=summary,
        groups=groups,
    )


# ---------------------------------------------------------------------------
# Recycle Bin support check (B7 — pre-emptive, so the delete confirm dialog
# never has to try-then-fall-back)
# ---------------------------------------------------------------------------

@router.get("/libraries/{library_id}/duplicates/recycle-bin-check")
def recycle_bin_check(library_id: str, request: Request):
    """Whether the library's drive supports the Recycle Bin, checked once for
    the library root — every execute_duplicates() target is `library_root /
    rel` (see below), so all trash targets share the root's volume."""
    _, library_root = _get_library_and_root(request, library_id)
    return {"recycle_bin_supported": recycle_bin_supported(library_root)}


# ---------------------------------------------------------------------------
# Set resolutions
# ---------------------------------------------------------------------------

@router.post("/libraries/{library_id}/duplicates/resolutions")
def set_resolutions(library_id: str, body: ResolutionsIn, request: Request):
    _, library_root = _get_library_and_root(request, library_id)

    valid_actions = {"keep", "trash"}
    for item in body.resolutions:
        if item.action not in valid_actions:
            raise HTTPException(status_code=422, detail=f"Invalid action '{item.action}'")

    conn = _open_library_db(library_root)
    try:
        updated = 0
        for item in body.resolutions:
            if upsert_resolution(conn, item.file_id, item.action):
                updated += 1

        bad_groups = validate_no_empty_groups(conn)
        if bad_groups:
            # Roll back the entire batch — don't commit a state with no keeper.
            conn.rollback()
            raise HTTPException(
                status_code=422,
                detail=f"Resolutions would leave {len(bad_groups)} group(s) with no keeper",
            )
    finally:
        conn.close()

    return {"updated": updated}


# ---------------------------------------------------------------------------
# Confirm (Save configuration — dismiss reviewed groups across rescans)
# ---------------------------------------------------------------------------

@router.post("/libraries/{library_id}/duplicates/confirm", response_model=ConfirmOut)
def confirm_duplicates(library_id: str, request: Request):
    """Record every fully-reviewed group's member signature so a future
    rescan of this library won't surface it again, unless its membership
    changes (see core.dedupe.group_signature and routes/scans.py's dedupe
    runner, which filters against these signatures)."""
    running = _job_manager(request).running_for(library_id)
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"A {running.type} scan is still running — wait for it to finish",
        )

    _, library_root = _get_library_and_root(request, library_id)
    conn = _open_library_db(library_root)
    try:
        scan = load_scan(conn)
        if scan is None:
            raise HTTPException(status_code=404, detail="No duplicate scan found — run a scan first")

        dismissal_rows: list[tuple[str, str, int]] = []
        group_ids: list[int] = []
        skipped_pending = 0

        for g in scan.groups:
            pending = [m for m in g.files if m.resolution == "trash"]
            if pending:
                # Unexecuted deletions — those files are still on disk, so
                # dismissing now would either be undone by the next scan or
                # wrongly hide files the user meant to delete. Execute first.
                skipped_pending += 1
                continue

            survivors = [m for m in g.files if m.resolution != "trashed"]
            if len(survivors) < 2:
                continue  # already resolved down to a single keeper

            sig = group_signature([m.content_hash for m in survivors])
            dismissal_rows.append((sig, g.match, len(survivors)))
            group_ids.append(g.id)

        add_dismissals(conn, dismissal_rows)
        mark_groups_ignored(conn, group_ids)
    finally:
        conn.close()

    return ConfirmOut(confirmed_groups=len(group_ids), skipped_pending=skipped_pending)


# ---------------------------------------------------------------------------
# Reset configuration (undo every "Save configuration" for this library)
# ---------------------------------------------------------------------------

@router.delete("/libraries/{library_id}/duplicates/dismissals", response_model=ResetConfigOut)
def reset_dismissals(library_id: str, request: Request):
    """Clear every dismissal signature recorded via confirm_duplicates() and
    un-hide the groups they were hiding, so a user who saved the wrong
    configuration (or just wants a clean slate) can start review over —
    takes effect immediately, no rescan required."""
    running = _job_manager(request).running_for(library_id)
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"A {running.type} scan is still running — wait for it to finish",
        )

    _, library_root = _get_library_and_root(request, library_id)
    conn = _open_library_db(library_root)
    try:
        cleared = clear_dismissals(conn)
        restored = unignore_all_groups(conn)
    finally:
        conn.close()

    return ResetConfigOut(cleared_dismissals=cleared, restored_groups=restored)


# ---------------------------------------------------------------------------
# Execute (dry-run + real)
# ---------------------------------------------------------------------------

@router.post("/libraries/{library_id}/duplicates/execute", response_model=ExecutionReportOut)
def execute_duplicates(library_id: str, body: ExecuteIn, request: Request):
    running = _job_manager(request).running_for(library_id)
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"A {running.type} scan is still running — wait for it to finish",
        )

    _, library_root = _get_library_and_root(request, library_id)
    conn = _open_library_db(library_root)
    try:
        trash_set = get_trash_set(conn)
        member_ids = [mid for mid, _ in trash_set]
        rel_paths = [rp for _, rp in trash_set]

        # Safety check 1: expected count guards against a stale UI trashing more
        # than the user approved (Fable plan §2.4, safety rule 6).
        if len(member_ids) != body.expected_trash_count:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Expected {body.expected_trash_count} files to trash but "
                    f"server has {len(member_ids)}. Refresh and re-confirm."
                ),
            )

        # Safety check 2: no group may be left with zero keepers.
        bad_groups = validate_no_empty_groups(conn)
        if bad_groups:
            raise HTTPException(
                status_code=422,
                detail=f"{len(bad_groups)} group(s) would have no keeper after execution",
            )

        # Safety check 3: files with resolution=NULL are never in the trash set
        # (get_trash_set only returns resolution='trash' rows), so the invariant
        # is guaranteed by the query — no additional check needed here.

        # Build absolute paths and verify each file's stat before touching anything.
        paths_to_trash: list[Path] = []
        skipped_ids: list[int] = []
        skip_entries: list[ManifestEntryOut] = []

        for mid, rel in zip(member_ids, rel_paths):
            abs_path = library_root / rel
            try:
                stat = abs_path.stat()
                _ = stat.st_size  # ensures the file is reachable
            except OSError:
                # Vanished or inaccessible — skip with an error entry, never trash blind.
                skipped_ids.append(mid)
                skip_entries.append(ManifestEntryOut(
                    source=str(abs_path),
                    action="error",
                    destination="",
                    error="file not found or inaccessible at execute time",
                ))
                continue
            paths_to_trash.append(abs_path)

        data_dir = library_data_dir(library_root)
        manifest_path = new_manifest_path(data_dir, "dedupe")
        report = trash(
            paths_to_trash,
            manifest_path=manifest_path,
            dry_run=body.dry_run,
            permanent=body.permanent,
        )

        if not body.dry_run:
            trashed_ids = [
                mid
                for mid, rel in zip(member_ids, rel_paths)
                if library_root / rel in paths_to_trash
                and not any(e.source == str(library_root / rel) and e.action == "error" for e in report.errors)
            ]
            mark_members_trashed(conn, trashed_ids)

    finally:
        conn.close()

    all_entries = skip_entries + [
        ManifestEntryOut(source=e.source, action=e.action, destination=e.destination, error=e.error)
        for e in report.entries
    ]

    return ExecutionReportOut(
        planned=report.planned + len(skipped_ids),
        handled=report.handled,
        ok=report.ok and not skipped_ids,
        dry_run=body.dry_run,
        manifest_path=str(report.manifest_path) if report.manifest_path else None,
        entries=all_entries,
    )


# ---------------------------------------------------------------------------
# Thumbnail (B7)
# ---------------------------------------------------------------------------

@router.get("/libraries/{library_id}/duplicates/files/{member_id}/thumbnail")
def get_thumbnail(
    library_id: str,
    member_id: int,
    request: Request,
    size: int = Query(default=256, ge=64, le=1024),
):
    """Return a JPEG thumbnail for a duplicate_members row.

    Keyed by row id (not by path) so the endpoint cannot be used to read
    arbitrary files — only files that were part of a dedupe scan are accessible.
    Delegates to `core.thumbnails.media_thumbnail_jpeg`, the same decode chain
    Explorer's own file thumbnails use, so video/GIF duplicates (not just
    images) get a real preview frame instead of a permanent blank tile.
    """
    _, library_root = _get_library_and_root(request, library_id)
    conn = _open_library_db(library_root)
    try:
        row = conn.execute(
            "SELECT path, kind FROM duplicate_members WHERE id = ?", (member_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Unknown file id")

    abs_path = library_root / row["path"]

    from mediamind.core.thumbnails import media_thumbnail_jpeg

    jpeg_bytes = media_thumbnail_jpeg(abs_path, row["kind"] or "image", size)
    if jpeg_bytes is None:
        raise HTTPException(status_code=422, detail="Cannot decode file")

    return StreamingResponse(io.BytesIO(jpeg_bytes), media_type="image/jpeg")
