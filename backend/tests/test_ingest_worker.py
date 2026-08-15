"""Phase 2 — IngestWorker: queue coalescing, batching, backpressure, and
exclusive-job deferral.

Driven deterministically against injected fakes: a fake `ingest_path`-shaped
callable, no real face model, and no real watchdog observer. Internal methods
(`enqueue` / `_drain_up_to` / `_process_batch` / `_by_library` / `_requeue`)
are called directly rather than spinning the background thread, so nothing
here depends on timing.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path

from mediamind.core.ingest_worker import IngestWorker
from mediamind.core.jobs import JobManager
from mediamind.core.libraries import LibraryRegistry


def _registry(tmp_path: Path):
    reg = LibraryRegistry(registry_path=tmp_path / "libraries.json")
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    lib = reg.add(lib_dir)
    return reg, lib.id


def test_enqueue_coalesces_duplicate_paths(tmp_path: Path) -> None:
    reg, lib_id = _registry(tmp_path)
    w = IngestWorker(reg, JobManager())
    w.enqueue(lib_id, ["a.jpg", "b.jpg", "a.jpg"])
    assert w.queue_size == 2


def test_enqueue_noop_when_disabled(tmp_path: Path) -> None:
    """The worker must default to not enqueueing anything unless the
    auto-ingest setting is on — checked at enqueue() itself, not just by the
    watcher, so any caller gets the same gate."""
    reg, lib_id = _registry(tmp_path)
    w = IngestWorker(reg, JobManager(), enabled=lambda: False)
    w.enqueue(lib_id, ["a.jpg"])
    assert w.queue_size == 0


def test_batch_of_n_calls_ingest_fn_n_times(tmp_path: Path) -> None:
    reg, lib_id = _registry(tmp_path)
    calls: list[Path] = []

    def fake_ingest(conn, root, path, *, provider, provider_id, warm_thumbnail):
        calls.append(path)

    w = IngestWorker(reg, JobManager(), ingest_fn=fake_ingest)
    paths = [f"{i}.jpg" for i in range(5)]
    w.enqueue(lib_id, paths)

    batch = w._drain_up_to(64)
    assert len(batch) == 5
    for library_id, group in w._by_library(batch).items():
        w._process_batch(library_id, group)

    assert len(calls) == 5


def test_batch_size_caps_a_single_drain(tmp_path: Path) -> None:
    reg, lib_id = _registry(tmp_path)
    w = IngestWorker(reg, JobManager())
    w.enqueue(lib_id, [f"{i}.jpg" for i in range(10)])
    first = w._drain_up_to(4)
    assert len(first) == 4
    assert w.queue_size == 6


def test_queue_overflow_drops_with_warn(tmp_path: Path, caplog) -> None:
    reg, lib_id = _registry(tmp_path)
    w = IngestWorker(reg, JobManager())
    w._MAX_QUEUE = 3  # instance override; keeps the test from enqueueing 20,000 paths
    with caplog.at_level(logging.WARNING, logger="mediamind.ingest_worker"):
        w.enqueue(lib_id, ["a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg"])
    assert w.queue_size == 3
    assert w.dropped_count == 2
    assert "dropping" in caplog.text


def test_a_bad_file_does_not_kill_the_rest_of_the_batch(tmp_path: Path) -> None:
    reg, lib_id = _registry(tmp_path)
    calls: list[Path] = []

    def flaky_ingest(conn, root, path, **kw):
        if str(path).endswith("bad.jpg"):
            raise RuntimeError("boom")
        calls.append(path)

    w = IngestWorker(reg, JobManager(), ingest_fn=flaky_ingest)
    w.enqueue(lib_id, ["a.jpg", "bad.jpg", "c.jpg"])
    batch = w._drain_up_to(64)
    for library_id, group in w._by_library(batch).items():
        w._process_batch(library_id, group)
    assert len(calls) == 2


def test_exclusive_active_job_defers_rather_than_racing(tmp_path: Path) -> None:
    reg, lib_id = _registry(tmp_path)
    jm = JobManager()
    jm.set_event_loop(asyncio.new_event_loop())  # avoid "no event loop in thread" noise from _worker
    calls: list[Path] = []

    def fake_ingest(conn, root, path, **kw):
        calls.append(path)

    w = IngestWorker(reg, jm, ingest_fn=fake_ingest)
    w.enqueue(lib_id, ["a.jpg"])

    # A real exclusive job, so running_for()/EXCLUSIVE_JOB_TYPES sees it exactly
    # as the worker would in production.
    release = threading.Event()
    jm.start(lib_id, "organize-execute", lambda ctx: release.wait(5) and {})

    deadline = time.monotonic() + 2.0
    while jm.running_for(lib_id) is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert jm.running_for(lib_id) is not None, "exclusive job never reached running state"

    batch = w._drain_up_to(64)
    for library_id, group in w._by_library(batch).items():
        assert w._exclusive_active(library_id)
        w._requeue(library_id, group)

    release.set()
    assert calls == []  # never ingested while the exclusive job was active
    assert w.queue_size == 1  # requeued, not dropped
