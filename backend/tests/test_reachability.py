import threading
import time
from pathlib import Path

from mediamind.core import reachability


def test_reachable_dir_is_true(tmp_path: Path) -> None:
    assert reachability.is_root_reachable(tmp_path) is True


def test_missing_path_is_false(tmp_path: Path) -> None:
    assert reachability.is_root_reachable(tmp_path / "does-not-exist") is False


def test_hung_probe_is_bounded_and_cached(monkeypatch) -> None:
    calls = []

    class _Slow:
        def __str__(self) -> str:
            return "Z:/offline-share"

        def is_dir(self):  # simulates a wedged network share
            calls.append(1)
            time.sleep(10)
            return True

    root = _Slow()
    monkeypatch.setattr(reachability, "_PROBE_TIMEOUT_SECONDS", 0.2)
    # This test's leaked probe thread holds a permit on _probe_limiter for
    # the full 10s sleep. _probe_limiter is module-level, process-lifetime
    # state (by design — it caps concurrent OS-level probes app-wide), so
    # without an isolated semaphore here this test's leak can starve real
    # reachability checks in unrelated tests that happen to run in the same
    # pytest process shortly afterward.
    monkeypatch.setattr(reachability, "_probe_limiter", threading.Semaphore(reachability._MAX_CONCURRENT_PROBES))
    start = time.monotonic()
    assert reachability.is_root_reachable(root) is False
    assert time.monotonic() - start < 1.0

    # Second call within the TTL must hit the cache, not probe again.
    reachability.is_root_reachable(root)
    assert len(calls) == 1


def test_many_offline_roots_dont_pay_full_timeout_each(monkeypatch) -> None:
    """A cold sweep across many hung roots (e.g. 44 offline libraries) must
    not cost N * timeout — only the first _MAX_CONCURRENT_PROBES roots should
    actually wait; the rest fail fast once the limiter is saturated, since
    their leaked probe threads are still stuck in the real OS call."""

    class _Slow:
        def __init__(self, key: str) -> None:
            self._key = key

        def __str__(self) -> str:
            return self._key

        def is_dir(self):
            time.sleep(10)
            return True

    monkeypatch.setattr(reachability, "_PROBE_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(reachability, "_probe_limiter", threading.Semaphore(reachability._MAX_CONCURRENT_PROBES))
    roots = [_Slow(f"Z:/offline-{i}") for i in range(12)]

    start = time.monotonic()
    for root in roots:
        assert reachability.is_root_reachable(root) is False
    elapsed = time.monotonic() - start

    # Unbounded would cost ~12 * 0.2s = 2.4s; capped at 4 concurrent probes
    # it should be close to 4 * 0.2s = 0.8s.
    assert elapsed < 1.5
