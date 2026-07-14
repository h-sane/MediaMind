"""Explorer shell: whole-filesystem browsing, independent of the `Library`
concept used by the scan/dedupe/faces features.

Read-only with respect to the filesystem the user browses — no `Library` is
registered, no `.mediamind` folder is created, nothing is written anywhere
the user can see. Every path comes from the caller and is validated by
`resolve_os_path` (`core/pathsafe.py`) before it ever touches the filesystem.
Quick Access (pin/unpin/reorder) and recent files (record) are the
exceptions that write anything at all, and they only ever write to
MediaMind's own app data dir, never to the browsed location itself.
"""

from __future__ import annotations

import ctypes
import mimetypes
import os
import re
import shutil
import string
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response

from mediamind.api.models import (
    BrowseDirOut,
    BrowseFileOut,
    BrowseFolderOut,
    BrowseMetadataOut,
    DiskUsageOut,
    DriveOut,
    FolderStatsOut,
    QuickAccessEntryOut,
    QuickAccessOut,
    QuickAccessPinIn,
    QuickAccessReorderIn,
    RecentFileEntryOut,
    RecentFileRecordIn,
    RecentFilesOut,
    SettingsOut,
    SettingsUpdateIn,
)
from mediamind.api.models_gallery import GalleryItemOut, GalleryResponseOut
from mediamind.api.models_search import SearchResponseOut, SearchResultOut
from mediamind.config import LIBRARY_DATA_DIRNAME
from mediamind.core.explorer_media import EXPLORER_KINDS, explorer_kind_of
from mediamind.core.file_facts import file_facts, stat_facts
from mediamind.core.folder_stats import FolderStatsIndex
from mediamind.core.gallery import DEFAULT_GALLERY_LIMIT, MAX_COLLECTED, MAX_GALLERY_LIMIT, iter_gallery_items
from mediamind.core.media_index import MediaIndex
from mediamind.core.pathsafe import resolve_os_path
from mediamind.core.quick_access import QuickAccessStore
from mediamind.core.scanner import is_noise_dir
from mediamind.core.recent import RecentFilesStore
from mediamind.core.scanner import MEDIA_KINDS, kind_of
from mediamind.core.settings import SettingsStore
from mediamind.core.search import DEFAULT_SEARCH_LIMIT, MAX_SEARCH_LIMIT, iter_search_hits
from mediamind.core.thumbnails import media_metadata, media_thumbnail_jpeg

router = APIRouter(prefix="/fs", tags=["fs"])


# ---------------------------------------------------------------------------
# Drives ("This PC")
# ---------------------------------------------------------------------------

def _windows_volume_label(letter: str) -> str:
    buf = ctypes.create_unicode_buffer(261)
    try:
        ok = ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
            f"{letter}:\\", buf, ctypes.sizeof(buf), None, None, None, None, 0
        )
    except OSError:
        ok = 0
    name = buf.value if ok else ""
    return f"{name} ({letter}:)" if name else f"Local Disk ({letter}:)"


def list_drives() -> list[DriveOut]:
    if sys.platform == "win32":
        drives = []
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if os.path.exists(root):
                drives.append(DriveOut(path=root, label=_windows_volume_label(letter)))
        return drives
    # Linux/macOS: a single root, refined later.
    return [DriveOut(path="/", label="Root")]


@router.get("/drives", response_model=list[DriveOut])
def drives() -> list[DriveOut]:
    return list_drives()


# ---------------------------------------------------------------------------
# Directory listing (single level, media-only — image/gif/video/audio)
# ---------------------------------------------------------------------------

