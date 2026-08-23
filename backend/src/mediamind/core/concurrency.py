"""Thread-based timeout wrapper for I/O calls that can't be interrupted any
other way (a blocking read()/stat()/scandir() has no cooperative cancellation
point). Used anywhere a single slow path — a cloud-sync placeholder, a
stalled network share, an encrypted-drive mount — must not be allowed to
freeze an entire scan.
"""

from __future__ import annotations

import threading
from typing import Callable


class _TimedOut:
    pass


TIMED_OUT = _TimedOut()

# hash_file() reads the entire file, so a flat wall-clock timeout is wrong for
# it: a multi-GB video on a slow disk legitimately needs more time than a
# small image, not the same budget. Scaling the timeout by size (floored for
# small files) tells "large but reading fine" apart from "stalled" — a flat
# timeout can't, and was skipping large-but-healthy video files outright.
MIN_HASH_THROUGHPUT_BYTES_PER_SEC = 5 * 1024 * 1024  # 5 MB/s floor - conservative even for a slow HDD/network share

# ...but the size-scaling assumes steady throughput, which a *stalled* read
# (a cloud-sync placeholder that never hydrates, a wedged mount) never
# delivers: a 6 GB placeholder would be handed a ~1200s budget and freeze the
# whole scan for 20 minutes on that one file instead of skipping it. A blocked
# read() can't be interrupted mid-call, so the only lever is the budget itself
# — cap it. A file that genuinely needs longer than this to read is skipped
# from dedupe/faces (read-only, logged, and it still shows in the browse
# surface — "everything routes somewhere" is unaffected); progress advances at
# most every MAX_FILE_TIMEOUT_SECONDS instead of appearing frozen indefinitely.
MAX_FILE_TIMEOUT_SECONDS = 90.0


def hash_timeout_for(size_bytes: int, floor: float) -> float:
    """Timeout for hashing a file of this size: scales with size so large
    files aren't skipped just for being large, floored so small stalled files
    still time out quickly, and capped at MAX_FILE_TIMEOUT_SECONDS so a single
    stalled read can never freeze the whole scan."""
    return min(max(floor, size_bytes / MIN_HASH_THROUGHPUT_BYTES_PER_SEC), MAX_FILE_TIMEOUT_SECONDS)


def run_with_timeout(
    fn: Callable[[], object],
    timeout: float,
    limiter: threading.Semaphore | None = None,
) -> object:
    """Runs `fn` on a fresh daemon thread and waits up to `timeout` seconds.

    Returns `TIMED_OUT` if it didn't finish in time. The thread is left
    running in the background in that case — Python cannot forcibly kill a
    thread, but every caller of this helper only performs read-only I/O, so a
    single leaked reader thread is harmless (it dies with the process).
    Re-raises whatever exception `fn` raised, once it actually completes.

    `limiter`, if given, bounds how many of these background threads may be
    leaked (started but never returned) at once. A chronically wedged mount
    (a stalled network share, a locked/disconnected encrypted-drive vault)
    times out file after file across a large scan, and each one leaks
    another thread that never comes back — unbounded over thousands of
    files, that eventually exhausts the process's thread capacity and the
    *next* thread creation fails outright, crashing the scan with an
    unrelated error instead of just skipping one more file. Once `limiter`
    is saturated with already-leaked threads, further calls skip spawning a
    new one and fail fast (treated as an immediate timeout) instead of
    piling on.
    """
    if limiter is not None and not limiter.acquire(blocking=False):
        return TIMED_OUT

    box: list[object] = []

    def _target() -> None:
        try:
            box.append(fn())
        except Exception as exc:  # re-raised on the caller's side below
            box.append(exc)
        finally:
            if limiter is not None:
                limiter.release()

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return TIMED_OUT
    result = box[0]
    if isinstance(result, Exception):
        raise result
    return result
