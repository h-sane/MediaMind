from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mediamind.core.dedupe import find_duplicates
from mediamind.core.scanner import scan_folder


def _noise_image(path: Path, seed: int, size: tuple[int, int] = (128, 128)) -> Path:
    """Distinct, non-uniform test image (pHash needs texture to discriminate)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
    Image.fromarray(arr).save(path)
    return path


@pytest.fixture
def dup_library(tmp_path: Path) -> Path:
    original = _noise_image(tmp_path / "photo.png", seed=1)

    # exact duplicate in a subfolder (byte-identical)
    copy = tmp_path / "backup" / "photo_copy.png"
    copy.parent.mkdir()
    copy.write_bytes(original.read_bytes())

    # near duplicate: same image, resized and re-encoded as JPEG
    with Image.open(original) as im:
        im.resize((96, 96)).save(tmp_path / "photo_small.jpg", quality=90)

    # unrelated image — must NOT group
    _noise_image(tmp_path / "other.png", seed=2)

    # exact duplicate pair of "videos" (byte-identical, exact matching only)
    (tmp_path / "clip.mp4").write_bytes(b"fake video bytes" * 100)
    (tmp_path / "clip_copy.mp4").write_bytes(b"fake video bytes" * 100)
    return tmp_path


def _groups(library: Path):
    return find_duplicates(list(scan_folder(library)))


def test_exact_and_near_duplicates_group_together(dup_library: Path):
    groups = _groups(dup_library)
    photo_group = next(g for g in groups if any(f.path.name == "photo.png" for f in g.files))
    names = {f.path.name for f in photo_group.files}
    assert names == {"photo.png", "photo_copy.png", "photo_small.jpg"}
    assert photo_group.match == "near"  # includes a non-byte-identical member


def test_videos_match_byte_exact(dup_library: Path):
    groups = _groups(dup_library)
    clip_group = next(g for g in groups if any(f.path.name == "clip.mp4" for f in g.files))
    assert {f.path.name for f in clip_group.files} == {"clip.mp4", "clip_copy.mp4"}
    assert clip_group.match == "exact"


def test_unrelated_image_not_grouped(dup_library: Path):
    groups = _groups(dup_library)
    for g in groups:
        assert "other.png" not in {f.path.name for f in g.files}


def test_best_copy_is_highest_resolution(dup_library: Path):
    groups = _groups(dup_library)
    photo_group = next(g for g in groups if any(f.path.name == "photo.png" for f in g.files))
    best = [f for f in photo_group.files if f.is_best]
    assert len(best) == 1  # exactly one keeper per group
    assert best[0].path.name in ("photo.png", "photo_copy.png")  # 128px beats 96px
    assert photo_group.files[0].is_best  # keeper is listed first


def test_no_duplicates_no_groups(tmp_path: Path):
    _noise_image(tmp_path / "a.png", seed=10)
    _noise_image(tmp_path / "b.png", seed=20)
    assert _groups(tmp_path) == []


def test_detection_is_read_only(dup_library: Path):
    before = {p: p.stat().st_mtime for p in dup_library.rglob("*") if p.is_file()}
    _groups(dup_library)
    after = {p: p.stat().st_mtime for p in dup_library.rglob("*") if p.is_file()}
    assert before == after


def test_cancel_stops_cleanly(dup_library: Path):
    calls = {"n": 0}

    def cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 2

    result = find_duplicates(list(scan_folder(dup_library)), should_cancel=cancel)
    assert result == []  # canceled scan returns nothing and touched nothing
