"""Walk a library and classify files by media kind.

Ported from V0 `sort_media.py` (extension sets and `kind_of`). Scanning is
read-only: it never moves, modifies, or deletes anything.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from mediamind.config import LIBRARY_DATA_DIRNAME
from mediamind.core.concurrency import TIMED_OUT, run_with_timeout

logger = logging.getLogger("mediamind.scanner")

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

# Never descend into these — OS/app noise that is never user media, and
# descending into some of them (e.g. system-protected folders) can be slow
# or trigger permission errors on every entry. Dot-prefixed names are always
# noise too (see is_noise_dir): besides MediaMind's own `.mediamind`, real
# folder trees on a user's drive can contain other apps' hidden state that
# must never be walked into or scanned as user media — e.g. `.git`, or a
# Cryptomator vault's `.dtrash` (its internal trash: files that already look
# "deleted" to the user but still exist on disk, and would otherwise get
# scanned as live duplicates of the files they were deleted from).
SKIP_DIR_NAMES = {
    "$Recycle.Bin",
    "System Volume Information",
    "node_modules",
    ".git",
    "Windows",
    "Program Files",
    "Program Files (x86)",
    "ProgramData",
    "$WinREAgent",
}


def is_noise_dir(name: str) -> bool:
    """True for OS/app clutter that should never be scanned, browsed, or
    descended into — hidden/dot folders, recycle bins, VCS and build
    folders, and known Windows system directories."""
    return name.startswith(".") or name in SKIP_DIR_NAMES


# A single unreachable directory or file must never freeze an entire scan:
# listing a directory or stat-ing a file is a blocking syscall with no other
# bound on its I/O time. Seen in practice with cloud-sync placeholder folders
# (OneDrive/Google Drive Files-On-Demand) and stalled network/encrypted-drive
# mounts — mirrors the same pattern used for the per-file hash read in
# core.dedupe. A directory listing is a single syscall regardless of size, so
# it gets the longer budget; a per-file stat is cheaper and gets a shorter one.
DEFAULT_WALK_TIMEOUT_SECONDS = 30.0
DEFAULT_STAT_TIMEOUT_SECONDS = 15.0

# A directory/file whose read times out leaks its watchdog thread forever
# (see run_with_timeout) — on a chronically wedged mount, a scan of
# thousands of files can leak thousands of never-returning threads with no
# bound, eventually exhausting the process's thread capacity and crashing
# the scan outright instead of just skipping one more file. This caps how
# many such leaked threads one scan_folder() call will tolerate before it
# starts failing further stalls fast rather than spawning more.
MAX_LEAKED_STALL_THREADS = 64


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


def _list_dir(path: Path, timeout: float, limiter: threading.Semaphore) -> list[os.DirEntry]:
    def _list() -> list[os.DirEntry]:
        try:
            return list(os.scandir(path))
        except OSError:
            return []

    outcome = run_with_timeout(_list, timeout, limiter)
    if outcome is TIMED_OUT:
        logger.warning(
            "scan: skipping directory %s - timed out after %.0fs listing it "
            "(likely a cloud-sync placeholder or a stalled network/encrypted-drive mount)",
            path, timeout,
        )
        return []
    return outcome  # type: ignore[return-value]


def scan_folder(
    root: Path,
    recursive: bool = True,
    exclude_dirs: tuple[str, ...] = (LIBRARY_DATA_DIRNAME,),
    on_walk: Callable[[int], None] | None = None,
    on_stat: Callable[[int, int], None] | None = None,
    walk_timeout_seconds: float = DEFAULT_WALK_TIMEOUT_SECONDS,
    stat_timeout_seconds: float = DEFAULT_STAT_TIMEOUT_SECONDS,
    should_cancel: Callable[[], bool] | None = None,
) -> Iterator[ScannedFile]:
    """Yield every file under `root`, classified, in stable sorted order.

    Directories named in `exclude_dirs` (MediaMind's own data folder by
    default) are pruned before descending into them, as is anything
    `is_noise_dir` flags — OS/app noise such as recycle bins, VCS folders,
    and other apps' hidden dot-directories (see `SKIP_DIR_NAMES`). Files that vanish
    mid-scan are skipped rather than raising — a scan must survive a
    changing folder. A directory whose listing doesn't return within
    `walk_timeout_seconds`, or a file whose metadata read doesn't return
    within `stat_timeout_seconds`, is skipped with a logged warning instead
    of hanging the whole scan forever.

    Walking is collected into a list before the first file is yielded, so on
    a large tree this can take a while with no feedback. `on_walk`, if
    given, is called periodically during the walk with a running count of
    files found so far (no known total yet) so a caller can surface
    "N files found so far" progress. Once the walk finishes and the total is
    known, every file's metadata is read (a `stat()` call each) before it can
    be yielded — on a slow disk or network share this was previously
    invisible to the caller (no progress, no timeout) and could look
    identical to a genuinely hung scan. `on_stat`, if given, is called with
    (done, total) as each file's metadata is read.

    Directories are listed manually via `os.scandir` (not `os.walk` or
    `Path.rglob`) so each directory's listing can be individually
    timeout-guarded, and so a symlink or Windows junction/reparse point that
    loops back into an ancestor directory is pruned — neither recursed into
    nor listed as a file — the same protection `os.walk(followlinks=False)`
    gave: an unguarded walk over such a loop can run indefinitely on a
    "many nested folders" tree and looks identical to a hung scan from the
    caller's side.

    `should_cancel`, if given, is polled between directories during the walk
    and between files during the stat pass so a cancelled job stops within
    one directory listing / one stat call instead of only after the entire
    tree has been walked and stat'd — on a large library that first phase can
    take far longer than the hashing phase it precedes, which is where the
    only other cancellation check used to live.
    """
    root = root.expanduser().resolve()
    collected: list[Path] = []
    found = 0
    limiter = threading.Semaphore(MAX_LEAKED_STALL_THREADS)

    def _emit_progress() -> None:
        if on_walk is not None and found % 200 == 0:
            on_walk(found)

    if not recursive:
        for entry in _list_dir(root, walk_timeout_seconds, limiter):
            if entry.name in exclude_dirs or is_noise_dir(entry.name):
                continue
            collected.append(Path(entry.path))
            found += 1
            _emit_progress()
    else:
        stack = [root]
        while stack:
            if should_cancel is not None and should_cancel():
                return
            current = stack.pop()
            subdirs: list[Path] = []
            for entry in _list_dir(current, walk_timeout_seconds, limiter):
                try:
                    is_dir = entry.is_dir()  # follows symlinks, matches os.walk's classification
                except OSError:
                    continue
                if is_dir:
                    if entry.name in exclude_dirs or is_noise_dir(entry.name):
                        continue
                    try:
                        is_link = entry.is_symlink()
                    except OSError:
                        is_link = False
                    if is_link:
                        continue  # symlink/junction to a directory — pruned, never recursed
                    subdirs.append(Path(entry.path))
                else:
                    collected.append(Path(entry.path))
                    found += 1
                    _emit_progress()
            stack.extend(subdirs)

    if should_cancel is not None and should_cancel():
        return

    if on_walk is not None:
        on_walk(found)

    total = len(collected)
    for i, path in enumerate(sorted(collected), 1):
        if should_cancel is not None and should_cancel():
            return

        def _read(path: Path = path) -> tuple[int, float] | None:
            if not path.is_file():
                return None
            stat = path.stat()
            return stat.st_size, stat.st_mtime

        try:
            outcome = run_with_timeout(_read, stat_timeout_seconds, limiter)
        except Exception:
            # A single file's metadata read must never end the whole scan
            # (project invariant: one bad file can't crash a run) — anything
            # beyond the expected OSError (e.g. a thread-creation failure
            # once many stalls have already leaked threads) is skipped the
            # same way.
            outcome = None

        if outcome is TIMED_OUT:
            logger.warning(
                "scan: skipping %s - timed out after %.0fs reading its file info "
                "(likely a cloud-sync placeholder or a stalled network/encrypted-drive read)",
                path, stat_timeout_seconds,
            )
            outcome = None

        if on_stat is not None:
            on_stat(i, total)

        if outcome is None:
            continue

        size, mtime = outcome  # type: ignore[misc]
        yield ScannedFile(path=path, kind=kind_of(path), size=size, mtime=mtime)
