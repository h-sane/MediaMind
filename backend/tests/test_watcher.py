"""Phase 8 (poll) + Phase 2/V4 (native events) watcher: change detection,
debounce, baseline behaviour, and the delta the callback now receives.

`on_change` is now `Callable[[Library, list[str]], None]` — the callback gets
the changed paths, not just "this library changed" (core/ingest_worker.py's
`enqueue()` needs the paths). Kept deterministic: no real watchdog Observer
thread is spun up here (that's OS-timing-dependent and slow); the native-event
tests drive the debounce buffer directly via `_mark_dirty`/`_flush_native`,
and the scheduling-fallback test monkeypatches `Observer.schedule` to fail
synchronously rather than relying on a real unsupported filesystem.
"""

from __future__ import annotations

import time
from pathlib import Path

from mediamind.core.libraries import LibraryRegistry
from mediamind.core.watcher import LibraryWatcher, Observer


def _registry(tmp_path: Path) -> LibraryRegistry:
    reg = LibraryRegistry(registry_path=tmp_path / "libraries.json")
    reg.add(tmp_path / "lib")
    return reg


def test_baseline_then_debounced_fire(tmp_path: Path) -> None:
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    (lib_dir / "a.jpg").write_bytes(b"x")

    reg = _registry(tmp_path)
    w = LibraryWatcher(reg, on_change=lambda lib, paths: None, enabled=lambda: True)

    # First poll only baselines the pre-existing file — nothing is "new".
    assert w.poll_once() == []

    # A new file appears: first poll after it sees a change but waits (debounce).
    (lib_dir / "b.jpg").write_bytes(b"y")
    assert w.poll_once() == []
    # Stable across the next poll → fires exactly once.
    fired = w.poll_once()
    lib_id = reg.list()[0].id
    assert [lib.id for lib in fired] == [lib_id]
    # The delta captured for the fired library is exactly the new file.
    assert len(w._last_delta[lib_id]) == 1
    assert w._last_delta[lib_id][0].endswith("b.jpg")
    # No further change → no more fires.
    assert w.poll_once() == []


def test_non_media_change_does_not_fire(tmp_path: Path) -> None:
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    reg = _registry(tmp_path)
    w = LibraryWatcher(reg, on_change=lambda lib, paths: None, enabled=lambda: True)
    assert w.poll_once() == []

    (lib_dir / "notes.txt").write_text("hi")
    assert w.poll_once() == []
    assert w.poll_once() == []  # a non-media file never counts as new media


def test_native_schedule_failure_falls_back_to_poll(tmp_path: Path, monkeypatch) -> None:
    """A root where `watchdog` can't schedule a native watch (e.g. some
    network drives) keeps working via the original poll-diff path, with the
    same delta contract."""
    monkeypatch.setattr(
        Observer, "schedule", lambda self, *a, **k: (_ for _ in ()).throw(OSError("no native support"))
    )
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    reg = _registry(tmp_path)
    lib_id = reg.list()[0].id
    fired: list[tuple[str, list[str]]] = []
    w = LibraryWatcher(reg, on_change=lambda lib, paths: fired.append((lib.id, paths)), enabled=lambda: True)
    w._observer = Observer()  # no .start() — no real thread, keeps this deterministic

    w._ensure_watches()
    assert lib_id not in w._native_roots  # scheduling failed -> fell back to poll

    assert w.poll_once() == []  # baseline
    (lib_dir / "b.jpg").write_bytes(b"y")
    assert w.poll_once() == []
    settled = w.poll_once()
    assert [lib.id for lib in settled] == [lib_id]
    assert w._last_delta[lib_id][0].endswith("b.jpg")


def test_native_flush_debounces_before_delivering(tmp_path: Path) -> None:
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    reg = _registry(tmp_path)
    lib = reg.list()[0]
    fired: list[tuple[str, list[str]]] = []
    w = LibraryWatcher(reg, on_change=lambda l, paths: fired.append((l.id, paths)), enabled=lambda: True)

    changed_path = str(lib_dir / "new.jpg")
    w._mark_dirty(lib.id, changed_path)
    w._flush_native()
    assert fired == []  # event just landed — still inside the debounce window

    # Simulate the debounce window having elapsed (no real sleep needed).
    with w._native_lock:
        w._native_dirty[lib.id][changed_path] = time.monotonic() - 10
    w._flush_native()
    assert fired == [(lib.id, [changed_path])]


def test_native_flush_drops_silently_when_disabled(tmp_path: Path) -> None:
    (tmp_path / "lib").mkdir()
    reg = _registry(tmp_path)
    lib = reg.list()[0]
    fired: list[tuple[str, list[str]]] = []
    w = LibraryWatcher(reg, on_change=lambda l, paths: fired.append((l.id, paths)), enabled=lambda: False)

    changed_path = str(tmp_path / "lib" / "new.jpg")
    w._mark_dirty(lib.id, changed_path)  # _mark_dirty itself isn't reached in
    # production while disabled (the handler checks `enabled()` first) — this
    # exercises _flush_native's own gate directly.
    with w._native_lock:
        w._native_dirty[lib.id][changed_path] = time.monotonic() - 10
    w._flush_native()
    assert fired == []
