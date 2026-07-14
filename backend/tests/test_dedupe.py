from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mediamind.core.dedupe import find_duplicates, group_signature
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


def test_best_copy_prefers_named_folder_over_generic_when_tied(tmp_path: Path):
    """Same pixels, same size, same mtime — only the folder name differs, and a
    named folder (e.g. a person's/group's name) should win over a generic
    placeholder folder (TEST*/TEMP*/Unknown/Unnamed/...)."""
    original = _noise_image(tmp_path / "TEST" / "photo.png", seed=5)
    named_copy = tmp_path / "Family Reunion" / "photo.png"
    named_copy.parent.mkdir()
    named_copy.write_bytes(original.read_bytes())
    # Keep mtimes identical so the folder-name tiebreak is the only signal
    # deciding the keeper, not the existing "oldest wins" fallback.
    import os

    st = original.stat()
    os.utime(named_copy, (st.st_atime, st.st_mtime))

    groups = _groups(tmp_path)
    group = next(g for g in groups if any(f.path.name == "photo.png" for f in g.files))
    best = [f for f in group.files if f.is_best]
    assert len(best) == 1
    assert best[0].path.parent.name == "Family Reunion"


def test_no_duplicates_no_groups(tmp_path: Path):
    _noise_image(tmp_path / "a.png", seed=10)
    _noise_image(tmp_path / "b.png", seed=20)
    assert _groups(tmp_path) == []


def test_detection_is_read_only(dup_library: Path):
    before = {p: p.stat().st_mtime for p in dup_library.rglob("*") if p.is_file()}
    _groups(dup_library)
    after = {p: p.stat().st_mtime for p in dup_library.rglob("*") if p.is_file()}
    assert before == after


def test_unique_size_files_skip_content_hash(dup_library: Path, monkeypatch):
    """Perf guard: a file whose size is unique in the library can never be a
    byte-exact duplicate, so it must never trigger a full-file hash read."""
    import mediamind.core.dedupe as dedupe_mod

    files = list(scan_folder(dup_library))
    sizes: dict[int, int] = {}
    for f in files:
        if f.is_media:
            sizes[f.size] = sizes.get(f.size, 0) + 1
    unique_size_paths = {f.path for f in files if f.is_media and sizes[f.size] == 1}
    assert unique_size_paths  # sanity: the fixture does contain a unique-size file (photo_small.jpg)

    real_hash_file = dedupe_mod.hash_file

    def guarded_hash_file(path: Path) -> str:
        assert path not in unique_size_paths, f"hash_file() called on unique-size file {path}"
        return real_hash_file(path)

    monkeypatch.setattr(dedupe_mod, "hash_file", guarded_hash_file)
    groups = find_duplicates(files)
    # Results must be unchanged by the optimization.
    photo_group = next(g for g in groups if any(f.path.name == "photo.png" for f in g.files))
    assert {f.path.name for f in photo_group.files} == {"photo.png", "photo_copy.png", "photo_small.jpg"}


def test_many_same_size_files_group_correctly(tmp_path: Path):
    """Alignment guard: every file shares one byte size, so all of them are
    hashed concurrently on the thread pool — each pair must still resolve to
    exactly its own group (a completion-order bug would mismatch path/hash
    pairs and scramble the groups)."""
    for n in range(10):
        payload = bytes([n]) * 4096
        (tmp_path / f"clip{n}.mp4").write_bytes(payload)
        (tmp_path / f"clip{n}_copy.mp4").write_bytes(payload)

    groups = _groups(tmp_path)
    got = {frozenset(f.path.name for f in g.files) for g in groups}
    want = {frozenset({f"clip{n}.mp4", f"clip{n}_copy.mp4"}) for n in range(10)}
    assert got == want


def test_stalled_file_is_skipped_not_hung(dup_library: Path, monkeypatch):
    """Bug reproduction: a single blocking read (cloud-sync placeholder,
    stalled network/encrypted-drive mount) must not freeze the whole scan.
    hash_file() only runs for files sharing a size, so make clip.mp4's
    "read" hang forever and confirm find_duplicates() still returns promptly
    by skipping it, instead of hanging forever."""
    import time

    import mediamind.core.dedupe as dedupe_mod

    real_hash_file = dedupe_mod.hash_file

    def hanging_hash_file(path: Path) -> str:
        if path.name == "clip.mp4":
            time.sleep(10)  # far longer than the test's tiny file_timeout_seconds
        return real_hash_file(path)

    monkeypatch.setattr(dedupe_mod, "hash_file", hanging_hash_file)

    files = list(scan_folder(dup_library))
    groups = find_duplicates(files, file_timeout_seconds=0.2)

    # The stalled file never joins a group (skipped, not waited-for-forever).
    for g in groups:
        assert "clip.mp4" not in {f.path.name for f in g.files}
    # Its (unaffected) duplicate pair partner is also absent — a group needs 2+.
    for g in groups:
        assert "clip_copy.mp4" not in {f.path.name for f in g.files}
    # Everything else still resolved normally in the same call.
    photo_group = next(g for g in groups if any(f.path.name == "photo.png" for f in g.files))
    assert {f.path.name for f in photo_group.files} == {"photo.png", "photo_copy.png", "photo_small.jpg"}


