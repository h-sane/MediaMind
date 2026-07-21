"""Phase 8 — filesystem watcher / auto-ingest.

Watches every registered library and, when its set of media files changes
(new/removed/modified), fires a callback so the app can re-run the existing
dedupe + face scans on it. Those scans already do the whole ingest pipeline:
index, duplicate-check, face-cluster, and route new faces of named people into
pending review (`pending_for_named`) — so "auto-ingest" is just re-triggering
them when disk changes.

Detection is by polling: every `interval` seconds each library's media-file
snapshot ({path: mtime}) is compared to the last one. A change must stay stable
across one extra poll (debounce) before firing, so a batch paste of many files
is scanned once after it settles, not mid-copy. The first time a library is
seen it is only baselined (no fire) — pre-existing files aren't "new".

ponytail: polling walk, not OS events (watchdog/ReadDirectoryChangesW). Zero
new dependency, cross-platform, and cost is zero while the feature is off (the
default). Ceiling: on a very large tree the periodic walk costs CPU and change
latency is up to ~2*interval. Swap in watchdog if that bites. The setting
defaults off, so this only runs when the user opts in.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from mediamind.core.libraries import Library, LibraryRegistry
from mediamind.core.scanner import scan_folder

logger = logging.getLogger("mediamind.watcher")

DEFAULT_INTERVAL_SECONDS = 8.0


class LibraryWatcher:
    def __init__(
        self,
        registry: LibraryRegistry,
        on_change: Callable[[Library], None],
        *,
        enabled: Callable[[], bool],
        interval: float = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._registry = registry
        self._on_change = on_change
        self._enabled = enabled
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Last confirmed snapshot per library, and the pending (changed but not
        # yet stable) one used for debounce.
        self._snapshots: dict[str, dict[str, float]] = {}
        self._pending: dict[str, dict[str, float]] = {}

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="library-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _snapshot(self, lib: Library) -> dict[str, float]:
        snap: dict[str, float] = {}
        for f in scan_folder(lib.root):
            if f.is_media:
                snap[str(f.path)] = f.mtime
        return snap

    def poll_once(self) -> list[Library]:
        """One detection pass over all libraries. Returns the libraries whose
        media set changed and has now settled (debounced) — ready to re-scan.
        Pure of any side effect beyond its own snapshot bookkeeping, so it can
        be driven deterministically in tests."""
        fired: list[Library] = []
        live_ids = set()
        for lib in self._registry.list():
            live_ids.add(lib.id)
            try:
                snap = self._snapshot(lib)
            except Exception:
                logger.exception("watcher: snapshot failed for %s", lib.path)
                continue
            prev = self._snapshots.get(lib.id)
            if prev is None:
                self._snapshots[lib.id] = snap  # baseline only — pre-existing files aren't "new"
                continue
            if snap != prev:
                if self._pending.get(lib.id) == snap:
                    # Stable across two polls — the change has settled.
                    self._snapshots[lib.id] = snap
                    self._pending.pop(lib.id, None)
                    fired.append(lib)
                else:
                    self._pending[lib.id] = snap  # still moving; wait one more poll
            else:
                self._pending.pop(lib.id, None)
        # Drop state for libraries that were unregistered.
        for gone in [i for i in self._snapshots if i not in live_ids]:
            self._snapshots.pop(gone, None)
            self._pending.pop(gone, None)
        return fired

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self._enabled():
                    for lib in self.poll_once():
                        logger.info("watcher: %s changed — auto-scanning", lib.path)
                        self._on_change(lib)
            except Exception:
                logger.exception("watcher: poll failed")
            self._stop.wait(self._interval)
