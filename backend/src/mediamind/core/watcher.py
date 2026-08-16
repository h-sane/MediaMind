"""Phase 8 (poll) + Phase 2/V4 (real FS events) — filesystem watcher / auto-ingest.

Watches every registered library and, when its set of media files changes
(new/modified), fires a callback with the *delta* of changed paths so the app
can incrementally ingest just those files (`core.ingest_worker.IngestWorker`)
instead of re-running a whole-folder scan.

Two detection mechanisms, selected per library root:

- **Native events** (default): a single shared `watchdog` `Observer` schedules
  a recursive watch per library root (`ReadDirectoryChangesW` on Windows,
  `inotify` on Linux, `FSEvents` on macOS). Changes are known the instant the
  OS reports them — no walking, ~0 CPU while idle.
- **Poll fallback**: for a root where scheduling the native watch fails (some
  network drives / virtual filesystems don't support it), this library falls
  back to the original snapshot-diff poll loop. This is the exact mechanism
  the watcher used before `watchdog` was added — kept verbatim as the
  fallback rather than deleted.

Both paths debounce ("settle across one extra tick") before a changed path is
considered ready to enqueue, since a large file mid-copy fires many
create/modify events. The first time a library is seen it is only baselined
(no fire) — pre-existing files aren't "new".

ponytail: the native path only catches a *synchronous* `schedule()` failure
(bad/unsupported path) and falls back to polling for that root; an observer
that starts fine but errors later (e.g. a network drive unmounted mid-run)
keeps its native registration with no further events until process restart.
Full per-root health-checking is a heavier watchdog integration than this
pass needs — the periodic manual/full scan remains the backstop either way.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from mediamind.config import LIBRARY_DATA_DIRNAME
from mediamind.core.discovery import fixed_drive_roots
from mediamind.core.libraries import Library, LibraryRegistry
from mediamind.core.scanner import MEDIA_KINDS, is_noise_dir, kind_of, scan_folder

logger = logging.getLogger("mediamind.watcher")

DEFAULT_INTERVAL_SECONDS = 8.0  # poll-fallback cadence
_NATIVE_DEBOUNCE_SECONDS = 1.5  # settle window for native FS events
_NATIVE_FLUSH_TICK_SECONDS = 1.0  # how often the debounce buffer is checked


class _WatchdogHandler(FileSystemEventHandler):
    """Records changed media paths for one library into the watcher's
    debounce buffer. All filtering (directories, `.mediamind`, non-media)
    happens here so the buffer only ever holds paths worth ingesting."""

    def __init__(self, watcher: "LibraryWatcher", lib: Library) -> None:
        self._watcher = watcher
        self._lib = lib

    def _record(self, raw_path: str, is_directory: bool) -> None:
        if is_directory or not self._watcher._enabled():
            return
        path = Path(raw_path)
        if LIBRARY_DATA_DIRNAME in path.parts or any(is_noise_dir(part) for part in path.parts):
            return  # e.g. our own thumbnail-cache writes under .mediamind
        if kind_of(path) not in MEDIA_KINDS:
            return
        self._watcher._mark_dirty(self._lib.id, str(path))

    def on_created(self, event) -> None:
        self._record(event.src_path, event.is_directory)

    def on_modified(self, event) -> None:
        self._record(event.src_path, event.is_directory)

    def on_moved(self, event) -> None:
        self._record(event.dest_path, event.is_directory)


# Tier-3 ("system" mode) path-part exclusions, on top of the library handler's
# existing name-based filter — cache/temp folders churn constantly and are
# never user media, and this fires on every raw OS event across whole drives
# so it must stay a cheap set-membership check.
_DISCOVERY_EXTRA_EXCLUDE = {
    "appdata",
    "temp",
    "cache",
    "caches",
    "cache_data",
    "gpucache",
    "code cache",
    "$winreagent",
    "recovery",
}


class _DiscoveryHandler(FileSystemEventHandler):
    """Tier-3 ("system" mode) handler for whole-drive watches: tallies which
    *unregistered* folders have new media, nothing more. Kept separate from
    `_WatchdogHandler` rather than extended from it — it has a different job
    (a cheap per-folder count vs. per-library dirty-path tracking for a real
    ingest run) and keeping the hot per-event path small and separate is
    easier to reason about than branching one handler two ways."""

    def __init__(self, watcher: "LibraryWatcher") -> None:
        self._watcher = watcher

    def _record(self, raw_path: str, is_directory: bool) -> None:
        if is_directory or not self._watcher._mode() == "system":
            return
        path = Path(raw_path)
        if LIBRARY_DATA_DIRNAME in path.parts or any(is_noise_dir(part) for part in path.parts):
            return
        if any(part.lower() in _DISCOVERY_EXTRA_EXCLUDE for part in path.parts):
            return
        if kind_of(path) not in MEDIA_KINDS:
            return
        if self._watcher._under_registered_root(path):
            return  # that library's own _WatchdogHandler already handles it
        self._watcher._mark_discovery_dirty(str(path.parent))

    def on_created(self, event) -> None:
        self._record(event.src_path, event.is_directory)

    def on_modified(self, event) -> None:
        self._record(event.src_path, event.is_directory)

    def on_moved(self, event) -> None:
        self._record(event.dest_path, event.is_directory)


class LibraryWatcher:
    def __init__(
        self,
        registry: LibraryRegistry,
        on_change: Callable[[Library, list[str]], None],
        *,
        enabled: Callable[[], bool],
        mode: Callable[[], str] = lambda: "libraries",
        on_discovery: Callable[[str], None] = lambda folder: None,
        interval: float = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._registry = registry
        self._on_change = on_change
        self._enabled = enabled
        self._mode = mode
        self._on_discovery = on_discovery
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        # Poll-fallback state (unchanged from the original Phase 8 poll loop).
        self._snapshots: dict[str, dict[str, float]] = {}
        self._pending: dict[str, dict[str, float]] = {}
        self._last_delta: dict[str, list[str]] = {}

        # Native-event state.
        self._observer: Observer | None = None
        self._attempted_native: set[str] = set()
        self._native_roots: set[str] = set()
        self._native_lock = threading.Lock()
        self._native_dirty: dict[str, dict[str, float]] = {}  # lib_id -> {path: last_event_time}

        # Tier-3 ("system" mode) discovery state.
        self._drive_watches: dict[str, object] = {}  # drive root -> ObservedWatch, for unscheduling
        self._discovery_dirty: dict[str, float] = {}  # folder -> last_event_time
        self._discovery_lock = threading.Lock()

    def start(self) -> None:
        if self._thread is not None:
            return
        try:
            self._observer = Observer()
            self._observer.start()
        except Exception:
            logger.exception("watcher: native observer unavailable — all libraries will use polling")
            self._observer = None
        self._thread = threading.Thread(target=self._loop, name="library-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._observer is not None:
            try:
                self._observer.stop()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Native-event scheduling
    # ------------------------------------------------------------------

    def _ensure_watches(self) -> None:
        # Registered-library watches are scheduled unconditionally (parity
        # with pre-V3 behavior: `_ensure_watches` never gated scheduling on
        # the enabled flag — only event *delivery* in `_record`/`poll_once`/
        # `_flush_native` is gated). Tier-3 drive watches are the new,
        # mode-gated behavior.
        live_ids = set()
        for lib in self._registry.list():
            live_ids.add(lib.id)
            if lib.id in self._attempted_native:
                continue
            self._attempted_native.add(lib.id)
            self._schedule_native(lib)
        gone = self._native_roots - live_ids
        for lib_id in gone:
            self._native_roots.discard(lib_id)
            self._attempted_native.discard(lib_id)
            with self._native_lock:
                self._native_dirty.pop(lib_id, None)

        self._ensure_drive_watches()

    def _ensure_drive_watches(self) -> None:
        if self._observer is None:
            return
        if self._mode() != "system":
            if self._drive_watches:
                for watch in self._drive_watches.values():
                    try:
                        self._observer.unschedule(watch)
                    except Exception:
                        pass
                self._drive_watches.clear()
            return
        wanted = set(fixed_drive_roots())
        for root in wanted - self._drive_watches.keys():
            try:
                watch = self._observer.schedule(_DiscoveryHandler(self), root, recursive=True)
                self._drive_watches[root] = watch
            except Exception:
                logger.warning("watcher: native events unavailable for drive %s", root)
        for root in self._drive_watches.keys() - wanted:
            try:
                self._observer.unschedule(self._drive_watches.pop(root))
            except Exception:
                self._drive_watches.pop(root, None)

    def _under_registered_root(self, path: Path) -> bool:
        for lib in self._registry.list():
            try:
                path.relative_to(lib.root)
                return True
            except ValueError:
                continue
        return False

    def _mark_discovery_dirty(self, folder: str) -> None:
        with self._discovery_lock:
            self._discovery_dirty[folder] = time.monotonic()

    def _schedule_native(self, lib: Library) -> None:
        if self._observer is None:
            return
        try:
            self._observer.schedule(_WatchdogHandler(self, lib), str(lib.root), recursive=True)
            self._native_roots.add(lib.id)
        except Exception:
            logger.warning("watcher: native events unavailable for %s — falling back to polling", lib.path)

    def _mark_dirty(self, library_id: str, path: str) -> None:
        with self._native_lock:
            self._native_dirty.setdefault(library_id, {})[path] = time.monotonic()

    def _flush_native(self) -> None:
        now = time.monotonic()
        ready: dict[str, list[str]] = {}
        with self._native_lock:
            for lib_id, dirty in list(self._native_dirty.items()):
                settled = [p for p, t in dirty.items() if now - t >= _NATIVE_DEBOUNCE_SECONDS]
                for p in settled:
                    dirty.pop(p, None)
                if not dirty:
                    self._native_dirty.pop(lib_id, None)
                if settled:
                    ready[lib_id] = settled
        if ready and self._enabled():
            for lib_id, paths in ready.items():
                lib = self._registry.get(lib_id)
                if lib is not None:
                    self._on_change(lib, paths)

        self._flush_discovery()

    def _flush_discovery(self) -> None:
        now = time.monotonic()
        settled: list[str] = []
        with self._discovery_lock:
            for folder, t in list(self._discovery_dirty.items()):
                if now - t >= _NATIVE_DEBOUNCE_SECONDS:
                    settled.append(folder)
                    self._discovery_dirty.pop(folder, None)
        for folder in settled:
            self._on_discovery(folder)

    # ------------------------------------------------------------------
    # Poll fallback (original Phase 8 mechanism)
    # ------------------------------------------------------------------

    def _snapshot(self, lib: Library) -> dict[str, float]:
        snap: dict[str, float] = {}
        for f in scan_folder(lib.root):
            if f.is_media:
                snap[str(f.path)] = f.mtime
        return snap

    def poll_once(self) -> list[Library]:
        """One detection pass over every library that isn't natively watched
        (or hasn't attempted native scheduling — e.g. driven directly in
        tests without `start()`). Returns the libraries whose media set
        changed and has now settled (debounced) — ready to re-scan. Pure of
        any side effect beyond its own snapshot bookkeeping, so it can be
        driven deterministically in tests."""
        fired: list[Library] = []
        live_ids = set()
        for lib in self._registry.list():
            live_ids.add(lib.id)
            if lib.id in self._native_roots:
                continue  # natively watched — polling it too would be redundant work
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
                    changed = [p for p, mtime in snap.items() if prev.get(p) != mtime]
                    self._last_delta[lib.id] = changed
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
            self._last_delta.pop(gone, None)
        return fired

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        next_poll = 0.0
        while not self._stop.is_set():
            try:
                self._ensure_watches()
                now = time.monotonic()
                if now >= next_poll:
                    next_poll = now + self._interval
                    if self._enabled():
                        for lib in self.poll_once():
                            paths = self._last_delta.get(lib.id, [])
                            logger.info("watcher: %s changed (%d files) — auto-ingesting", lib.path, len(paths))
                            self._on_change(lib, paths)
                self._flush_native()
            except Exception:
                logger.exception("watcher: loop failed")
            self._stop.wait(min(self._interval, _NATIVE_FLUSH_TICK_SECONDS))