@router.get("/list", response_model=BrowseDirOut)
def list_dir(request: Request, path: str = Query(...)):
    resolved = resolve_os_path(path)
    if resolved is None or not resolved.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    media_index: MediaIndex = request.app.state.media_index
    try:
        with os.scandir(resolved) as it:
            entries = list(it)
    except OSError:
        raise HTTPException(status_code=403, detail="Folder is not accessible")

    folders: list[BrowseFolderOut] = []
    files: list[BrowseFileOut] = []
    for entry in entries:
        try:
            if entry.is_dir(follow_symlinks=False):
                if entry.name == LIBRARY_DATA_DIRNAME or is_noise_dir(entry.name):
                    continue
                entry_path = Path(entry.path)
                status = media_index.check_full(entry_path)
                if status is not None and status.has_media is False and status.has_any_file:
                    continue  # confirmed junk: has files, but none of them media
                has_media = None if status is None else status.has_media
                dir_stat = entry.stat()
                facts = stat_facts(entry_path, dir_stat)
                folders.append(
                    BrowseFolderOut(
                        name=entry.name,
                        path=str(entry_path),
                        has_media=has_media,
                        mtime=dir_stat.st_mtime,
                        created=facts.created,
                        accessed=facts.accessed,
                        read_only=facts.read_only,
                        hidden=facts.hidden,
                        system=facts.system,
                    )
                )
            elif entry.is_file(follow_symlinks=False):
                entry_path = Path(entry.path)
                kind = explorer_kind_of(entry_path)
                if kind not in EXPLORER_KINDS:
                    continue
                stat = entry.stat()
                facts = stat_facts(entry_path, stat)
                files.append(
                    BrowseFileOut(
                        name=entry.name,
                        path=str(entry_path),
                        kind=kind,
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                        created=facts.created,
                        accessed=facts.accessed,
                        read_only=facts.read_only,
                        hidden=facts.hidden,
                        system=facts.system,
                    )
                )
        except OSError:
            continue

    folders.sort(key=lambda f: f.name.lower())
    files.sort(key=lambda f: f.name.lower())
    return BrowseDirOut(path=str(resolved), folders=folders, files=files)


# ---------------------------------------------------------------------------
# Recursive / cross-subfolder search (Phase I)
# ---------------------------------------------------------------------------

@router.get("/search", response_model=SearchResponseOut)
async def search(
    request: Request,
    path: str = Query(...),
    query: str = Query(...),
    limit: int = Query(default=DEFAULT_SEARCH_LIMIT, ge=1, le=MAX_SEARCH_LIMIT),
) -> SearchResponseOut:
    resolved = resolve_os_path(path)
    if resolved is None or not resolved.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    media_index: MediaIndex = request.app.state.media_index
    results: list[SearchResultOut] = []
    # `iter_search_hits` yields a `None` heartbeat every so often so a client
    # disconnect (query changed, component unmounted) stops the walk instead
    # of running it to completion for nothing.
    for item in iter_search_hits(resolved, query, limit, media_index=media_index):
        if item is None:
            if await request.is_disconnected():
                break
            continue
        results.append(
            SearchResultOut(
                kind=item.kind,
                name=item.name,
                path=item.path,
                media_kind=item.media_kind,
                size=item.size,
                mtime=item.mtime,
            )
        )

    return SearchResponseOut(
        path=str(resolved), query=query, results=results, truncated=len(results) >= limit
    )


# ---------------------------------------------------------------------------
# Gallery — recursive, date-sorted media timeline (Phase O)
# ---------------------------------------------------------------------------

@router.get("/gallery", response_model=GalleryResponseOut)
async def gallery(
    request: Request,
    path: str = Query(...),
    limit: int = Query(default=DEFAULT_GALLERY_LIMIT, ge=1, le=MAX_GALLERY_LIMIT),
) -> GalleryResponseOut:
    resolved = resolve_os_path(path)
    if resolved is None or not resolved.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    collected: list = []
    for item in iter_gallery_items(resolved):
        if item is None:
            if await request.is_disconnected():
                break
            continue
        collected.append(item)

    # Sorting only happens after the whole (bounded) walk finishes — the
    # generator's cap bounds work, not correctness of the eventual order.
    collected.sort(key=lambda i: i.mtime, reverse=True)
    truncated = len(collected) > limit or len(collected) >= MAX_COLLECTED
    sliced = collected[:limit]
    return GalleryResponseOut(
        path=str(resolved),
        items=[
            GalleryItemOut(name=i.name, path=i.path, media_kind=i.media_kind, size=i.size, mtime=i.mtime)
            for i in sliced
        ],
        truncated=truncated,
    )


# ---------------------------------------------------------------------------
# Thumbnail / raw file, by absolute path
# ---------------------------------------------------------------------------

