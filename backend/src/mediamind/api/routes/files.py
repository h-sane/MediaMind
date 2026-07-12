"""Live library file browser: list every file, thumbnail any media file.

Filesystem-first by design — both endpoints walk/read the real folder on
every request. No database rows, no hashing, no writes of any kind, so they
are always fresh and safe to call at any time, including while a scan job is
running for the same library.

Security note: the thumbnail endpoint takes a user-controlled relative path.
`_resolve_in_library` is the only way a path is turned into a filesystem
location — it rejects absolute paths, traversal (`..`), symlink escapes, and
MediaMind's own `.mediamind` data folder. Do not bypass it.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response

from mediamind.api.models import FileEntryOut, LibraryFilesOut
from mediamind.config import LIBRARY_DATA_DIRNAME
from mediamind.core.explorer_media import EXPLORER_KINDS, explorer_kind_of
from mediamind.core.libraries import LibraryRegistry
from mediamind.core.scanner import MEDIA_KINDS, kind_of, scan_folder
from mediamind.core.thumbnails import media_thumbnail_jpeg

router = APIRouter(tags=["files"])


def _registry(request: Request) -> LibraryRegistry:
    return request.app.state.registry


def _get_library_and_root(request: Request, library_id: str) -> tuple:
    lib = _registry(request).get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="Unknown library")
    return lib, Path(lib.path)


def _resolve_in_library(library_root: Path, rel: str) -> Path | None:
    """Resolve a user-supplied relative path strictly inside the library.

    Returns None for anything unsafe: absolute paths (incl. drive-letter and
    UNC forms), `..` traversal, symlinks that escape the root, paths inside
    the `.mediamind` data folder, or malformed paths.
    """
    if not rel or rel.startswith(("/", "\\")):
        return None
    try:
        candidate = Path(rel)
        if candidate.is_absolute() or candidate.drive:
            return None
        root = library_root.resolve()
        abs_path = (root / candidate).resolve()
        if not abs_path.is_relative_to(root):
            return None
        if LIBRARY_DATA_DIRNAME in abs_path.relative_to(root).parts:
            return None
        return abs_path
    except (OSError, ValueError):
        # Malformed path (e.g. embedded NUL) — treat as not found.
        return None


# ---------------------------------------------------------------------------
# List files (live walk — no DB, no hashing)
# ---------------------------------------------------------------------------

@router.get("/libraries/{library_id}/files", response_model=LibraryFilesOut)
def list_files(library_id: str, request: Request):
    """Every file currently in the library, straight from the filesystem.

    Read-only and always fresh: reflects the folder as it is right now, not
    as it was at the last scan. `.mediamind/` is excluded (scan_folder).
    """
    lib, library_root = _get_library_and_root(request, library_id)
    root = library_root.resolve()
    files = [
        FileEntryOut(
            path=f.path.relative_to(root).as_posix(),
            kind=explorer_kind_of(f.path),
            size=f.size,
            mtime=f.mtime,
        )
        for f in scan_folder(library_root)
    ]
    return LibraryFilesOut(library_id=lib.id, root=lib.path, total=len(files), files=files)


# ---------------------------------------------------------------------------
# Thumbnail by path (works without any prior scan)
# ---------------------------------------------------------------------------

@router.get("/libraries/{library_id}/files/thumbnail")
def file_thumbnail(
    library_id: str,
    request: Request,
    path: str = Query(..., description="File path relative to the library root"),
    size: int = Query(default=256, ge=64, le=1024),
):
    """JPEG thumbnail of any image/gif/video file in the library, by relative path.

    Unlike the duplicates/faces thumbnails this needs no scan and no DB row —
    it decodes straight from disk. One undecodable file returns 422 for that
    file only; it can never 500 or affect other requests. Audio has no visual
    frame to render, so it's excluded here (the frontend shows a music icon
    instead) — see `/files/raw`, which does serve audio for playback.
    """
    _, library_root = _get_library_and_root(request, library_id)

    abs_path = _resolve_in_library(library_root, path)
    if abs_path is None or not abs_path.is_file():
        raise HTTPException(status_code=404, detail="File not found in library")

    kind = kind_of(abs_path)
    if kind not in MEDIA_KINDS:
        raise HTTPException(status_code=422, detail="Not a media file")

    data = media_thumbnail_jpeg(abs_path, kind, size)
    if data is None:
        raise HTTPException(status_code=422, detail="Cannot decode file")

    return Response(content=data, media_type="image/jpeg")


# ---------------------------------------------------------------------------
# Raw file (full-resolution image / video, for the in-app viewer)
# ---------------------------------------------------------------------------

@router.get("/libraries/{library_id}/files/raw")
def file_raw(
    library_id: str,
    request: Request,
    path: str = Query(..., description="File path relative to the library root"),
):
    """Original bytes of a media file, for viewing full-size or playing back.

    Read-only, same path-safety as the thumbnail endpoint above. Never used
    by any operation that moves, renames, or deletes files. Audio counts as
    media here (playback), same as the Explorer shell's `/raw` route.
    """
    _, library_root = _get_library_and_root(request, library_id)

    abs_path = _resolve_in_library(library_root, path)
    if abs_path is None or not abs_path.is_file():
        raise HTTPException(status_code=404, detail="File not found in library")

    kind = explorer_kind_of(abs_path)
    if kind not in EXPLORER_KINDS:
        raise HTTPException(status_code=422, detail="Not a media file")

    media_type, _ = mimetypes.guess_type(str(abs_path))
    return FileResponse(str(abs_path), media_type=media_type or "application/octet-stream")
