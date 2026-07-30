"""Phase 8 watcher: change detection + debounce + baseline behaviour."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mediamind.api.app import create_app
from mediamind.core.libraries import LibraryRegistry
from mediamind.core.watcher import LibraryWatcher


def _registry(tmp_path: Path) -> LibraryRegistry:
    reg = LibraryRegistry(registry_path=tmp_path / "libraries.json")
    reg.add(tmp_path / "lib")
    return reg


def test_baseline_then_debounced_fire(tmp_path: Path) -> None:
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    (lib_dir / "a.jpg").write_bytes(b"x")

    reg = _registry(tmp_path)
    w = LibraryWatcher(reg, on_change=lambda lib: None, enabled=lambda: True)

    # First poll only baselines the pre-existing file — nothing is "new".
    assert w.poll_once() == []

    # A new file appears: first poll after it sees a change but waits (debounce).
    (lib_dir / "b.jpg").write_bytes(b"y")
    assert w.poll_once() == []
    # Stable across the next poll → fires exactly once.
    fired = w.poll_once()
    assert [lib.id for lib in fired] == [reg.list()[0].id]
    # No further change → no more fires.
    assert w.poll_once() == []


def test_non_media_change_does_not_fire(tmp_path: Path) -> None:
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    reg = _registry(tmp_path)
    w = LibraryWatcher(reg, on_change=lambda lib: None, enabled=lambda: True)
    assert w.poll_once() == []

    (lib_dir / "notes.txt").write_text("hi")
    assert w.poll_once() == []
    assert w.poll_once() == []  # a non-media file never counts as new media


def test_wired_watcher_auto_starts_a_dedupe_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: the watcher the app wires in lifespan, once auto-scan is on,
    starts a real dedupe job when new media settles in a registered library."""
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    Image.new("RGB", (64, 64), (100, 150, 200)).save(lib_dir / "a.jpg")

    with TestClient(create_app()) as client:
        # Leave auto-scan off so the background poll loop stays idle and can't
        # race the manual polling below; poll_once()/_on_change are the exact
        # calls the loop makes, so this still exercises the wired path.
        lib_id = client.post("/v1/libraries", json={"path": str(lib_dir)}).json()["id"]

        watcher = client.app.state.watcher
        jm = client.app.state.job_manager

        assert watcher.poll_once() == []  # baseline the existing file

        # New media lands; fires after it settles across one extra poll.
        Image.new("RGB", (64, 64), (0, 0, 0)).save(lib_dir / "b.jpg")
        assert watcher.poll_once() == []
        fired = watcher.poll_once()
        for lib in fired:
            client.app.state.watcher._on_change(lib)  # what the real loop does

        deadline = time.monotonic() + 30.0
        job = None
        while time.monotonic() < deadline:
            job = jm.running_for(lib_id, "dedupe") or next(
                (j for j in jm._jobs.values() if j.library_id == lib_id and j.type == "dedupe"),
                None,
            )
            if job is not None and job.state in ("succeeded", "failed", "cancelled"):
                break
            time.sleep(0.1)
        assert job is not None and job.state == "succeeded"
        assert job.triggered_by == "watcher", "auto-scan jobs must be tagged for the frontend's toast copy"
