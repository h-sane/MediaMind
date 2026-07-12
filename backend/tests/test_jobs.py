"""Tests for the in-process JobManager."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from mediamind.core.jobs import Job, JobManager


def _make_manager() -> JobManager:
    """Create a JobManager wired to a real event loop."""
    loop = asyncio.new_event_loop()
    jm = JobManager()
    jm.set_event_loop(loop)
    # Run the loop in a background thread so call_soon_threadsafe works.
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    return jm


def _wait_for(job: Job, states: set[str], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while job.state not in states:
        if time.monotonic() > deadline:
            raise TimeoutError(f"Job stuck in state {job.state!r}")
        time.sleep(0.01)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

def test_successful_job_reaches_succeeded():
    jm = _make_manager()
    job = jm.start("lib1", "dedupe", lambda ctx: {"groups": 0})
    _wait_for(job, {"succeeded"})
    assert job.state == "succeeded"
    assert job.result == {"groups": 0}
    assert job.finished_at is not None


def test_failed_job_captures_error():
    jm = _make_manager()

    def bad_runner(ctx):
        raise ValueError("boom")

    job = jm.start("lib1", "dedupe", bad_runner)
    _wait_for(job, {"failed"})
    assert job.state == "failed"
    assert "boom" in job.error
    assert job.finished_at is not None


def test_cancelled_job_reaches_cancelled():
    done = threading.Event()

    def slow_runner(ctx):
        for _ in range(1000):
            if ctx.cancelled():
                return {}
            time.sleep(0.001)
        return {"groups": 99}

    jm = _make_manager()
    job = jm.start("lib1", "dedupe", slow_runner)
    _wait_for(job, {"running"})
    jm.cancel(job.id)
    _wait_for(job, {"cancelled"})
    assert job.state == "cancelled"
    assert job.result is None


def test_one_running_job_per_library():
    barrier = threading.Barrier(2)

    def blocking_runner(ctx):
        barrier.wait(timeout=5)
        while not ctx.cancelled():
            time.sleep(0.005)
        return {}

    jm = _make_manager()
    job = jm.start("lib1", "dedupe", blocking_runner)
    _wait_for(job, {"running"})
    assert jm.running_for("lib1") is not None
    barrier.wait(timeout=5)
    jm.cancel(job.id)


def test_running_for_type_filter():
    """Same-type jobs are reported as active; different types are not."""

    def blocking_runner(ctx):
        while not ctx.cancelled():
            time.sleep(0.005)
        return {}

    jm = _make_manager()
    job = jm.start("lib1", "dedupe", blocking_runner)
    _wait_for(job, {"running"})
    assert jm.running_for("lib1") is not None            # no filter: any type matches
    assert jm.running_for("lib1", "dedupe") is not None  # same type matches
    assert jm.running_for("lib1", "faces") is None       # different type does not
    assert jm.running_for("lib2", "dedupe") is None      # different library
    jm.cancel(job.id)
    _wait_for(job, {"cancelled"})


def test_running_for_includes_queued_jobs():
    """A job that has not flipped to 'running' yet still blocks a double-submit."""
    jm = JobManager()
    jm._jobs["j1"] = Job(id="j1", library_id="lib1", type="dedupe", state="queued")
    assert jm.running_for("lib1") is not None
    assert jm.running_for("lib1", "dedupe") is not None
    assert jm.running_for("lib1", "faces") is None


def test_cancel_idempotent_on_terminal_job():
    jm = _make_manager()
    job = jm.start("lib1", "dedupe", lambda ctx: {})
    _wait_for(job, {"succeeded"})
    assert jm.cancel(job.id) is False  # already terminal


def test_cancel_unknown_job_returns_false():
    jm = _make_manager()
    assert jm.cancel("nonexistent") is False


# ---------------------------------------------------------------------------
# Cancelled vs no-results distinction
# ---------------------------------------------------------------------------

def test_cancelled_result_is_none_not_empty_dict():
    """A cancelled job must set result=None, not the runner's empty return value."""
    finished = threading.Event()

    def runner(ctx):
        ctx._cancel.set()  # self-cancel immediately
        return {}           # find_duplicates returns [] on cancel; runner returns {}

    jm = _make_manager()
    job = jm.start("lib1", "dedupe", runner)
    _wait_for(job, {"cancelled"})
    assert job.result is None


# ---------------------------------------------------------------------------
# Progress reporting
# ---------------------------------------------------------------------------

def test_progress_updates_job_fields():
    reported = []

    def runner(ctx):
        ctx.report_progress(5, 100, "hashing")
        time.sleep(0.05)
        ctx.report_progress(100, 100, "done")
        return {}

    jm = _make_manager()
    job = jm.start("lib1", "dedupe", runner)
    _wait_for(job, {"succeeded"})
    assert job.done == 100
    assert job.total == 100


# ---------------------------------------------------------------------------
# Active-jobs snapshot
# ---------------------------------------------------------------------------

def test_active_jobs_excludes_terminal():
    jm = _make_manager()
    job = jm.start("lib1", "dedupe", lambda ctx: {})
    _wait_for(job, {"succeeded"})
    assert job not in jm.active_jobs()
