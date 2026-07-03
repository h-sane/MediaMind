"""Tests for the OpenCV YuNet+SFace provider interface.

No model files are needed — tests cover the provider contract and error handling.
Integration tests that require actual model files are marked 'integration'.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from mediamind.providers.opencv_provider import OpenCVYuNetSFaceProvider


def test_provider_id_and_dim():
    p = OpenCVYuNetSFaceProvider(Path("/tmp/models"))
    assert p.id == "opencv-yunet-sface"
    assert p.embedding_dim == 128


def test_prepare_raises_if_model_missing(tmp_path):
    """prepare() must raise FileNotFoundError when model files are absent."""
    p = OpenCVYuNetSFaceProvider(tmp_path)
    with pytest.raises(FileNotFoundError, match="YuNet"):
        p.prepare()


def test_prepare_raises_if_sface_model_missing(tmp_path):
    """prepare() fails cleanly when only the detection model is present."""
    from mediamind.providers.opencv_provider import YUNET_MODEL
    (tmp_path / YUNET_MODEL).write_bytes(b"fake")
    p = OpenCVYuNetSFaceProvider(tmp_path)
    with pytest.raises(FileNotFoundError, match="SFace"):
        p.prepare()


def test_get_faces_raises_without_prepare(tmp_path):
    """get_faces() must assert that prepare() was called first."""
    p = OpenCVYuNetSFaceProvider(tmp_path)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    with pytest.raises(AssertionError, match="prepare"):
        p.get_faces(frame)


def test_catalog_contains_opencv_entry():
    """The catalog must expose the opencv-yunet-sface entry."""
    from mediamind.providers.catalog import CATALOG
    ids = [e.id for e in CATALOG]
    assert "opencv-yunet-sface" in ids


def test_opencv_catalog_entry_fields():
    """Verify catalog entry fields are correct before release."""
    from mediamind.providers.catalog import CATALOG
    entry = next(e for e in CATALOG if e.id == "opencv-yunet-sface")

    assert entry.kind == "opencv_zoo"
    assert entry.license.commercial_use is True
    assert entry.license.name == "Apache-2.0"
    assert entry.embedding_dim == 128
    assert len(entry.downloads) == 2

    filenames = {dl.filename for dl in entry.downloads}
    assert "face_detection_yunet_2023mar.onnx" in filenames
    assert "face_recognition_sface_2021dec.onnx" in filenames


def test_manager_creates_opencv_provider(tmp_path):
    """ProviderManager.create() returns an OpenCVYuNetSFaceProvider for opencv_zoo kind."""
    from mediamind.providers.catalog import CatalogEntry, LicenseInfo, DownloadFile
    from mediamind.providers.manager import ProviderManager

    entry = CatalogEntry(
        id="opencv-yunet-sface",
        name="Test",
        description="",
        license=LicenseInfo(name="Apache-2.0", url="", commercial_use=True, summary=""),
        downloads=[
            DownloadFile(url="http://x/det.onnx", sha256=None, filename="face_detection_yunet_2023mar.onnx"),
            DownloadFile(url="http://x/rec.onnx", sha256=None, filename="face_recognition_sface_2021dec.onnx"),
        ],
        archive="direct",
        extract_subdir="models/opencv-yunet-sface",
        embedding_dim=128,
        cluster_eps=0.5,
        kind="opencv_zoo",
    )
    pm = ProviderManager(tmp_path, catalog=[entry])

    # Mark as installed so create() doesn't raise
    pm.mark_installed("opencv-yunet-sface")

    provider = pm.create("opencv-yunet-sface")
    assert isinstance(provider, OpenCVYuNetSFaceProvider)
    assert provider.id == "opencv-yunet-sface"


def test_download_runner_direct_archive(tmp_path):
    """'direct' archive mode downloads files into extract_subdir, not models_root."""
    from mediamind.providers.catalog import CatalogEntry, LicenseInfo, DownloadFile
    from mediamind.providers.manager import ProviderManager
    from mediamind.providers.downloads import make_download_runner

    captured: list[tuple[str, Path]] = []

    def fake_opener(url: str, headers: dict):
        import io
        captured.append((url, None))
        return io.BytesIO(b"model-data")

    entry = CatalogEntry(
        id="opencv-yunet-sface",
        name="Test",
        description="",
        license=LicenseInfo(name="Apache-2.0", url="", commercial_use=True, summary=""),
        downloads=[
            DownloadFile(url="http://x/det.onnx", sha256=None, filename="face_detection_yunet_2023mar.onnx", size_bytes=10),
            DownloadFile(url="http://x/rec.onnx", sha256=None, filename="face_recognition_sface_2021dec.onnx", size_bytes=10),
        ],
        archive="direct",
        extract_subdir="models/opencv-yunet-sface",
        embedding_dim=128,
        cluster_eps=0.5,
        kind="opencv_zoo",
    )
    pm = ProviderManager(tmp_path, catalog=[entry])
    runner = make_download_runner(entry, pm, opener=fake_opener)

    import threading
    import asyncio
    from mediamind.core.jobs import Job, JobContext

    loop = asyncio.new_event_loop()
    job = Job(id="j1", library_id="lib1", type="provider-download", state="running")
    ctx = JobContext(job, threading.Event(), loop, lambda j: None)

    result = runner(ctx)
    assert result.get("installed") is True

    extract_dir = tmp_path / "models/opencv-yunet-sface"
    assert (extract_dir / "face_detection_yunet_2023mar.onnx").exists()
    assert (extract_dir / "face_recognition_sface_2021dec.onnx").exists()
    # Files must NOT be in models_root directly (only in extract_subdir)
    assert not (tmp_path / "face_detection_yunet_2023mar.onnx").exists()
    assert not (tmp_path / "face_recognition_sface_2021dec.onnx").exists()

    loop.close()
