"""Registry add() safety: idempotent re-add is I/O-free, and a wedged mount
can't hang the call past its bounded probe timeout (regression for the
POST /v1/libraries 100s-hang on a locked encrypted-drive vault)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from mediamind.core import libraries
from mediamind.core.libraries import LibraryRegistry


def _registry(tmp_path: Path) -> LibraryRegistry:
    return LibraryRegistry(registry_path=tmp_path / "libraries.json")


def test_add_is_idempotent(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    (tmp_path / "lib1").mkdir()
    lib = reg.add(tmp_path / "lib1")
    again = reg.add(Path(lib.path))
    assert again.id == lib.id


def test_readd_never_touches_filesystem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reg = _registry(tmp_path)
    (tmp_path / "lib2").mkdir()
    lib = reg.add(tmp_path / "lib2")

    def _boom(self):  # any filesystem probe on the re-add path is a bug
        raise AssertionError("resolve() called on idempotent re-add")

    monkeypatch.setattr(Path, "resolve", _boom)
    again = reg.add(Path(lib.path))  # exact stored path — must hit the fast path
    assert again.id == lib.id


def test_missing_path_raises(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    with pytest.raises(NotADirectoryError):
        reg.add(tmp_path / "does-not-exist")


def test_wedged_mount_times_out_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reg = _registry(tmp_path)
    monkeypatch.setattr(libraries, "_ADD_PROBE_TIMEOUT_SECONDS", 0.3)

    def _hang(self):
        time.sleep(30)
        return self

    monkeypatch.setattr(Path, "resolve", _hang)
    t0 = time.perf_counter()
    with pytest.raises(NotADirectoryError):
        reg.add(tmp_path / "wedged-share")
    assert time.perf_counter() - t0 < 5.0  # bounded by the probe timeout, not the 30s hang
