"""Tests for the live file-browser API (M11): listing + path thumbnails.

Invariants under test:
- the listing is purely filesystem-first: always fresh, no DB writes, no hashing
- every file routes somewhere (non-media appears too, with kind="other")
- `.mediamind/` is never listed
- one bad file -> 422 for that file only, never a 500
- the thumbnail path parameter cannot escape the library root
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mediamind.api.app import create_app

JPEG_MAGIC = b"\xff\xd8"


def _make_wav(path: Path) -> None:
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 800)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def lib(client: TestClient, tmp_path: Path):
    """A registered library with images, a GIF, a corrupt jpg, and a text file."""
    root = tmp_path / "photos"
    (root / "nested").mkdir(parents=True)

    Image.new("RGB", (64, 48), (255, 0, 0)).save(root / "red1.jpg")
    Image.new("RGB", (64, 64), (0, 0, 255)).save(root / "nested" / "blue.png")
    frames = [Image.new("RGB", (64, 64), (255, 0, 0)) for _ in range(3)]
    frames[0].save(root / "anim.gif", save_all=True, append_images=frames[1:],
                   duration=100, loop=0)
    (root / "corrupt.jpg").write_bytes(b"this is not a jpeg")
    (root / "notes.txt").write_text("not media")

    res = client.post("/v1/libraries", json={"path": str(root)})
    assert res.status_code == 201
    return res.json()["id"], root


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def test_list_files_returns_every_file(client: TestClient, lib):
    lib_id, root = lib
    body = client.get(f"/v1/libraries/{lib_id}/files").json()

    assert body["library_id"] == lib_id
    assert body["root"] == str(root)
    assert body["total"] == 5

    by_path = {f["path"]: f for f in body["files"]}
    assert set(by_path) == {"red1.jpg", "nested/blue.png", "anim.gif",
                            "corrupt.jpg", "notes.txt"}

    assert by_path["red1.jpg"]["kind"] == "image"
    assert by_path["nested/blue.png"]["kind"] == "image"  # forward-slash rel path
    assert by_path["anim.gif"]["kind"] == "gif"
    assert by_path["corrupt.jpg"]["kind"] == "image"      # kind is by extension
    assert by_path["notes.txt"]["kind"] == "other"        # nothing silently hidden

    for f in body["files"]:
        assert f["size"] > 0
        assert f["mtime"] > 0

    # .mediamind (created at registration) must never appear.
    assert not any(p.startswith(".mediamind") for p in by_path)


def test_list_files_is_always_fresh(client: TestClient, lib):
    """A file added after registration shows up on the next request — no cache."""
    lib_id, root = lib
    assert client.get(f"/v1/libraries/{lib_id}/files").json()["total"] == 5

    Image.new("RGB", (32, 32), (0, 255, 0)).save(root / "new.jpg")
    body = client.get(f"/v1/libraries/{lib_id}/files").json()
    assert body["total"] == 6
    assert "new.jpg" in {f["path"] for f in body["files"]}


def test_list_files_writes_nothing(client: TestClient, lib):
    """Listing is read-only: no index.db, nothing new inside .mediamind/."""
    lib_id, root = lib
    before = set((root / ".mediamind").iterdir())
    client.get(f"/v1/libraries/{lib_id}/files")
    assert set((root / ".mediamind").iterdir()) == before
    assert not (root / ".mediamind" / "index.db").exists()


def test_list_files_unknown_library_404(client: TestClient):
    assert client.get("/v1/libraries/nope/files").status_code == 404


# ---------------------------------------------------------------------------
# Audio — a first-class media kind for browsing/playback, but not for
# thumbnailing (no visual frame) or dedupe/faces (see core/explorer_media.py).
# ---------------------------------------------------------------------------

@pytest.fixture
def lib_with_audio(client: TestClient, tmp_path: Path):
    root = tmp_path / "music"
    root.mkdir()
    _make_wav(root / "song.wav")
    res = client.post("/v1/libraries", json={"path": str(root)})
    assert res.status_code == 201
    return res.json()["id"], root


def test_list_files_classifies_audio(client: TestClient, lib_with_audio):
    lib_id, _ = lib_with_audio
    body = client.get(f"/v1/libraries/{lib_id}/files").json()
    by_path = {f["path"]: f for f in body["files"]}
    assert by_path["song.wav"]["kind"] == "audio"


def test_raw_serves_audio_for_playback(client: TestClient, lib_with_audio):
    lib_id, _ = lib_with_audio
    res = client.get(f"/v1/libraries/{lib_id}/files/raw", params={"path": "song.wav"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("audio/")


def test_raw_unknown_kind_still_422(client: TestClient, lib):
    """Non-media (e.g. a .txt file) is still rejected by /raw."""
    lib_id, _ = lib
    res = client.get(f"/v1/libraries/{lib_id}/files/raw", params={"path": "notes.txt"})
    assert res.status_code == 422


def test_thumbnail_audio_422(client: TestClient, lib_with_audio):
    """Audio has no visual frame — the frontend shows a music icon instead."""
    lib_id, _ = lib_with_audio
    assert _thumb(client, lib_id, "song.wav").status_code == 422


# ---------------------------------------------------------------------------
# Thumbnails by path
# ---------------------------------------------------------------------------

def _thumb(client: TestClient, lib_id: str, path: str, **params):
    return client.get(
        f"/v1/libraries/{lib_id}/files/thumbnail",
        params={"path": path, **params},
    )


def test_thumbnail_image(client: TestClient, lib):
    lib_id, _ = lib
    res = _thumb(client, lib_id, "red1.jpg")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    assert res.content.startswith(JPEG_MAGIC)


def test_thumbnail_nested_forward_slash_path(client: TestClient, lib):
    lib_id, _ = lib
    res = _thumb(client, lib_id, "nested/blue.png")
    assert res.status_code == 200
    assert res.content.startswith(JPEG_MAGIC)


def test_thumbnail_gif_first_frame(client: TestClient, lib):
    lib_id, _ = lib
    res = _thumb(client, lib_id, "anim.gif")
    assert res.status_code == 200
    assert res.content.startswith(JPEG_MAGIC)


def test_thumbnail_video(client: TestClient, lib):
    """Video thumbnails come from the first sampled frame."""
    import cv2
    import numpy as np

    lib_id, root = lib
    out = root / "clip.mp4"
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 64))
    if not writer.isOpened():
        pytest.skip("no mp4 codec available in this OpenCV build")
    for _ in range(5):
        writer.write(np.full((64, 64, 3), 128, dtype=np.uint8))
    writer.release()

    res = _thumb(client, lib_id, "clip.mp4")
    assert res.status_code == 200
    assert res.content.startswith(JPEG_MAGIC)


def test_thumbnail_corrupt_file_422_not_500(client: TestClient, lib):
    lib_id, _ = lib
    res = _thumb(client, lib_id, "corrupt.jpg")
    assert res.status_code == 422


def test_thumbnail_non_media_422(client: TestClient, lib):
    lib_id, _ = lib
    assert _thumb(client, lib_id, "notes.txt").status_code == 422


def test_thumbnail_missing_file_404(client: TestClient, lib):
    lib_id, _ = lib
    assert _thumb(client, lib_id, "does-not-exist.jpg").status_code == 404


def test_thumbnail_respects_size_bounds(client: TestClient, lib):
    lib_id, _ = lib
    assert _thumb(client, lib_id, "red1.jpg", size=64).status_code == 200
    assert _thumb(client, lib_id, "red1.jpg", size=32).status_code == 422    # < ge
    assert _thumb(client, lib_id, "red1.jpg", size=4096).status_code == 422  # > le


# ---------------------------------------------------------------------------
# Path traversal safety — user-controlled path must stay inside the root
# ---------------------------------------------------------------------------

def test_thumbnail_rejects_traversal_and_absolute_paths(client: TestClient, lib, tmp_path: Path):
    lib_id, root = lib

    # A real, decodable image OUTSIDE the library — must still be unreachable.
    outside = tmp_path / "outside.jpg"
    Image.new("RGB", (32, 32), (1, 2, 3)).save(outside)

    for attempt in (
        "../outside.jpg",
        "..\\outside.jpg",
        "nested/../../outside.jpg",
        str(outside),                  # absolute path
        outside.as_posix(),
        "/etc/passwd",
        "\\\\server\\share\\x.jpg",    # UNC
        "C:/Windows/win.ini",          # drive letter
        "",
    ):
        res = _thumb(client, lib_id, attempt)
        assert res.status_code == 404, f"path {attempt!r} was not rejected"


def test_thumbnail_rejects_mediamind_data_dir(client: TestClient, lib):
    """MediaMind's own data folder is not browsable through the API."""
    lib_id, root = lib
    secret = root / ".mediamind" / "secret.jpg"
    Image.new("RGB", (32, 32), (9, 9, 9)).save(secret)
    assert _thumb(client, lib_id, ".mediamind/secret.jpg").status_code == 404
