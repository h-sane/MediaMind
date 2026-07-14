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
