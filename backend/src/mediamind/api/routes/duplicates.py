"""Duplicate review routes: list groups, set resolutions, execute, thumbnail.

Safety-critical section — every function that touches user files goes through
safety.trash() and the manifest system. Read the inline safety comments before
editing the execute endpoint.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from mediamind.api.models import (
    ConfirmOut,
    DuplicateFileOut,
    DuplicateGroupOut,
    DuplicatesOut,
    DuplicatesSummary,
    ExecuteIn,
    ExecuteJobIn,
    ExecutionReportOut,
    JobSnapshot,
    ManifestEntryOut,
    ResetConfigOut,
    ResolutionsIn,
)
from mediamind.config import library_data_dir
from mediamind.core.dedupe import group_signature
from mediamind.core.jobs import JobContext, JobManager
from mediamind.core.libraries import LibraryRegistry
from mediamind.core.safety import ExecutionReport, new_manifest_path, recycle_bin_supported, trash
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
)

router = APIRouter(tags=["duplicates"])

# Max per-file error entries embedded directly in a job's result payload —
# broadcast over the WS to every connected client on completion, so this
# stays small even for a batch of thousands of files. Full detail always
# lives in the manifest CSV (`result["manifest_path"]`).
_MAX_RESULT_ERRORS = 50


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


def _snapshot(job) -> JobSnapshot:
    return JobSnapshot(
        id=job.id,
        library_id=job.library_id,
        type=job.type,
        state=job.state,
        phase=job.phase,
        done=job.done,
        total=job.total,
        error=job.error,
        result=job.result,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


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
# Execute (dry-run + real) — shared stat-check-then-trash logic
# ---------------------------------------------------------------------------

def _run_trash(
    library_root: Path,
    member_ids: list[int],
    rel_paths: list[str],
    dry_run: bool,
    permanent: bool,
    on_progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[ExecutionReport, list[int], list[ManifestEntryOut], list[tuple[int, Path]]]:
    """Stat-check each target then trash the ones that are actually reachable.

    Returns (report, skipped_ids, skip_entries, attempted) — `attempted` is
    the (member_id, abs_path) pairs actually handed to `trash()`, which
    callers need to work out which ids really got trashed vs. errored.
    Never touches the DB; callers persist results themselves.
    """
    paths_to_trash: list[Path] = []
    attempted: list[tuple[int, Path]] = []
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
        attempted.append((mid, abs_path))

    data_dir = library_data_dir(library_root)
    manifest_path = new_manifest_path(data_dir, "dedupe")
    report = trash(
        paths_to_trash,
        manifest_path=manifest_path,
        dry_run=dry_run,
        permanent=permanent,
        on_progress=on_progress,
        should_cancel=should_cancel,
    )
    return report, skipped_ids, skip_entries, attempted


def _trashed_ids(report: ExecutionReport, attempted: list[tuple[int, Path]]) -> list[int]:
    """Which attempted member ids actually got trashed/deleted — checked
    against report.entries directly so this is correct whether the batch ran
    to completion, hit per-file errors, or was cancelled partway through
    (paths never reached by `trash()` just have no entry at all)."""
    success_paths = {e.source for e in report.entries if e.action in ("trashed", "deleted")}
    return [mid for mid, p in attempted if str(p) in success_paths]


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

        # Safety check: expected count guards against a stale UI trashing more
        # than the user approved (Fable plan §2.4, safety rule 6).
        if len(member_ids) != body.expected_trash_count:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Expected {body.expected_trash_count} files to trash but "
                    f"server has {len(member_ids)}. Refresh and re-confirm."
                ),
            )

        report, skipped_ids, skip_entries, attempted = _run_trash(
            library_root, member_ids, rel_paths, body.dry_run, body.permanent,
        )

        if not body.dry_run:
            mark_members_trashed(conn, _trashed_ids(report, attempted))

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
# Execute as a background job (real deletion only) — the same real-delete
# work as execute_duplicates(dry_run=False), but run on a JobManager thread
# so a large batch (hundreds of files, minutes of send2trash calls) never
# blocks the request/UI. /execute above stays synchronous and unchanged for
# dry-run previews and the legacy DedupeReview screen.
# ---------------------------------------------------------------------------

def _make_execute_runner(
    library_root: Path, member_ids: list[int], rel_paths: list[str], permanent: bool
) -> Callable[[JobContext], dict]:
    def runner(ctx: JobContext) -> dict:
        ctx.report_progress(0, len(member_ids), "checking")

        report, skipped_ids, skip_entries, attempted = _run_trash(
            library_root, member_ids, rel_paths, dry_run=False, permanent=permanent,
            on_progress=lambda done, total: ctx.report_progress(done, total, "deleting"),
            should_cancel=ctx.cancelled,
        )

        conn = _open_library_db(library_root)
        try:
            mark_members_trashed(conn, _trashed_ids(report, attempted))
        finally:
            conn.close()

        errors = skip_entries + [e for e in report.entries if e.action == "error"]
        network_only = len(errors) > 0 and all(
            "network or virtual drive" in e.error for e in errors
        )

        return {
            "planned": report.planned + len(skipped_ids),
            "handled": report.handled,
            "ok": report.ok and not skipped_ids,
            "manifest_path": str(report.manifest_path) if report.manifest_path else None,
            "permanent": permanent,
            "error_count": len(errors),
            "network_errors_only": network_only,
            "errors": [
                {"source": e.source, "error": e.error} for e in errors[:_MAX_RESULT_ERRORS]
            ],
        }

    return runner


@router.post(
    "/libraries/{library_id}/duplicates/execute-job",
    response_model=JobSnapshot,
    status_code=202,
)
def start_execute_job(library_id: str, body: ExecuteJobIn, request: Request):
    jm = _job_manager(request)
    running = jm.running_for(library_id)
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"A {running.type} job is still running — wait for it to finish",
        )

    _, library_root = _get_library_and_root(request, library_id)
    conn = _open_library_db(library_root)
    try:
        trash_set = get_trash_set(conn)
    finally:
        conn.close()
    member_ids = [mid for mid, _ in trash_set]
    rel_paths = [rp for _, rp in trash_set]

    if len(member_ids) != body.expected_trash_count:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Expected {body.expected_trash_count} files to trash but "
                f"server has {len(member_ids)}. Refresh and re-confirm."
            ),
        )

    runner = _make_execute_runner(library_root, member_ids, rel_paths, body.permanent)
    job = jm.start(library_id, "dedupe-execute", runner)
    return _snapshot(job)


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
