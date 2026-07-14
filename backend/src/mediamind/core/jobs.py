"""In-process background job manager.

One daemon thread per job; cooperative cancellation via threading.Event.
Jobs are ephemeral (in-memory); results are written to SQLite by the runner.
Concurrency policy: at most one active job of a given *type* per library
(two dedupe scans can't overlap, but a dedupe scan and a face scan can —
they touch disjoint tables and only read the filesystem). Destructive
operations (organize, trash) still refuse to start while ANY job is active
for the library via `running_for(library_id)` with no type filter.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger("mediamind.jobs")


@dataclass
class Job:
    id: str
    library_id: str
    type: str   # "dedupe" | "faces" | "provider-download" | "dedupe-execute"
    state: str  # queued | running | succeeded | failed | cancelled
    phase: str = ""
    done: int = 0
    total: int = 0
    error: str = ""
    result: dict | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None


class JobContext:
    """Passed to a runner function; bridges threaded progress into the asyncio loop."""

    # Throttle: emit at most one progress event per _INTERVAL seconds from threads.
    _INTERVAL = 0.2

    def __init__(
        self,
        job: Job,
        cancel_event: threading.Event,
        loop: asyncio.AbstractEventLoop,
        on_progress: Callable[[Job], None],
    ) -> None:
        self._job = job
        self._cancel = cancel_event
        self._loop = loop
        self._on_progress = on_progress
        self._last_emit = 0.0

    @property
    def job_id(self) -> str:
        return self._job.id

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def report_progress(self, done: int, total: int, phase: str = "") -> None:
        self._job.done = done
        self._job.total = total
        if phase:
            self._job.phase = phase
        now = time.monotonic()
        if now - self._last_emit >= self._INTERVAL:
            self._last_emit = now
            try:
                self._loop.call_soon_threadsafe(self._on_progress, self._job)
            except RuntimeError:
                pass  # loop closed (e.g. test teardown)


class JobManager:
    """Thread-safe registry of running and recently-finished jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        # Set by api/ws.py once the broadcast channel is ready.
        self._broadcast: Callable[[Job], None] | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def set_broadcast(self, fn: Callable[[Job], None]) -> None:
        self._broadcast = fn

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def running_for(self, library_id: str, job_type: str | None = None) -> Job | None:
        """Return an active (queued or running) job for this library, if any.

        job_type=None matches any type — used by guards that must block on all
        activity (organize/trash execute). Pass a type to only match same-type
        jobs, which lets independent scan types run concurrently. "queued" is
        included so a double-submit can't slip in before the worker thread
        flips the state to "running".
        """
        with self._lock:
            for job in self._jobs.values():
                if job.library_id != library_id:
                    continue
                if job.state not in ("queued", "running"):
                    continue
                if job_type is not None and job.type != job_type:
                    continue
                return job
        return None

    def active_jobs(self) -> list[Job]:
        """Non-terminal jobs — sent as a snapshot to newly connected WS clients."""
        with self._lock:
            return [j for j in self._jobs.values() if j.state in ("queued", "running")]

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def start(
        self,
        library_id: str,
        job_type: str,
        runner: Callable[["JobContext"], dict],
    ) -> Job:
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, library_id=library_id, type=job_type, state="queued")
        cancel_event = threading.Event()

        with self._lock:
            self._jobs[job_id] = job
            self._cancel_events[job_id] = cancel_event

        loop = self._loop or asyncio.get_event_loop()
        ctx = JobContext(job, cancel_event, loop, self._emit)
        thread = threading.Thread(
            target=self._worker, args=(job, ctx, runner, cancel_event), daemon=True
        )
        thread.start()
        return job

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            event = self._cancel_events.get(job_id)
        if job is None or job.state not in ("queued", "running"):
            return False
        if event:
            event.set()
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _emit(self, job: Job) -> None:
        """Called in the asyncio event loop (via call_soon_threadsafe)."""
        if self._broadcast:
            self._broadcast(job)

    def _worker(
        self,
        job: Job,
        ctx: JobContext,
        runner: Callable[[JobContext], dict],
        cancel_event: threading.Event,
    ) -> None:
        loop = self._loop or asyncio.get_event_loop()
        job.state = "running"
        try:
            loop.call_soon_threadsafe(self._emit, job)
        except RuntimeError:
            pass
        try:
            result = runner(ctx)
            if cancel_event.is_set():
                job.state = "cancelled"
                job.result = None
            else:
                job.state = "succeeded"
                job.result = result
        except Exception as exc:
            job.state = "failed"
            job.error = str(exc)
            logger.exception("Job %s (type=%s, library=%s) failed", job.id, job.type, job.library_id)
        finally:
            job.finished_at = time.time()
            try:
                loop.call_soon_threadsafe(self._emit, job)
            except RuntimeError:
                pass  # loop closed (e.g. test teardown)
