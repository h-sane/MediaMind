"""Recursive, date-sorted media enumeration for the Explorer's Gallery view
(Phase O).

A sibling walk to `core/search.py`'s recursive search: same media-scope
predicate (`EXPLORER_KINDS`/`explorer_kind_of`), same `is_noise_dir`
directory skip, same iterative/per-entry-`try/except`/cancellable-heartbeat
shape — but unfiltered (every media file under the root, not just name
matches) and files-only (a gallery is a flat timeline of media, not a
folder/file mixed listing). Audio is included, matching every other
Explorer-side media surface (`EXPLORER_KINDS`) — the app's face-recognition
scan/dedupe pipeline (`core/scanner.py`'s `MEDIA_KINDS`) is unaffected either
way, same separation `core/explorer_media.py` already established.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from mediamind.config import LIBRARY_DATA_DIRNAME
from mediamind.core.explorer_media import EXPLORER_KINDS, explorer_kind_of
from mediamind.core.media_index import is_noise_dir

# How many filesystem entries to examine between heartbeats — same rationale
# as `core/search.py::HEARTBEAT_ENTRIES`.
HEARTBEAT_ENTRIES = 200

DEFAULT_GALLERY_LIMIT = 500
MAX_GALLERY_LIMIT = 2000

# Hard ceiling on raw items collected during the walk, before sorting and
# slicing to the caller's requested limit — bounds worst-case work on a huge
# tree the same way `core/search.py` bounds its own walk via a result cap.
# Unlike search's cap (which stops as soon as enough *matches* are found),
# this cap can't stop the instant it's hit without risking a bias toward
# whichever subtree the walk happened to visit first — sorting by date only
# happens after collection, so a walk that's cut short could in theory miss
# a truly-most-recent file buried behind a much larger, earlier-visited
# sibling folder. Generous enough that this never matters in practice for a
# single photos/media folder; documented here rather than silently assumed.
MAX_COLLECTED = 5000


@dataclass(frozen=True)
class GalleryItem:
    name: str
    path: str  # absolute
    media_kind: str  # "image" | "gif" | "video" | "audio"
    size: int
    mtime: float


def iter_gallery_items(root: Path) -> Iterator[GalleryItem | None]:
    """Depth-first walk under `root`, yielding every media file found (no
    query filter) and `None` heartbeats every `HEARTBEAT_ENTRIES` entries
    examined. Stops once `MAX_COLLECTED` items have been yielded. The caller
    sorts by `mtime` and slices to whatever limit it actually needs — this
    generator's own job is only bounding the walk, not ordering results.
    """
    collected = 0
    examined = 0
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                entries = list(it)
        except OSError:
            continue  # ACL-denied or vanished directory — skip, don't abort

        for entry in entries:
            examined += 1
            if examined % HEARTBEAT_ENTRIES == 0:
                yield None

            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue

            if is_dir:
                if entry.name == LIBRARY_DATA_DIRNAME or is_noise_dir(entry.name):
                    continue
                try:
                    stack.append(Path(entry.path))
                except OSError:
                    continue
                continue

            try:
                if not entry.is_file(follow_symlinks=False):
                    continue
                entry_path = Path(entry.path)
                kind = explorer_kind_of(entry_path)
            except OSError:
                continue
            if kind not in EXPLORER_KINDS:
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            yield GalleryItem(
                name=entry.name,
                path=str(entry_path),
                media_kind=kind,
                size=stat.st_size,
                mtime=stat.st_mtime,
            )
            collected += 1
            if collected >= MAX_COLLECTED:
                return
