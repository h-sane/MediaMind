"""Tier-3 ("system" mode) discovery tally: `fixed_drive_roots` filtering and
the `folder_tally` upsert/suggestion logic. The "is this path under a
registered library" exclusion lives in `watcher.py` (it needs the live
registry), so that case is covered in `test_watcher.py` instead.
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

import pytest

from mediamind.core import discovery

_DRIVE_FIXED = 3
_DRIVE_REMOVABLE = 2
_DRIVE_REMOTE = 4


@pytest.mark.skipif(sys.platform != "win32", reason="patches the Windows drive-type API")
def test_fixed_drive_roots_filters_by_drive_type(monkeypatch):
    fixed = {"C:\\": _DRIVE_FIXED, "D:\\": _DRIVE_REMOVABLE, "Z:\\": _DRIVE_REMOTE}

    def fake_get_drive_type(root):
        return fixed.get(root, 1)  # DRIVE_UNKNOWN for anything else

    monkeypatch.setattr(ctypes.windll.kernel32, "GetDriveTypeW", fake_get_drive_type, raising=False)
    monkeypatch.setattr("sys.platform", "win32")

    roots = discovery.fixed_drive_roots()
    assert roots == ["C:\\"]


def test_record_and_list_suggestions_threshold(tmp_path: Path):
    folder = tmp_path / "Photos"
    folder.mkdir()
    conn = discovery.connect(tmp_path / "discovery.sqlite3")

    for _ in range(9):
        discovery.record(conn, str(folder))
    assert discovery.list_suggestions(conn, threshold=10) == []

    discovery.record(conn, str(folder))
    suggestions = discovery.list_suggestions(conn, threshold=10)
    assert len(suggestions) == 1
    assert suggestions[0]["folder"] == str(folder)
    assert suggestions[0]["media_count"] == 10


def test_dismissed_and_registered_drop_out(tmp_path: Path):
    folder = tmp_path / "Photos"
    folder.mkdir()
    conn = discovery.connect(tmp_path / "discovery.sqlite3")
    for _ in range(10):
        discovery.record(conn, str(folder))

    discovery.mark_dismissed(conn, str(folder))
    assert discovery.list_suggestions(conn, threshold=10) == []

    conn.execute("UPDATE folder_tally SET dismissed = 0 WHERE folder = ?", (str(folder),))
    conn.commit()
    discovery.mark_registered(conn, str(folder))
    assert discovery.list_suggestions(conn, threshold=10) == []


def test_inbox_suggestions_proactive_and_dismissable(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    (home / "Downloads" / "a.jpg").write_bytes(b"x")
    (home / "Downloads" / "b.png").write_bytes(b"y")
    (home / "Pictures").mkdir()  # exists but empty -> not suggested
    monkeypatch.setattr(discovery.Path, "home", classmethod(lambda cls: home))

    conn = discovery.connect(tmp_path / "discovery.sqlite3")
    sugg = discovery.list_inbox_suggestions(conn)
    folders = {s["folder"] for s in sugg}
    assert str(home / "Downloads") in folders
    assert str(home / "Pictures") not in folders  # empty
    assert next(s for s in sugg if s["folder"].endswith("Downloads"))["media_count"] == 2

    # Dismissing a never-tallied inbox must persist (upsert, not bare UPDATE).
    discovery.mark_dismissed(conn, str(home / "Downloads"))
    assert discovery.list_inbox_suggestions(conn) == []


def test_deleted_folder_is_not_suggested(tmp_path: Path):
    folder = tmp_path / "Gone"
    folder.mkdir()
    conn = discovery.connect(tmp_path / "discovery.sqlite3")
    for _ in range(10):
        discovery.record(conn, str(folder))
    assert len(discovery.list_suggestions(conn, threshold=10)) == 1

    folder.rmdir()
    assert discovery.list_suggestions(conn, threshold=10) == []