@router.get("/thumbnail")
def thumbnail(
    path: str = Query(...),
    size: int = Query(default=256, ge=64, le=1024),
):
    resolved = resolve_os_path(path)
    if resolved is None or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    kind = kind_of(resolved)
    if kind not in MEDIA_KINDS:
        raise HTTPException(status_code=422, detail="Not a media file")

    data = media_thumbnail_jpeg(resolved, kind, size)
    if data is None:
        raise HTTPException(status_code=422, detail="Cannot decode file")

    return Response(content=data, media_type="image/jpeg")


@router.get("/raw")
def raw(path: str = Query(...)):
    resolved = resolve_os_path(path)
    if resolved is None or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    kind = explorer_kind_of(resolved)
    if kind not in EXPLORER_KINDS:
        raise HTTPException(status_code=422, detail="Not a media file")

    media_type, _ = mimetypes.guess_type(str(resolved))
    return FileResponse(str(resolved), media_type=media_type or "application/octet-stream")


# ---------------------------------------------------------------------------
# Metadata (preview pane)
# ---------------------------------------------------------------------------

@router.get("/metadata", response_model=BrowseMetadataOut)
def metadata(path: str = Query(...)) -> BrowseMetadataOut:
    resolved = resolve_os_path(path)
    if resolved is None or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    kind = explorer_kind_of(resolved)
    if kind not in EXPLORER_KINDS:
        raise HTTPException(status_code=422, detail="Not a media file")

    stat = resolved.stat()
    meta = media_metadata(resolved, kind)
    facts = file_facts(resolved)
    return BrowseMetadataOut(
        path=str(resolved),
        name=resolved.name,
        kind=kind,
        size=stat.st_size,
        mtime=stat.st_mtime,
        width=meta.width if meta else None,
        height=meta.height if meta else None,
        duration_seconds=meta.duration_seconds if meta else None,
        created=facts.created,
        accessed=facts.accessed,
        read_only=facts.read_only,
        hidden=facts.hidden,
        system=facts.system,
        owner=facts.owner,
    )


# ---------------------------------------------------------------------------
# Folder aggregate stats (Properties panel, multi-select) + disk usage
# ---------------------------------------------------------------------------

@router.get("/folder-stats", response_model=FolderStatsOut)
def folder_stats(request: Request, path: str = Query(...)) -> FolderStatsOut:
    resolved = resolve_os_path(path)
    if resolved is None or not resolved.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    index: FolderStatsIndex = request.app.state.folder_stats
    stats = index.check_full(resolved)
    return FolderStatsOut(
        path=str(resolved),
        item_count=None if stats is None else stats.item_count,
        total_bytes=None if stats is None else stats.total_bytes,
    )


@router.get("/disk-usage", response_model=DiskUsageOut)
def disk_usage(path: str = Query(...)) -> DiskUsageOut:
    resolved = resolve_os_path(path)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Path not found")

    try:
        usage = shutil.disk_usage(resolved)
    except OSError:
        raise HTTPException(status_code=404, detail="Cannot read disk usage for this path")
    return DiskUsageOut(
        path=str(resolved),
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
    )


# ---------------------------------------------------------------------------
# Quick Access (pinned folders)
# ---------------------------------------------------------------------------

_DRIVE_ROOT_RE = re.compile(r"^[A-Za-z]:\\?$")


def _pin_display_name(resolved: Path) -> str:
    name = resolved.name
    if name:
        return name
    # A drive root (e.g. "C:\\") has an empty basename — show its volume
    # label instead, matching the drives list.
    text = str(resolved)
    if sys.platform == "win32" and _DRIVE_ROOT_RE.match(text):
        return _windows_volume_label(text[0])
    return text


def _list_valid_pins(request: Request) -> QuickAccessOut:
    store: QuickAccessStore = request.app.state.quick_access
    entries: list[QuickAccessEntryOut] = []
    for raw_path in store.list_raw():
        resolved = resolve_os_path(raw_path)
        if resolved is None or not resolved.is_dir():
            continue  # stale pin (deleted folder/unplugged drive) — left in
            # storage untouched, just not shown; see quick_access.py's module
            # docstring for why this self-heals instead of pruning.
        entries.append(QuickAccessEntryOut(path=str(resolved), name=_pin_display_name(resolved)))
    return QuickAccessOut(pins=entries)


