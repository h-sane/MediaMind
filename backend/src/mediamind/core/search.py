"""Recursive, cross-subfolder search for the Explorer shell (Phase I).

Single-folder search is a live client-side filter over already-loaded data
(`stores/explorer.ts`, `content/useDirectoryListing.ts` — no network round
trip needed). This module backs the *other* path: a real walk of every
subfolder under an arbitrary root, so the user can find a file that isn't in
the folder currently being browsed.

Media scope is the same predicate `api/routes/fs.py::list_dir` already uses —
`EXPLORER_KINDS`/`explorer_kind_of` from `core/explorer_media.py` for files,
and `is_noise_dir` from `core/media_index.py` for directories to skip — so a
recursive search never surfaces a file/folder type the plain listing wouldn't. Folder *hits*
are further checked against the same `MediaIndex` cache the listing uses
(when available) so a folder that's confirmed junk (has files, none of them
media) doesn't show up as a search result either; that check is a cheap
cache lookup, not an extra walk, so it doesn't slow anything down.

The walk is iterative (no Python recursion depth limit on a deep tree) and
per-entry `try/except` — one ACL-denied or vanished entry is skipped, never
aborting the whole search. It's also cooperatively cancellable: every
`HEARTBEAT_ENTRIES` filesystem entries examined, the generator yields `None`
as a heartbeat so a caller (the API route) gets a chance to check for
cancellation between matches, not just when a match is found — a long
non-matching stretch of the tree would otherwise be unresponsive to cancel.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from mediamind.config import LIBRARY_DATA_DIRNAME
from mediamind.core.explorer_media import EXPLORER_KINDS, explorer_kind_of
from mediamind.core.media_index import MediaIndex, is_noise_dir

# How many filesystem entries to examine between heartbeats — bounds how
# long a non-matching stretch of the tree can run before the caller gets a
# chance to check for cancellation/client-disconnect.
HEARTBEAT_ENTRIES = 200

DEFAULT_SEARCH_LIMIT = 200
MAX_SEARCH_LIMIT = 1000


@dataclass(frozen=True)
class SearchHit:
    kind: str                # "folder" | "file"
    name: str
    path: str                # absolute
    media_kind: str | None   # "image" | "gif" | "video" | "audio"; None for folders
    size: int | None         # None for folders
    mtime: float


def _matches(name: str, query: str) -> bool:
    """Case-insensitive substring match — the same semantics as the
    client-side single-folder filter in `useDirectoryListing.ts` so recursive
    search doesn't behave differently for the common case."""
    return query in name.lower()


def iter_search_hits(
    root: Path,
    query: str,
    limit: int,
    media_index: MediaIndex | None = None,
) -> Iterator[SearchHit | None]:
    """Depth-first walk under `root`, yielding `SearchHit`s as they're found
    and `None` heartbeats every `HEARTBEAT_ENTRIES` entries examined. Stops
    once `limit` hits have been yielded — the caller decides what counts as
    "enough" via `limit` so a huge tree can never hang indefinitely.

    An empty/blank `query` yields nothing (there is nothing useful to walk
    for), matching the client-side filter's own no-op-on-empty-query rule.
    """
    query = query.strip().lower()
    if not query:
        return

    found = 0
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
                    entry_path = Path(entry.path)
                except OSError:
                    continue
                if _matches(entry.name, query) and not _is_confirmed_junk(entry_path, media_index):
                    try:
                        stat = entry.stat()
                        mtime = stat.st_mtime
                    except OSError:
                        mtime = 0.0
                    yield SearchHit(
                        kind="folder",
                        name=entry.name,
                        path=str(entry_path),
                        media_kind=None,
                        size=None,
                        mtime=mtime,
                    )
                    found += 1
                    if found >= limit:
                        return
                stack.append(entry_path)  # descend regardless of whether it matched
            else:
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    entry_path = Path(entry.path)
                    kind = explorer_kind_of(entry_path)
                except OSError:
                    continue
                if kind not in EXPLORER_KINDS or not _matches(entry.name, query):
                    continue
                try:
                    stat = entry.stat()
                except OSError:
                    continue
                yield SearchHit(
                    kind="file",
                    name=entry.name,
                    path=str(entry_path),
                    media_kind=kind,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                )
                found += 1
                if found >= limit:
                    return


def _is_confirmed_junk(path: Path, media_index: MediaIndex | None) -> bool:
    """True only if the cache already knows this subtree has files but none
    of them media — the same "confirmed junk" rule `list_dir` uses. Unknown
    (not yet cached) is treated as "include it" rather than blocking the
    search on a fresh background walk."""
    if media_index is None:
        return False
    status = media_index.check_full(path)
    return status is not None and status.has_media is False and status.has_any_file
