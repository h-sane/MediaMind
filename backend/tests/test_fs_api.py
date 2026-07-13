"""Tests for the Explorer shell's whole-filesystem browsing (M12):
path safety beyond a single library root, and the lazy has-media cache.

Invariants under test:
- resolve_os_path only accepts real, absolute, existing paths, collapses
  `..`, and rejects anything inside MediaMind's own app data or a
  `.mediamind` folder
- MediaIndex reports unknown on first look, resolves in the background, and
  self-invalidates when a directory's own contents change
- /v1/fs/list only ever returns media files and folders that contain media
  somewhere below them, plus folders that are empty of files entirely
  (structure, not junk); /v1/fs/thumbnail and /v1/fs/raw work by absolute path
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mediamind.api.app import create_app
from mediamind.config import app_data_dir
from mediamind.core.media_index import MediaIndex
from mediamind.core.pathsafe import resolve_os_path

JPEG_MAGIC = b"\xff\xd8"


def _wait_for_resolution(index: MediaIndex, path: Path, timeout: float = 2.0) -> bool | None:
    deadline = time.time() + timeout
    result = index.check(path)
    while result is None and time.time() < deadline:
        time.sleep(0.02)
        result = index.check(path)
    return result


def _wait_for_full_resolution(index: MediaIndex, path: Path, timeout: float = 2.0):
    deadline = time.time() + timeout
    result = index.check_full(path)
    while result is None and time.time() < deadline:
        time.sleep(0.02)
        result = index.check_full(path)
    return result


# ---------------------------------------------------------------------------
# resolve_os_path
# ---------------------------------------------------------------------------

def test_resolve_os_path_rejects_relative(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    assert resolve_os_path("relative/path") is None
    assert resolve_os_path("") is None


def test_resolve_os_path_rejects_nonexistent(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    assert resolve_os_path(str(tmp_path / "does-not-exist")) is None


def test_resolve_os_path_accepts_real_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    real = tmp_path / "photos"
    real.mkdir()
    assert resolve_os_path(str(real)) == real.resolve()


def test_resolve_os_path_collapses_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    (tmp_path / "photos").mkdir()
    (tmp_path / "other").mkdir()
    sneaky = tmp_path / "other" / ".." / "photos"
    assert resolve_os_path(str(sneaky)) == (tmp_path / "photos").resolve()


def test_resolve_os_path_rejects_app_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    data_dir = app_data_dir()  # created on demand
    assert resolve_os_path(str(data_dir)) is None
    nested = data_dir / "models"
    nested.mkdir(parents=True, exist_ok=True)
    assert resolve_os_path(str(nested)) is None


def test_resolve_os_path_rejects_mediamind_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    lib_data = tmp_path / "photos" / ".mediamind"
    lib_data.mkdir(parents=True)
    assert resolve_os_path(str(lib_data)) is None


# ---------------------------------------------------------------------------
# MediaIndex — lazy has-media cache
# ---------------------------------------------------------------------------

def test_media_index_unknown_then_resolves_true(tmp_path):
    root = tmp_path / "folder"
    root.mkdir()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(root / "photo.jpg")

    index = MediaIndex(tmp_path / "index.sqlite3")
    assert index.check(root) is None  # unknown on first look, walk scheduled
    assert _wait_for_resolution(index, root) is True


def test_media_index_resolves_true_for_audio_only_folder(tmp_path):
    """Explorer-only audio support: a folder containing only audio must not
    be treated as junk and hidden from the listing."""
    root = tmp_path / "audio_only"
    root.mkdir()
    (root / "song.mp3").write_bytes(b"fake mp3 bytes")

    index = MediaIndex(tmp_path / "index.sqlite3")
    assert _wait_for_resolution(index, root) is True


def test_media_index_resolves_false_for_non_media_folder(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    (root / "notes.txt").write_text("not media")

    index = MediaIndex(tmp_path / "index.sqlite3")
    assert _wait_for_resolution(index, root) is False


def test_media_index_skips_noise_dirs(tmp_path):
    root = tmp_path / "folder"
    (root / "node_modules").mkdir(parents=True)
    Image.new("RGB", (8, 8), (0, 255, 0)).save(root / "node_modules" / "hidden.jpg")

    index = MediaIndex(tmp_path / "index.sqlite3")
    assert _wait_for_resolution(index, root) is False  # media only inside a skipped dir


def test_media_index_cache_hit_is_instant(tmp_path):
    root = tmp_path / "folder"
    root.mkdir()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(root / "photo.jpg")

    index = MediaIndex(tmp_path / "index.sqlite3")
    assert _wait_for_resolution(index, root) is True
    assert index.check(root) is True  # second call hits the cache synchronously


def test_media_index_invalidates_on_dir_change(tmp_path):
    root = tmp_path / "folder"
    root.mkdir()
    (root / "notes.txt").write_text("not media")

    index = MediaIndex(tmp_path / "index.sqlite3")
    assert _wait_for_resolution(index, root) is False

    time.sleep(0.05)  # ensure the mtime actually advances
    Image.new("RGB", (8, 8), (0, 0, 255)).save(root / "photo.jpg")
    assert index.check(root) is None  # directory's own mtime changed -> stale
    assert _wait_for_resolution(index, root) is True


def test_media_index_truly_empty_folder_has_no_files(tmp_path):
    root = tmp_path / "brand_new_folder"
    root.mkdir()

    index = MediaIndex(tmp_path / "index.sqlite3")
    status = _wait_for_full_resolution(index, root)
    assert status is not None
    assert status.has_media is False
    assert status.has_any_file is False  # pure structure, not junk


def test_media_index_nested_empty_folders_have_no_files(tmp_path):
    root = tmp_path / "outer"
    (root / "inner").mkdir(parents=True)

    index = MediaIndex(tmp_path / "index.sqlite3")
    status = _wait_for_full_resolution(index, root)
    assert status is not None
    assert status.has_media is False
    assert status.has_any_file is False  # only nested empty folders, still not junk


def test_media_index_junk_only_folder_has_any_file_true(tmp_path):
    root = tmp_path / "junk"
    root.mkdir()
    (root / "notes.txt").write_text("not media")

    index = MediaIndex(tmp_path / "index.sqlite3")
    status = _wait_for_full_resolution(index, root)
    assert status is not None
    assert status.has_media is False
    assert status.has_any_file is True  # confirmed junk: has files, none of them media


def test_media_index_migrates_pre_has_any_file_schema(tmp_path):
    """A DB created before has_any_file existed must not crash on open."""
    db_path = tmp_path / "old_index.sqlite3"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE dir_media (
                path TEXT PRIMARY KEY,
                has_media INTEGER NOT NULL,
                dir_mtime_ns INTEGER NOT NULL,
                checked_at REAL NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    index = MediaIndex(db_path)  # must not raise
    root = tmp_path / "folder"
    root.mkdir()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(root / "photo.jpg")
    status = _wait_for_full_resolution(index, root)
    assert status is not None
    assert status.has_media is True


# ---------------------------------------------------------------------------
# FolderStatsIndex — lazy recursive count/size cache (M12 Phase E)
# ---------------------------------------------------------------------------

def _wait_for_folder_stats(index, path: Path, timeout: float = 2.0):
    deadline = time.time() + timeout
    result = index.check_full(path)
    while result is None and time.time() < deadline:
        time.sleep(0.02)
        result = index.check_full(path)
    return result


def test_folder_stats_counts_only_media_and_sums_bytes(tmp_path):
    from mediamind.core.folder_stats import FolderStatsIndex

    root = tmp_path / "stats"
    (root / "sub").mkdir(parents=True)
    Image.new("RGB", (8, 8), (255, 0, 0)).save(root / "a.jpg")
    Image.new("RGB", (8, 8), (0, 255, 0)).save(root / "sub" / "b.jpg")
    (root / "notes.txt").write_text("not media")

    index = FolderStatsIndex(tmp_path / "folder_stats.sqlite3")
    stats = _wait_for_folder_stats(index, root)
    assert stats is not None
    assert stats.item_count == 2  # notes.txt excluded
    assert stats.total_bytes > 0


def test_folder_stats_counts_audio_files(tmp_path):
    from mediamind.core.folder_stats import FolderStatsIndex

    root = tmp_path / "stats_audio"
    root.mkdir()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(root / "a.jpg")
    (root / "song.mp3").write_bytes(b"fake mp3 bytes")
    (root / "notes.txt").write_text("not media")

    index = FolderStatsIndex(tmp_path / "folder_stats.sqlite3")
    stats = _wait_for_folder_stats(index, root)
    assert stats is not None
    assert stats.item_count == 2  # notes.txt excluded, song.mp3 included


def test_folder_stats_skips_noise_dirs(tmp_path):
    from mediamind.core.folder_stats import FolderStatsIndex

    root = tmp_path / "stats_noise"
    (root / "node_modules").mkdir(parents=True)
    Image.new("RGB", (8, 8), (0, 0, 255)).save(root / "node_modules" / "hidden.jpg")

    index = FolderStatsIndex(tmp_path / "folder_stats.sqlite3")
    stats = _wait_for_folder_stats(index, root)
    assert stats is not None
    assert stats.item_count == 0


def test_folder_stats_invalidates_on_dir_change(tmp_path):
    from mediamind.core.folder_stats import FolderStatsIndex

    root = tmp_path / "stats_change"
    root.mkdir()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(root / "a.jpg")

    index = FolderStatsIndex(tmp_path / "folder_stats.sqlite3")
    stats = _wait_for_folder_stats(index, root)
    assert stats.item_count == 1

    time.sleep(0.05)  # ensure the mtime actually advances
    Image.new("RGB", (8, 8), (0, 255, 0)).save(root / "b.jpg")
    assert index.check_full(root) is None  # stale after the directory changed
    stats = _wait_for_folder_stats(index, root)
    assert stats.item_count == 2


# ---------------------------------------------------------------------------
# file_facts — OS-level facts, never raises (M12 Phase E)
# ---------------------------------------------------------------------------

def test_file_facts_never_raises_on_real_file(tmp_path):
    from mediamind.core.file_facts import file_facts

    f = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(f)

    facts = file_facts(f)  # must not raise regardless of platform
    assert facts.created is None or facts.created > 0


def test_file_facts_never_raises_on_missing_file(tmp_path):
    from mediamind.core.file_facts import file_facts

    facts = file_facts(tmp_path / "does-not-exist.jpg")
    assert facts == (None, None, None, None, None, None)


# ---------------------------------------------------------------------------
# /v1/fs API
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app()) as c:
        yield c


def test_fs_drives_nonempty(client: TestClient):
    res = client.get("/v1/fs/drives")
    assert res.status_code == 200
    drives = res.json()
    assert len(drives) >= 1
    assert all("path" in d and "label" in d for d in drives)


def test_fs_list_media_only(client: TestClient, tmp_path: Path):
    root = tmp_path / "browse_target"
    (root / "sub").mkdir(parents=True)
    Image.new("RGB", (8, 8), (255, 0, 0)).save(root / "photo.jpg")
    (root / "notes.txt").write_text("not media")

    res = client.get("/v1/fs/list", params={"path": str(root)})
    assert res.status_code == 200
    body = res.json()
    assert {f["name"] for f in body["files"]} == {"photo.jpg"}  # notes.txt hidden
    assert any(f["name"] == "sub" for f in body["folders"])


def test_fs_list_includes_audio_files(client: TestClient, tmp_path: Path):
    """Explorer-only audio support: audio is a recognized kind for browsing/
    search/preview (`core/explorer_media.py`), even though the scan/dedupe
    face pipeline (`core/scanner.py`) never treats audio as media."""
    root = tmp_path / "browse_target_audio"
    root.mkdir()
    (root / "song.mp3").write_bytes(b"fake mp3 bytes")
    (root / "notes.txt").write_text("not media")

    res = client.get("/v1/fs/list", params={"path": str(root)})
    assert res.status_code == 200
    body = res.json()
    assert {f["name"] for f in body["files"]} == {"song.mp3"}
    file_entry = next(f for f in body["files"] if f["name"] == "song.mp3")
    assert file_entry["kind"] == "audio"


def test_fs_list_includes_created_and_attributes(client: TestClient, tmp_path: Path):
    """Details-column widening (Phase G): `created`/attribute facts come for
    free from the same `stat()` files/folders already need — no extra
    request, unlike the owner lookup which stays Properties-dialog-only."""
    root = tmp_path / "browse_target_facts"
    root.mkdir()
    (root / "sub").mkdir()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(root / "photo.jpg")

    res = client.get("/v1/fs/list", params={"path": str(root)})
    assert res.status_code == 200
    body = res.json()

    file_entry = next(f for f in body["files"] if f["name"] == "photo.jpg")
    assert file_entry["created"] is not None
    assert file_entry["accessed"] is not None
    assert file_entry["read_only"] is False
    assert file_entry["hidden"] is False

    folder_entry = next(f for f in body["folders"] if f["name"] == "sub")
    assert folder_entry["mtime"] > 0  # folders never had this at all before Phase G
    assert folder_entry["created"] is not None
    assert folder_entry["accessed"] is not None
    assert folder_entry["read_only"] is False
    assert folder_entry["hidden"] is False


def test_fs_list_keeps_empty_folder_visible_after_resolution(
    client: TestClient, tmp_path: Path
):
    """A brand-new empty folder (e.g. from the "New Folder" action) must not
    vanish once its background has-media walk resolves — it has structure,
    not junk. Regression test for the Phase B / Phase C empty-folder gap."""
    root = tmp_path / "browse_target_empty"
    root.mkdir()
    (root / "brand_new").mkdir()

    # Poll /v1/fs/list until the background walk has actually resolved
    # brand_new's status (has_media no longer null), the same way the
    # frontend's refetchInterval does.
    deadline = time.time() + 2.0
    body = None
    while time.time() < deadline:
        res = client.get("/v1/fs/list", params={"path": str(root)})
        assert res.status_code == 200
        body = res.json()
        entry = next((f for f in body["folders"] if f["name"] == "brand_new"), None)
        if entry is not None and entry["has_media"] is not None:
            break
        time.sleep(0.02)

    assert body is not None
    entry = next((f for f in body["folders"] if f["name"] == "brand_new"), None)
    assert entry is not None, "empty folder disappeared from the listing"
    assert entry["has_media"] is False


def test_fs_list_omits_folder_with_only_non_media_junk(client: TestClient, tmp_path: Path):
    root = tmp_path / "browse_target_junk"
    root.mkdir()
    (root / "junk_only").mkdir()
    (root / "junk_only" / "notes.txt").write_text("not media")

    deadline = time.time() + 2.0
    body = None
    while time.time() < deadline:
        res = client.get("/v1/fs/list", params={"path": str(root)})
        assert res.status_code == 200
        body = res.json()
        if not any(f["name"] == "junk_only" and f["has_media"] is None for f in body["folders"]):
            break
        time.sleep(0.02)

    assert body is not None
    assert not any(f["name"] == "junk_only" for f in body["folders"])


def test_fs_list_rejects_relative_path(client: TestClient):
    assert client.get("/v1/fs/list", params={"path": "relative"}).status_code == 404


def test_fs_list_rejects_nonexistent_path(client: TestClient, tmp_path: Path):
    res = client.get("/v1/fs/list", params={"path": str(tmp_path / "nope")})
    assert res.status_code == 404


def test_fs_thumbnail_and_raw_by_path(client: TestClient, tmp_path: Path):
    root = tmp_path / "browse_target2"
    root.mkdir()
    Image.new("RGB", (16, 16), (0, 255, 0)).save(root / "photo.jpg")

    res = client.get("/v1/fs/thumbnail", params={"path": str(root / "photo.jpg")})
    assert res.status_code == 200
    assert res.content.startswith(JPEG_MAGIC)

    res = client.get("/v1/fs/raw", params={"path": str(root / "photo.jpg")})
    assert res.status_code == 200


def test_fs_thumbnail_rejects_non_media(client: TestClient, tmp_path: Path):
    root = tmp_path / "browse_target3"
    root.mkdir()
    (root / "notes.txt").write_text("not media")
    res = client.get("/v1/fs/thumbnail", params={"path": str(root / "notes.txt")})
    assert res.status_code == 422


def test_fs_thumbnail_rejects_audio(client: TestClient, tmp_path: Path):
    """Audio streams via /raw for inline playback, but has no visual frame to
    thumbnail — /thumbnail stays image/gif/video-only."""
    root = tmp_path / "browse_target_audio_thumb"
    root.mkdir()
    (root / "song.mp3").write_bytes(b"fake mp3 bytes")
    res = client.get("/v1/fs/thumbnail", params={"path": str(root / "song.mp3")})
    assert res.status_code == 422


def test_fs_raw_serves_audio(client: TestClient, tmp_path: Path):
    root = tmp_path / "browse_target_audio_raw"
    root.mkdir()
    (root / "song.mp3").write_bytes(b"fake mp3 bytes")
    res = client.get("/v1/fs/raw", params={"path": str(root / "song.mp3")})
    assert res.status_code == 200
    assert res.content == b"fake mp3 bytes"


# ---------------------------------------------------------------------------
# /v1/fs/metadata (M12 Phase C — preview pane)
# ---------------------------------------------------------------------------

def test_fs_metadata_image_dimensions(client: TestClient, tmp_path: Path):
    root = tmp_path / "meta_target"
    root.mkdir()
    Image.new("RGB", (32, 24), (255, 0, 0)).save(root / "photo.jpg")

    res = client.get("/v1/fs/metadata", params={"path": str(root / "photo.jpg")})
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "image"
    assert body["width"] == 32
    assert body["height"] == 24
    assert body["duration_seconds"] is None
    assert body["name"] == "photo.jpg"


def test_fs_metadata_audio_kind_has_no_dimensions_or_duration(client: TestClient, tmp_path: Path):
    root = tmp_path / "meta_target_audio"
    root.mkdir()
    (root / "song.mp3").write_bytes(b"fake mp3 bytes")

    res = client.get("/v1/fs/metadata", params={"path": str(root / "song.mp3")})
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "audio"
    assert body["width"] is None
    assert body["height"] is None
    assert body["duration_seconds"] is None


def test_fs_metadata_rejects_non_media(client: TestClient, tmp_path: Path):
    root = tmp_path / "meta_target2"
    root.mkdir()
    (root / "notes.txt").write_text("not media")
    res = client.get("/v1/fs/metadata", params={"path": str(root / "notes.txt")})
    assert res.status_code == 422


def test_fs_metadata_rejects_missing_file(client: TestClient, tmp_path: Path):
    res = client.get("/v1/fs/metadata", params={"path": str(tmp_path / "nope.jpg")})
    assert res.status_code == 404


def test_fs_metadata_video_dimensions_and_duration(client: TestClient, tmp_path: Path):
    import cv2
    import numpy as np

    root = tmp_path / "meta_target_video"
    root.mkdir()
    out = root / "clip.mp4"
    fps = 10
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 48))
    if not writer.isOpened():
        pytest.skip("no mp4 codec available in this OpenCV build")
    for _ in range(20):
        writer.write(np.full((48, 64, 3), 128, dtype=np.uint8))
    writer.release()

    res = client.get("/v1/fs/metadata", params={"path": str(out)})
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "video"
    assert body["width"] == 64
    assert body["height"] == 48
    assert body["duration_seconds"] is not None
    assert body["duration_seconds"] > 0


def test_fs_metadata_includes_os_facts(client: TestClient, tmp_path: Path):
    """M12 Phase E: metadata carries created/attributes/owner facts alongside
    the pixel-derived width/height/duration. Every field is best-effort — the
    contract under test is "the keys exist and don't error", not exact OS
    values, since attributes/owner are platform-dependent."""
    root = tmp_path / "meta_target_facts"
    root.mkdir()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(root / "photo.jpg")

    res = client.get("/v1/fs/metadata", params={"path": str(root / "photo.jpg")})
    assert res.status_code == 200
    body = res.json()
    for key in ("created", "read_only", "hidden", "system", "owner"):
        assert key in body
    assert body["created"] is None or body["created"] > 0


# ---------------------------------------------------------------------------
# /v1/fs/folder-stats and /v1/fs/disk-usage (M12 Phase E)
# ---------------------------------------------------------------------------

def test_fs_folder_stats_unknown_then_resolves(client: TestClient, tmp_path: Path):
    root = tmp_path / "stats_target"
    root.mkdir()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(root / "a.jpg")
    Image.new("RGB", (8, 8), (0, 255, 0)).save(root / "b.jpg")
    (root / "notes.txt").write_text("not media")  # excluded from the count

    deadline = time.time() + 2.0
    body = None
    while time.time() < deadline:
        res = client.get("/v1/fs/folder-stats", params={"path": str(root)})
        assert res.status_code == 200
        body = res.json()
        if body["item_count"] is not None:
            break
        time.sleep(0.02)

    assert body is not None
    assert body["item_count"] == 2
    assert body["total_bytes"] > 0


def test_fs_folder_stats_rejects_missing_folder(client: TestClient, tmp_path: Path):
    res = client.get("/v1/fs/folder-stats", params={"path": str(tmp_path / "nope")})
    assert res.status_code == 404


def test_fs_disk_usage_reports_positive_totals(client: TestClient, tmp_path: Path):
    folder = tmp_path / "disk_target"
    folder.mkdir()
    res = client.get("/v1/fs/disk-usage", params={"path": str(folder)})
    assert res.status_code == 200
    body = res.json()
    assert body["total_bytes"] > 0
    assert body["free_bytes"] >= 0
    assert body["used_bytes"] >= 0


def test_fs_disk_usage_rejects_missing_path(client: TestClient, tmp_path: Path):
    res = client.get("/v1/fs/disk-usage", params={"path": str(tmp_path / "nope")})
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# /v1/fs/quick-access (M12 Phase C)
# ---------------------------------------------------------------------------

def test_fs_quick_access_empty_by_default(client: TestClient):
    res = client.get("/v1/fs/quick-access")
    assert res.status_code == 200
    assert res.json() == {"pins": []}


def test_fs_quick_access_pin_and_list(client: TestClient, tmp_path: Path):
    folder = tmp_path / "pinned_folder"
    folder.mkdir()

    res = client.post("/v1/fs/quick-access", json={"path": str(folder)})
    assert res.status_code == 200
    pins = res.json()["pins"]
    assert len(pins) == 1
    assert pins[0]["name"] == "pinned_folder"
    assert Path(pins[0]["path"]) == folder.resolve()

    res = client.get("/v1/fs/quick-access")
    assert res.json()["pins"] == pins


def test_fs_quick_access_pin_is_idempotent(client: TestClient, tmp_path: Path):
    folder = tmp_path / "pinned_folder2"
    folder.mkdir()

    client.post("/v1/fs/quick-access", json={"path": str(folder)})
    res = client.post("/v1/fs/quick-access", json={"path": str(folder)})
    assert len(res.json()["pins"]) == 1


def test_fs_quick_access_pin_rejects_missing_folder(client: TestClient, tmp_path: Path):
    res = client.post("/v1/fs/quick-access", json={"path": str(tmp_path / "nope")})
    assert res.status_code == 404


def test_fs_quick_access_unpin(client: TestClient, tmp_path: Path):
    folder = tmp_path / "pinned_folder3"
    folder.mkdir()

    pin_res = client.post("/v1/fs/quick-access", json={"path": str(folder)})
    pinned_path = pin_res.json()["pins"][0]["path"]

    res = client.request("DELETE", "/v1/fs/quick-access", params={"path": pinned_path})
    assert res.status_code == 200
    assert res.json()["pins"] == []


def test_fs_quick_access_reorder(client: TestClient, tmp_path: Path):
    a = tmp_path / "pin_a"
    b = tmp_path / "pin_b"
    c = tmp_path / "pin_c"
    for f in (a, b, c):
        f.mkdir()
        client.post("/v1/fs/quick-access", json={"path": str(f)})

    pins = client.get("/v1/fs/quick-access").json()["pins"]
    ordered_paths = [p["path"] for p in pins]
    assert [Path(p).name for p in ordered_paths] == ["pin_a", "pin_b", "pin_c"]

    reordered = [ordered_paths[2], ordered_paths[0], ordered_paths[1]]
    res = client.put("/v1/fs/quick-access/reorder", json={"paths": reordered})
    assert res.status_code == 200
    assert [p["path"] for p in res.json()["pins"]] == reordered

    # Persists — a plain GET afterwards reflects the new order too.
    res = client.get("/v1/fs/quick-access")
    assert [p["path"] for p in res.json()["pins"]] == reordered


def test_fs_quick_access_reorder_ignores_unknown_paths(client: TestClient, tmp_path: Path):
    folder = tmp_path / "pin_only"
    folder.mkdir()
    client.post("/v1/fs/quick-access", json={"path": str(folder)})
    pinned_path = client.get("/v1/fs/quick-access").json()["pins"][0]["path"]

    res = client.put(
        "/v1/fs/quick-access/reorder",
        json={"paths": [str(tmp_path / "never_pinned"), pinned_path]},
    )
    assert res.status_code == 200
    assert [p["path"] for p in res.json()["pins"]] == [pinned_path]


# ---------------------------------------------------------------------------
# /v1/fs/recent — recently-opened files (Home page, Phase N)
# ---------------------------------------------------------------------------

def test_fs_recent_empty_by_default(client: TestClient):
    res = client.get("/v1/fs/recent")
    assert res.status_code == 200
    assert res.json() == {"files": []}


def test_fs_recent_record_and_list(client: TestClient, tmp_path: Path):
    folder = tmp_path / "recent_target"
    folder.mkdir()
    photo = folder / "photo.jpg"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(photo)

    res = client.post("/v1/fs/recent", json={"path": str(photo)})
    assert res.status_code == 200
    files = res.json()["files"]
    assert len(files) == 1
    assert files[0]["name"] == "photo.jpg"
    assert files[0]["kind"] == "image"
    assert Path(files[0]["path"]) == photo.resolve()

    res = client.get("/v1/fs/recent")
    assert res.json()["files"] == files


def test_fs_recent_reopen_moves_to_front_without_duplicating(client: TestClient, tmp_path: Path):
    folder = tmp_path / "recent_mru"
    folder.mkdir()
    first = folder / "first.jpg"
    second = folder / "second.jpg"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(first)
    Image.new("RGB", (8, 8), (0, 0, 255)).save(second)

    client.post("/v1/fs/recent", json={"path": str(first)})
    client.post("/v1/fs/recent", json={"path": str(second)})
    res = client.post("/v1/fs/recent", json={"path": str(first)})

    names = [f["name"] for f in res.json()["files"]]
    assert names == ["first.jpg", "second.jpg"]  # first re-opened -> moved to front, not duplicated


def test_fs_recent_record_rejects_non_media_file(client: TestClient, tmp_path: Path):
    doc = tmp_path / "notes.txt"
    doc.write_text("not media")
    res = client.post("/v1/fs/recent", json={"path": str(doc)})
    assert res.status_code == 422


def test_fs_recent_record_rejects_missing_file(client: TestClient, tmp_path: Path):
    res = client.post("/v1/fs/recent", json={"path": str(tmp_path / "nope.jpg")})
    assert res.status_code == 404


def test_fs_recent_hides_deleted_file(client: TestClient, tmp_path: Path):
    folder = tmp_path / "recent_deleted"
    folder.mkdir()
    photo = folder / "gone.jpg"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(photo)

    client.post("/v1/fs/recent", json={"path": str(photo)})
    photo.unlink()

    res = client.get("/v1/fs/recent")
    assert res.status_code == 200
    assert res.json()["files"] == []


# ---------------------------------------------------------------------------
# /v1/fs/settings — Folder Options (Privacy: Recent files toggle)
# ---------------------------------------------------------------------------

def test_fs_settings_recent_files_enabled_by_default(client: TestClient):
    res = client.get("/v1/fs/settings")
    assert res.status_code == 200
    assert res.json() == {"recent_files_enabled": True}


def test_fs_settings_disable_recent_files_hides_and_stops_tracking(client: TestClient, tmp_path: Path):
    folder = tmp_path / "settings_target"
    folder.mkdir()
    photo = folder / "photo.jpg"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(photo)
    client.post("/v1/fs/recent", json={"path": str(photo)})

    res = client.patch("/v1/fs/settings", json={"recent_files_enabled": False})
    assert res.status_code == 200
    assert res.json() == {"recent_files_enabled": False}

    # Existing history is cleared, not just hidden.
    res = client.get("/v1/fs/recent")
    assert res.json()["files"] == []

    # New opens aren't tracked while disabled either.
    client.post("/v1/fs/recent", json={"path": str(photo)})
    res = client.patch("/v1/fs/settings", json={"recent_files_enabled": True})
    assert res.json() == {"recent_files_enabled": True}
    res = client.get("/v1/fs/recent")
    assert res.json()["files"] == []


def test_fs_settings_reenable_recent_files_tracks_again(client: TestClient, tmp_path: Path):
    folder = tmp_path / "settings_reenable"
    folder.mkdir()
    photo = folder / "photo.jpg"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(photo)

    client.patch("/v1/fs/settings", json={"recent_files_enabled": False})
    client.patch("/v1/fs/settings", json={"recent_files_enabled": True})
    client.post("/v1/fs/recent", json={"path": str(photo)})

    res = client.get("/v1/fs/recent")
    assert len(res.json()["files"]) == 1


# ---------------------------------------------------------------------------
# /v1/fs/search — recursive / cross-subfolder search (Phase I)
# ---------------------------------------------------------------------------

def test_fs_search_finds_match_in_subfolder(client: TestClient, tmp_path: Path):
    root = tmp_path / "search_target"
    (root / "sub" / "deeper").mkdir(parents=True)
    Image.new("RGB", (8, 8), (255, 0, 0)).save(root / "sub" / "deeper" / "vacation_photo.jpg")

    res = client.get("/v1/fs/search", params={"path": str(root), "query": "vacation"})
    assert res.status_code == 200
    body = res.json()
    assert body["truncated"] is False
    names = {r["name"] for r in body["results"]}
    assert "vacation_photo.jpg" in names
    hit = next(r for r in body["results"] if r["name"] == "vacation_photo.jpg")
    assert hit["kind"] == "file"
    assert hit["media_kind"] == "image"
    assert Path(hit["path"]) == (root / "sub" / "deeper" / "vacation_photo.jpg").resolve()


def test_fs_search_finds_audio_files(client: TestClient, tmp_path: Path):
    root = tmp_path / "search_audio"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "vacation_song.mp3").write_bytes(b"fake mp3 bytes")

    res = client.get("/v1/fs/search", params={"path": str(root), "query": "vacation"})
    assert res.status_code == 200
    body = res.json()
    hit = next(r for r in body["results"] if r["name"] == "vacation_song.mp3")
    assert hit["media_kind"] == "audio"


def test_fs_search_matches_folder_names_too(client: TestClient, tmp_path: Path):
    root = tmp_path / "search_folders"
    (root / "Family Trip 2024").mkdir(parents=True)
    Image.new("RGB", (8, 8), (0, 255, 0)).save(root / "Family Trip 2024" / "a.jpg")

    res = client.get("/v1/fs/search", params={"path": str(root), "query": "family"})
    assert res.status_code == 200
    body = res.json()
    folder_hits = [r for r in body["results"] if r["kind"] == "folder"]
    assert any(r["name"] == "Family Trip 2024" for r in folder_hits)


def test_fs_search_ignores_non_media_files(client: TestClient, tmp_path: Path):
    root = tmp_path / "search_non_media"
    root.mkdir()
    (root / "notes_report.txt").write_text("not media")
    Image.new("RGB", (8, 8), (0, 0, 255)).save(root / "report_photo.jpg")

    res = client.get("/v1/fs/search", params={"path": str(root), "query": "report"})
    assert res.status_code == 200
    names = {r["name"] for r in res.json()["results"]}
    assert names == {"report_photo.jpg"}  # notes_report.txt never surfaced


def test_fs_search_is_case_insensitive_substring(client: TestClient, tmp_path: Path):
    root = tmp_path / "search_case"
    root.mkdir()
    Image.new("RGB", (8, 8), (255, 255, 0)).save(root / "SUNSET.jpg")

    res = client.get("/v1/fs/search", params={"path": str(root), "query": "sun"})
    assert res.status_code == 200
    assert {r["name"] for r in res.json()["results"]} == {"SUNSET.jpg"}


def test_fs_search_respects_result_cap(client: TestClient, tmp_path: Path):
    root = tmp_path / "search_cap"
    root.mkdir()
    for i in range(10):
        Image.new("RGB", (8, 8), (i, i, i)).save(root / f"match_{i}.jpg")

    res = client.get("/v1/fs/search", params={"path": str(root), "query": "match", "limit": 3})
    assert res.status_code == 200
    body = res.json()
    assert len(body["results"]) == 3
    assert body["truncated"] is True


def test_fs_search_survives_one_broken_entry(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """One ACL-denied/vanished subdirectory must not abort the whole search
    — the real `os.scandir` is used everywhere except the simulated-broken
    folder, whose scan raises OSError like a real permission error would."""
    root = tmp_path / "search_resilience"
    (root / "good").mkdir(parents=True)
    (root / "broken").mkdir(parents=True)
    Image.new("RGB", (8, 8), (10, 20, 30)).save(root / "good" / "findme_ok.jpg")
    Image.new("RGB", (8, 8), (40, 50, 60)).save(root / "broken" / "findme_hidden.jpg")

    real_scandir = os.scandir
    broken_dir = str((root / "broken").resolve())

    def flaky_scandir(path):
        if str(Path(path).resolve()) == broken_dir:
            raise PermissionError("simulated ACL denial")
        return real_scandir(path)

    monkeypatch.setattr("mediamind.core.search.os.scandir", flaky_scandir)

    res = client.get("/v1/fs/search", params={"path": str(root), "query": "findme"})
    assert res.status_code == 200
    names = {r["name"] for r in res.json()["results"]}
    assert names == {"findme_ok.jpg"}  # the broken folder's match never surfaced, but this did


def test_fs_search_empty_query_returns_nothing(client: TestClient, tmp_path: Path):
    root = tmp_path / "search_empty"
    root.mkdir()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(root / "a.jpg")

    res = client.get("/v1/fs/search", params={"path": str(root), "query": "  "})
    assert res.status_code == 200
    assert res.json()["results"] == []


def test_fs_search_rejects_nonexistent_root(client: TestClient, tmp_path: Path):
    res = client.get(
        "/v1/fs/search", params={"path": str(tmp_path / "nope"), "query": "anything"}
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# /v1/fs/gallery — recursive, date-sorted media timeline (Phase O)
# ---------------------------------------------------------------------------

def test_fs_gallery_recursive_and_sorted_by_mtime_desc(client: TestClient, tmp_path: Path):
    root = tmp_path / "gallery_root"
    (root / "sub").mkdir(parents=True)
    older = root / "older.jpg"
    newer = root / "sub" / "newer.jpg"
    Image.new("RGB", (8, 8), (1, 1, 1)).save(older)
    Image.new("RGB", (8, 8), (2, 2, 2)).save(newer)
    old_time = time.time() - 1000
    os.utime(older, (old_time, old_time))

    res = client.get("/v1/fs/gallery", params={"path": str(root)})
    assert res.status_code == 200
    body = res.json()
    names = [i["name"] for i in body["items"]]
    assert names.index("newer.jpg") < names.index("older.jpg")
    assert body["truncated"] is False


def test_fs_gallery_includes_audio(client: TestClient, tmp_path: Path):
    root = tmp_path / "gallery_audio"
    root.mkdir()
    (root / "song.mp3").write_bytes(b"fake mp3 bytes")
    Image.new("RGB", (8, 8), (3, 3, 3)).save(root / "photo.jpg")

    res = client.get("/v1/fs/gallery", params={"path": str(root)})
    assert res.status_code == 200
    kinds = {i["name"]: i["media_kind"] for i in res.json()["items"]}
    assert kinds["song.mp3"] == "audio"
    assert kinds["photo.jpg"] == "image"


def test_fs_gallery_ignores_non_media_files(client: TestClient, tmp_path: Path):
    root = tmp_path / "gallery_non_media"
    root.mkdir()
    (root / "notes.txt").write_text("not media")
    Image.new("RGB", (8, 8), (4, 4, 4)).save(root / "photo.jpg")

    res = client.get("/v1/fs/gallery", params={"path": str(root)})
    assert res.status_code == 200
    names = {i["name"] for i in res.json()["items"]}
    assert names == {"photo.jpg"}


def test_fs_gallery_respects_limit_and_reports_truncated(client: TestClient, tmp_path: Path):
    root = tmp_path / "gallery_cap"
    root.mkdir()
    for i in range(10):
        Image.new("RGB", (8, 8), (i, i, i)).save(root / f"photo_{i}.jpg")

    res = client.get("/v1/fs/gallery", params={"path": str(root), "limit": 3})
    assert res.status_code == 200
    body = res.json()
    assert len(body["items"]) == 3
    assert body["truncated"] is True


def test_fs_gallery_skips_noise_dirs(client: TestClient, tmp_path: Path):
    root = tmp_path / "gallery_noise"
    (root / "node_modules").mkdir(parents=True)
    Image.new("RGB", (8, 8), (5, 5, 5)).save(root / "node_modules" / "hidden.jpg")
    Image.new("RGB", (8, 8), (6, 6, 6)).save(root / "visible.jpg")

    res = client.get("/v1/fs/gallery", params={"path": str(root)})
    assert res.status_code == 200
    names = {i["name"] for i in res.json()["items"]}
    assert names == {"visible.jpg"}


def test_fs_gallery_rejects_nonexistent_root(client: TestClient, tmp_path: Path):
    res = client.get("/v1/fs/gallery", params={"path": str(tmp_path / "nope")})
    assert res.status_code == 404


def test_fs_quick_access_hides_stale_pin(client: TestClient, tmp_path: Path):
    """A pin whose folder was deleted out from under it (or a drive that got
    unplugged) is left out of the listing rather than raising — it should
    self-heal if the folder reappears, not corrupt the store."""
    folder = tmp_path / "pinned_then_deleted"
    folder.mkdir()
    client.post("/v1/fs/quick-access", json={"path": str(folder)})

    import shutil
    shutil.rmtree(folder)

    res = client.get("/v1/fs/quick-access")
    assert res.status_code == 200
    assert res.json()["pins"] == []
