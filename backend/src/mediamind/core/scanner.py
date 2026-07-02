"""Walk a library and classify files by media kind.

Ported from V0 `sort_media.py` (extension sets and `kind_of`). Scanning is
read-only: it never moves, modifies, or deletes anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from mediamind.config import LIBRARY_DATA_DIRNAME

IMAGE_EXTS = {".jpg", ".jpeg", ".jfif", ".png", ".bmp", ".webp",
              ".tiff", ".tif", ".heic", ".heif", ".avif"}
GIF_EXTS = {".gif"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".3g2",
              ".mpg", ".mpeg", ".wmv", ".flv", ".ts", ".mts", ".m2ts", ".ogv"}

KIND_IMAGE = "image"
KIND_GIF = "gif"
KIND_VIDEO = "video"
KIND_OTHER = "other"

MEDIA_KINDS = (KIND_IMAGE, KIND_GIF, KIND_VIDEO)


@dataclass(frozen=True)
class ScannedFile:
    path: Path
    kind: str
    size: int
    mtime: float

    @property
    def is_media(self) -> bool:
        return self.kind in MEDIA_KINDS


def kind_of(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return KIND_IMAGE
    if ext in GIF_EXTS:
        return KIND_GIF
    if ext in VIDEO_EXTS:
        return KIND_VIDEO
    return KIND_OTHER


def scan_folder(
    root: Path,
    recursive: bool = True,
    exclude_dirs: tuple[str, ...] = (LIBRARY_DATA_DIRNAME,),
) -> Iterator[ScannedFile]:
    """Yield every file under `root`, classified, in stable sorted order.

    Directories named in `exclude_dirs` (MediaMind's own data folder by
    default) are skipped entirely. Files that vanish mid-scan are skipped
    rather than raising — a scan must survive a changing folder.
    """
    root = root.expanduser().resolve()
    walker = root.rglob("*") if recursive else root.glob("*")
    for path in sorted(walker):
        if any(part in exclude_dirs for part in path.relative_to(root).parts):
            continue
        try:
            if not path.is_file():
                continue
            stat = path.stat()
        except OSError:
            continue
        yield ScannedFile(path=path, kind=kind_of(path), size=stat.st_size, mtime=stat.st_mtime)
