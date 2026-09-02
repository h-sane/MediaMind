"""Cached, bounded reachability probe for library roots.

Stat-ing an offline network share or a locked encrypted-drive vault
(Cryptomator/WinFsp) can block for the OS network timeout (tens of seconds)
instead of failing fast, and on Windows repeated attempts against a dead UNC
path can back up the shared SMB redirector, stalling I/O to *unrelated*
reachable drives too. Anything that touches many registered library roots in
a loop (watcher scheduling/polling, cross-library People aggregation) must
probe each root at most once per cache window, not once per call.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from mediamind.core.concurrency import TIMED_OUT, run_with_timeout

_PROBE_TIMEOUT_SECONDS = 5.0
_CACHE_TTL_SECONDS = 60.0

# A timed-out probe leaks its background thread (concurrency.run_with_timeout
# can't kill it) sitting in the real OS call until the actual network/mount
# timeout fires — often far longer than _PROBE_TIMEOUT_SECONDS. Without a cap,
# a cold-cache sweep across dozens of offline roots leaks dozens of threads
# each holding a pending connection to a dead host, which backs up Windows'
# shared SMB redirector and stalls unrelated I/O (even to a local drive).
# Capping concurrent in-flight probes bounds that pileup process-wide.
_MAX_CONCURRENT_PROBES = 4
_probe_limiter = threading.Semaphore(_MAX_CONCURRENT_PROBES)

_cache: dict[str, tuple[float, bool]] = {}
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.setdefault(key, threading.Lock())
    return lock


def is_root_reachable(root: Path) -> bool:
    """True if `root` is a directory, probed with a bounded timeout and
    cached so a chronically offline root is only ever actually stat-ed once
    per `_CACHE_TTL_SECONDS` — and only by one caller at a time, so concurrent
    callers racing on the same cold root don't each leak their own probe
    thread."""
    key = str(root)

    def _cached() -> bool | None:
        cached = _cache.get(key)
        if cached is not None and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]
        return None

    hit = _cached()
    if hit is not None:
        return hit

    with _lock_for(key):
        hit = _cached()  # a racing caller may have just finished probing this key
        if hit is not None:
            return hit

        def _probe() -> bool:
            try:
                return root.is_dir()
            except OSError:
                return False

        outcome = run_with_timeout(_probe, _PROBE_TIMEOUT_SECONDS, limiter=_probe_limiter)
        reachable = False if outcome is TIMED_OUT else bool(outcome)
        _cache[key] = (time.monotonic(), reachable)
        return reachable
