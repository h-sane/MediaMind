"""Background thumbnail pre-warm for a just-opened Explorer folder (Phase 5, E1).

Native `<img loading="lazy">` already fetches the *visible* tiles first; this
fills the below-the-fold tiles ahead of the scroll so they're an instant cache
hit when reached — Explorer's cache-first-async-fill. Warming is a pure cache
side-effect: each file is run through `media_thumbnail_jpeg`, whose L1/L2 caches
store the result; the returned bytes are discarded here.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mediamind.core.scanner import MEDIA_KINDS, kind_of
from mediamind.core.thumbnails import media_thumbnail_jpeg


class ThumbnailPrewarmer:
    """One instance on `app.state`. A new `warm()` supersedes the previous one:
    rapid folder-to-folder navigation abandons the old folder's remaining work
    at the next file boundary instead of piling decode tasks up behind it."""

    def __init__(self, max_workers: int = 2):
        # ponytail: bounded pool, no visible-vs-below-fold priority — warming
        # competes with on-demand /fs/thumbnail decodes for CPU. Upgrade path:
        # pause warming while requests are in flight.
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="thumb-warm"
        )
        self._generation = 0
        self._lock = threading.Lock()

    def warm(self, folder: Path, size: int) -> None:
        with self._lock:
            self._generation += 1
            gen = self._generation
        self._executor.submit(self._run, folder, size, gen)

    def _run(self, folder: Path, size: int, gen: int) -> None:
        try:
            with os.scandir(folder) as it:
                # Name-sorted = the listing's default top-down order, so tiles
                # fill in the order they're most likely to scroll into view.
                paths = sorted(
                    (e.path for e in it if e.is_file(follow_symlinks=False)),
                    key=lambda p: os.path.basename(p).lower(),
                )
        except OSError:
            return
        for p in paths:
            with self._lock:
                if gen != self._generation:
                    return  # superseded by a newer folder open
            path = Path(p)
            kind = kind_of(path)
            if kind in MEDIA_KINDS:
                media_thumbnail_jpeg(path, kind, size)  # caches; bytes discarded
