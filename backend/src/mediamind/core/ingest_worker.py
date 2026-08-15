"""Phase 2 — always-on incremental ingest worker.

One global daemon thread for the whole app. `LibraryWatcher` (core/watcher.py)
feeds it changed-path deltas via `enqueue()`; it drains them in small batches
and calls `core.ingest.ingest_path` per file — the same per-file pipeline the
full-folder scans use (Phase 1), so incremental and full scans share one
implementation of "process a file". Idle (blocked on the queue) when nothing
changes => ~0 CPU/memory.

ponytail: a dict-backed queue + one lock/condvar, not a framework — coalescing
and backpressure are the only two behaviours worth custom code for; everything
else is a plain drain loop.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Iterable

from mediamind.config import library_data_dir
from mediamind.core.jobs import EXCLUSIVE_JOB_TYPES, JobManager
from mediamind.core.libraries import LibraryRegistry
from mediamind.providers.base import FaceProvider
from mediamind.store.db import library_db_path, open_db

logger = logging.getLogger("mediamind.ingest_worker")


class IngestWorker:
    _MAX_QUEUE = 20_000  # backpressure ceiling; overflow drops-with-warn — the
    # next full/manual scan is the backstop that catches anything dropped.
    _BATCH = 64  # commit/report cadence
    _PROVIDER_IDLE_UNLOAD_S = 300.0  # unload the ~300MB face model after 5 min idle
    _DEFER_BACKOFF_S = 2.0  # avoid busy-spinning while an exclusive job holds a library
    _WAIT_POLL_S = 5.0  # wake periodically on an empty queue so idle-unload still runs

    def __init__(
        self,
        registry: LibraryRegistry,
        job_manager: JobManager,
        *,
        provider_factory: Callable[[], FaceProvider] | None = None,
        provider_id: str | None = None,
        enabled: Callable[[], bool] = lambda: True,
        ingest_fn: Callable[..., object] | None = None,
        on_batch_done: Callable[[str, list[str]], None] | None = None,
    ) -> None:
        self._registry = registry
        self._jm = job_manager
        self._provider_factory = provider_factory
        self._provider_id = provider_id
        self._enabled = enabled
        self._ingest_fn = ingest_fn  # injectable for tests; lazily resolved otherwise
        self._on_batch_done = on_batch_done

        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._queue: "OrderedDict[tuple[str, str], None]" = OrderedDict()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.dropped_count = 0

        self._provider_lock = threading.Lock()
        self._provider: FaceProvider | None = None
        self._provider_last_used = 0.0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="ingest-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()

    @property
    def queue_size(self) -> int:
        with self._lock:
            return len(self._queue)

    def enqueue(self, library_id: str, paths: Iterable[str | Path]) -> None:
        """Queue paths for ingest. Duplicate (library_id, path) pairs already
        pending are coalesced. Silently a no-op when auto-ingest is disabled —
        callers (the watcher) don't each need to re-check the setting."""
        if not self._enabled():
            return
        with self._cond:
            for p in paths:
                key = (library_id, str(p))
                if key in self._queue:
                    continue
                if len(self._queue) >= self._MAX_QUEUE:
                    self.dropped_count += 1
                    logger.warning("ingest queue full (%d) — dropping %s", self._MAX_QUEUE, p)
                    continue
                self._queue[key] = None
            self._cond.notify()

    def _drain_up_to(self, n: int) -> list[tuple[str, str]]:
        with self._cond:
            while not self._queue and not self._stop.is_set():
                self._cond.wait(timeout=self._WAIT_POLL_S)
            batch = []
            for _ in range(min(n, len(self._queue))):
                batch.append(self._queue.popitem(last=False)[0])
            return batch

    def _requeue(self, library_id: str, paths: list[str]) -> None:
        with self._cond:
            for p in paths:
                key = (library_id, p)
                if key not in self._queue and len(self._queue) < self._MAX_QUEUE:
                    self._queue[key] = None
            self._cond.notify()

    @staticmethod
    def _by_library(batch: list[tuple[str, str]]) -> "OrderedDict[str, list[str]]":
        groups: "OrderedDict[str, list[str]]" = OrderedDict()
        for library_id, path in batch:
            groups.setdefault(library_id, []).append(path)
        return groups

    def _exclusive_active(self, library_id: str) -> bool:
        job = self._jm.running_for(library_id)
        return job is not None and job.type in EXCLUSIVE_JOB_TYPES

    def _get_provider(self) -> FaceProvider | None:
        with self._provider_lock:
            if self._provider is None and self._provider_factory is not None:
                self._provider = self._provider_factory()
                self._provider.prepare()
            self._provider_last_used = time.monotonic()
            return self._provider

    def _maybe_unload_provider(self) -> None:
        with self._provider_lock:
            if self._provider is not None and time.monotonic() - self._provider_last_used >= self._PROVIDER_IDLE_UNLOAD_S:
                self._provider = None  # drop the reference; GC frees the model

    def _resolve_ingest_fn(self):
        if self._ingest_fn is None:
            from mediamind.core.ingest import ingest_path  # deferred: Phase 1 module, not yet present at import time

            self._ingest_fn = ingest_path
        return self._ingest_fn

    def _process_batch(self, library_id: str, paths: list[str]) -> None:
        lib = self._registry.get(library_id)
        if lib is None:
            return  # library was removed after these paths were enqueued
        provider = self._get_provider() if self._provider_factory else None
        ingest_fn = self._resolve_ingest_fn()
        with self._jm.mark_busy(library_id, "ingest"):
            conn = open_db(library_db_path(library_data_dir(lib.root)))
            try:
                for path in paths:
                    try:
                        ingest_fn(
                            conn,
                            lib.root,
                            Path(path),
                            provider=provider,
                            provider_id=self._provider_id,
                            warm_thumbnail=True,
                        )
                    except Exception:
                        # One bad file must never kill a batch (project-wide invariant).
                        logger.exception("ingest: failed for %s", path)
            finally:
                conn.close()
        if self._on_batch_done is not None:
            self._on_batch_done(library_id, paths)

    def _run(self) -> None:
        while not self._stop.is_set():
            batch = self._drain_up_to(self._BATCH)
            if not batch:
                self._maybe_unload_provider()
                continue
            deferred = False
            for library_id, group in self._by_library(batch).items():
                if self._exclusive_active(library_id):
                    self._requeue(library_id, group)
                    deferred = True
                    continue
                try:
                    self._process_batch(library_id, group)
                except Exception:
                    logger.exception("ingest: batch failed for library %s", library_id)
            if deferred:
                self._stop.wait(self._DEFER_BACKOFF_S)
            self._maybe_unload_provider()