def test_many_simultaneous_stalls_dont_hang_or_crash(tmp_path: Path, monkeypatch):
    """Regression: a chronically wedged mount can stall many files at once,
    not just one. Each stall leaks a watchdog thread that never returns
    (Python can't kill it) — without a cap, that grows without bound and can
    eventually crash the scan when the OS refuses to hand out more threads.
    With the cap, stalls beyond the limit fail fast instead of piling on, and
    the whole call still returns promptly."""
    import time

    import mediamind.core.dedupe as dedupe_mod

    monkeypatch.setattr(dedupe_mod, "MAX_LEAKED_STALL_THREADS", 3)

    real_hash_file = dedupe_mod.hash_file

    def hanging_hash_file(path: Path) -> str:
        if path.name.startswith("clip"):
            time.sleep(10)  # far longer than the test's tiny file_timeout_seconds
        return real_hash_file(path)

    monkeypatch.setattr(dedupe_mod, "hash_file", hanging_hash_file)

    payload = b"fake video bytes" * 100
    for n in range(6):
        (tmp_path / f"clip{n}.mp4").write_bytes(payload)

    files = list(scan_folder(tmp_path))
    started = time.monotonic()
    groups = find_duplicates(files, file_timeout_seconds=0.2)
    elapsed = time.monotonic() - started

    # All six stall, but only 3 (the cap) ever wait out the real 0.2s
    # timeout — the rest fail fast without spawning a thread at all, so this
    # returns in roughly one timeout window, not six.
    assert elapsed < 2.0
    assert groups == []  # every file skipped; none can group


def test_non_os_error_during_hash_is_skipped_not_fatal(dup_library: Path, monkeypatch):
    """Safety invariant (CLAUDE.md): one bad file must never crash a run.
    Only OSError was previously guarded against; anything else (e.g. a
    thread-creation failure once many stalls have already leaked threads)
    used to propagate and fail the whole scan."""
    import mediamind.core.dedupe as dedupe_mod

    real_hash_file = dedupe_mod.hash_file

    def flaky_hash_file(path: Path) -> str:
        if path.name == "clip.mp4":
            raise RuntimeError("simulated non-OSError failure")
        return real_hash_file(path)

    monkeypatch.setattr(dedupe_mod, "hash_file", flaky_hash_file)

    files = list(scan_folder(dup_library))
    groups = find_duplicates(files)  # must not raise

    for g in groups:
        assert "clip.mp4" not in {f.path.name for f in g.files}
    photo_group = next(g for g in groups if any(f.path.name == "photo.png" for f in g.files))
    assert {f.path.name for f in photo_group.files} == {"photo.png", "photo_copy.png", "photo_small.jpg"}


def test_group_signature_stable_across_scans_with_unrelated_file_churn(dup_library: Path):
    """Regression: photo_small.jpg is unique-size (a sentinel-hash member,
    since it joins the group only via a phash edge) — its group_signature()
    must stay identical across scans even when unrelated files are
    added/removed elsewhere, since the sentinel hash is only guaranteed
    unique *within* one scan's positional ordering, not across scans."""

    def photo_signature() -> str:
        groups = _groups(dup_library)
        photo_group = next(g for g in groups if any(f.path.name == "photo.png" for f in g.files))
        assert photo_group.match == "near"
        assert any(f.content_hash.startswith("\x00uniq:") for f in photo_group.files)
        return group_signature([f.identity for f in photo_group.files])

    sig_before = photo_signature()

    extra = dup_library / "aaa_unrelated_extra.bin"
    extra.write_bytes(b"unrelated churn bytes")
    assert photo_signature() == sig_before

    extra.unlink()
    assert photo_signature() == sig_before


def test_cancel_stops_cleanly(dup_library: Path):
    calls = {"n": 0}

    def cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 2

    result = find_duplicates(list(scan_folder(dup_library)), should_cancel=cancel)
    assert result == []  # canceled scan returns nothing and touched nothing