@router.get("/quick-access", response_model=QuickAccessOut)
def quick_access(request: Request) -> QuickAccessOut:
    return _list_valid_pins(request)


@router.post("/quick-access", response_model=QuickAccessOut)
def pin_quick_access(body: QuickAccessPinIn, request: Request) -> QuickAccessOut:
    resolved = resolve_os_path(body.path)
    if resolved is None or not resolved.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")
    store: QuickAccessStore = request.app.state.quick_access
    store.pin(str(resolved))
    return _list_valid_pins(request)


@router.delete("/quick-access", response_model=QuickAccessOut)
def unpin_quick_access(request: Request, path: str = Query(...)) -> QuickAccessOut:
    store: QuickAccessStore = request.app.state.quick_access
    store.unpin(path)
    return _list_valid_pins(request)


@router.put("/quick-access/reorder", response_model=QuickAccessOut)
def reorder_quick_access(body: QuickAccessReorderIn, request: Request) -> QuickAccessOut:
    store: QuickAccessStore = request.app.state.quick_access
    store.reorder(body.paths)
    return _list_valid_pins(request)


# ---------------------------------------------------------------------------
# Recent files (Home page, Phase N)
# ---------------------------------------------------------------------------

def _list_valid_recent(request: Request) -> RecentFilesOut:
    settings: SettingsStore = request.app.state.settings
    if not settings.recent_files_enabled:
        return RecentFilesOut(files=[])

    store: RecentFilesStore = request.app.state.recent_files
    entries: list[RecentFileEntryOut] = []
    for raw_path, opened_at in store.list_raw():
        resolved = resolve_os_path(raw_path)
        if resolved is None or not resolved.is_file():
            continue  # stale entry (deleted/moved file) — left in storage
            # untouched, just not shown; see recent.py's module docstring.
        kind = explorer_kind_of(resolved)
        if kind not in EXPLORER_KINDS:
            continue  # no longer a media file (e.g. overwritten) — skip
        try:
            stat = resolved.stat()
        except OSError:
            continue
        entries.append(
            RecentFileEntryOut(
                path=str(resolved),
                name=resolved.name,
                kind=kind,
                size=stat.st_size,
                mtime=stat.st_mtime,
                opened_at=opened_at,
            )
        )
    return RecentFilesOut(files=entries)


@router.get("/recent", response_model=RecentFilesOut)
def recent_files(request: Request) -> RecentFilesOut:
    return _list_valid_recent(request)


@router.post("/recent", response_model=RecentFilesOut)
def record_recent_file(body: RecentFileRecordIn, request: Request) -> RecentFilesOut:
    resolved = resolve_os_path(body.path)
    if resolved is None or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    kind = explorer_kind_of(resolved)
    if kind not in EXPLORER_KINDS:
        raise HTTPException(status_code=422, detail="Not a media file")
    settings: SettingsStore = request.app.state.settings
    if settings.recent_files_enabled:
        store: RecentFilesStore = request.app.state.recent_files
        store.record(str(resolved))
    return _list_valid_recent(request)


# ---------------------------------------------------------------------------
# Settings (Folder Options — Privacy)
# ---------------------------------------------------------------------------

@router.get("/settings", response_model=SettingsOut)
def get_settings(request: Request) -> SettingsOut:
    settings: SettingsStore = request.app.state.settings
    return SettingsOut(recent_files_enabled=settings.recent_files_enabled)


@router.patch("/settings", response_model=SettingsOut)
def update_settings(body: SettingsUpdateIn, request: Request) -> SettingsOut:
    settings: SettingsStore = request.app.state.settings
    enabled = settings.set_recent_files_enabled(body.recent_files_enabled)
    if not enabled:
        # Turning tracking off also clears what's already tracked — matches
        # Explorer's "Clear File Explorer history" so nothing lingers that
        # could resurface if the setting is switched back on later.
        recent_store: RecentFilesStore = request.app.state.recent_files
        recent_store.clear()
    return SettingsOut(recent_files_enabled=enabled)
