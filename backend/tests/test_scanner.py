from pathlib import Path

from mediamind.core.scanner import (
    KIND_GIF,
    KIND_IMAGE,
    KIND_OTHER,
    KIND_VIDEO,
    kind_of,
    scan_folder,
)


def test_kind_classification():
    assert kind_of(Path("a.JPG")) == KIND_IMAGE
    assert kind_of(Path("a.heic")) == KIND_IMAGE
    assert kind_of(Path("a.avif")) == KIND_IMAGE
    assert kind_of(Path("a.gif")) == KIND_GIF
    assert kind_of(Path("a.MP4")) == KIND_VIDEO
    assert kind_of(Path("a.mkv")) == KIND_VIDEO
    assert kind_of(Path("a.txt")) == KIND_OTHER
    assert kind_of(Path("noext")) == KIND_OTHER


def test_scan_finds_everything_recursively(media_library: Path):
    found = list(scan_folder(media_library))
    names = {f.path.name for f in found}
    assert "red3.jpg" in names  # nested
    assert "notes.txt" in names  # non-media still listed (routes to _others)
    assert len(found) == 9


def test_scan_non_recursive_skips_nested(media_library: Path):
    names = {f.path.name for f in scan_folder(media_library, recursive=False)}
    assert "red3.jpg" not in names
    assert "red1.jpg" in names


def test_scan_excludes_mediamind_dir(media_library: Path):
    hidden = media_library / ".mediamind"
    hidden.mkdir()
    (hidden / "index.db").write_bytes(b"db")
    names = {f.path.name for f in scan_folder(media_library)}
    assert "index.db" not in names


def test_scan_is_read_only(media_library: Path):
    before = sorted(p.name for p in media_library.rglob("*"))
    list(scan_folder(media_library))
    after = sorted(p.name for p in media_library.rglob("*"))
    assert before == after


def test_on_stat_reports_progress_with_real_total(media_library: Path):
    """The metadata-read phase (stat() per file, after the walk finishes) was
    previously invisible — no progress at all — which made a slow disk look
    identical to a hung scan. on_stat must report a real total, counting up
    to it exactly once per file."""
    calls: list[tuple[int, int]] = []
    found = list(scan_folder(media_library, on_stat=lambda done, total: calls.append((done, total))))
    assert len(found) == 9
    assert len(calls) == 9
    assert all(total == 9 for _done, total in calls)
    assert [done for done, _total in calls] == list(range(1, 10))


def test_stalled_file_stat_is_skipped_not_hung(media_library: Path, monkeypatch):
    """Bug reproduction: a single blocking stat() (cloud-sync placeholder,
    stalled network/encrypted-drive mount) must not freeze the whole scan —
    mirrors the same protection already proven for dedupe's file-hash
    timeout (core.dedupe.DEFAULT_FILE_TIMEOUT_SECONDS)."""
    import os
    import time

    real_stat = os.stat

    def slow_stat(path, *args, **kwargs):
        if os.fspath(path).endswith("red3.jpg"):
            time.sleep(10)  # far longer than the test's tiny stat_timeout_seconds
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", slow_stat)

    found = list(scan_folder(media_library, stat_timeout_seconds=0.2))
    names = {f.path.name for f in found}
    assert "red3.jpg" not in names
    assert len(found) == 8  # everything else still returned promptly


def test_stalled_directory_listing_is_skipped_not_hung(media_library: Path, monkeypatch):
    """Same bug class as the stat timeout above, but for a directory whose
    listing itself never returns (e.g. a hung network share) — previously
    this had no bound at all, since os.walk gives no per-directory hook."""
    import os
    import time

    real_scandir = os.scandir
    stalled_dir = str(media_library / "nested")

    def slow_scandir(path=".", *args, **kwargs):
        if os.fspath(path) == stalled_dir:
            time.sleep(10)  # far longer than the test's tiny walk_timeout_seconds
        return real_scandir(path, *args, **kwargs)

    monkeypatch.setattr(os, "scandir", slow_scandir)

    found = list(scan_folder(media_library, walk_timeout_seconds=0.2))
    names = {f.path.name for f in found}
    assert "red3.jpg" not in names  # inside the stalled directory
    assert len(found) == 8  # everything outside it still returned promptly
