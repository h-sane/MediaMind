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
