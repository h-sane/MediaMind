"""ProviderManager installed-state semantics + catalog integrity.

The core contract under test: "installed" means the real model files exist on
disk. The .mediamind-installed.json marker is bookkeeping only — model files
downloaded by anything else (e.g. the insightface package's own auto-download
into ~/.insightface) count as installed with no marker, and deleting the real
files makes the provider downloadable again even if a stale marker survives.
"""

from __future__ import annotations

from pathlib import Path

from mediamind.providers.catalog import (
    CATALOG,
    CatalogEntry,
    DownloadFile,
    LicenseInfo,
)
from mediamind.providers.manager import ProviderManager

_NC_LICENSE = LicenseInfo(name="NC", url="https://example.invalid", commercial_use=False, summary="t")


def _pack_entry(pack: str = "buffalo_l", required=("det_10g.onnx", "w600k_r50.onnx")) -> CatalogEntry:
    return CatalogEntry(
        id=f"insightface-{pack.replace('_', '-')}",
        name=pack,
        description="test",
        license=_NC_LICENSE,
        downloads=[
            DownloadFile(
                url=f"https://github.com/deepinsight/insightface/releases/download/v0.7/{pack}.zip",
                sha256=None,
                filename=f"{pack}.zip",
                size_bytes=1,
            )
        ],
        archive="zip",
        extract_subdir=f"models/{pack}",
        embedding_dim=512,
        cluster_eps=0.5,
        kind="insightface_pack",
        required_files=tuple(required),
    )


def _pm(tmp_path: Path, entry: CatalogEntry) -> ProviderManager:
    return ProviderManager(
        tmp_path / "appmodels",
        catalog=[entry],
        insightface_root=tmp_path / "ifcache",
    )


def _write_pack_files(root: Path, pack: str, names) -> Path:
    d = root / "models" / pack
    d.mkdir(parents=True, exist_ok=True)
    for name in names:
        (d / name).write_bytes(b"onnx-bytes")
    return d


# ---------------------------------------------------------------------------
# insightface_pack: shared-cache detection (the reported bug)
# ---------------------------------------------------------------------------

def test_preexisting_insightface_cache_counts_as_installed_without_marker(tmp_path):
    """Model files placed by the insightface package itself (no MediaMind
    marker anywhere) must be detected as installed — no duplicate download."""
    entry = _pack_entry()
    pm = _pm(tmp_path, entry)
    _write_pack_files(tmp_path / "ifcache", "buffalo_l", ["det_10g.onnx", "w600k_r50.onnx"])

    assert pm.is_installed("insightface-buffalo-l") is True


def test_deleting_model_files_makes_pack_downloadable_again(tmp_path):
    """User deletes the real files -> not installed, even though the stale
    marker file survives. (Explicit user requirement.)"""
    entry = _pack_entry()
    pm = _pm(tmp_path, entry)
    model_dir = _write_pack_files(tmp_path / "ifcache", "buffalo_l", ["det_10g.onnx", "w600k_r50.onnx"])
    pm.mark_installed("insightface-buffalo-l")
    assert pm.is_installed("insightface-buffalo-l") is True

    (model_dir / "det_10g.onnx").unlink()
    (model_dir / "w600k_r50.onnx").unlink()
    assert (model_dir / ".mediamind-installed.json").exists()  # stale marker remains
    assert pm.is_installed("insightface-buffalo-l") is False


def test_partial_pack_is_not_installed(tmp_path):
    """Missing any required file (e.g. deleted recognition model) -> not installed."""
    entry = _pack_entry()
    pm = _pm(tmp_path, entry)
    _write_pack_files(tmp_path / "ifcache", "buffalo_l", ["det_10g.onnx"])  # no w600k_r50

    assert pm.is_installed("insightface-buffalo-l") is False


def test_marker_alone_never_counts_as_installed(tmp_path):
    """A marker without the real model files is not an install."""
    entry = _pack_entry()
    pm = _pm(tmp_path, entry)
    pm.mark_installed("insightface-buffalo-l")

    assert pm.is_installed("insightface-buffalo-l") is False


def test_pack_in_private_models_root_is_ignored(tmp_path):
    """insightface_pack entries live in the shared InsightFace cache only —
    a copy under MediaMind's private models dir is not consulted."""
    entry = _pack_entry()
    pm = _pm(tmp_path, entry)
    _write_pack_files(tmp_path / "appmodels", "buffalo_l", ["det_10g.onnx", "w600k_r50.onnx"])

    assert pm.is_installed("insightface-buffalo-l") is False


def test_mark_installed_writes_marker_next_to_shared_models(tmp_path):
    """Bookkeeping lives where the model lives."""
    entry = _pack_entry()
    pm = _pm(tmp_path, entry)
    pm.mark_installed("insightface-buffalo-l")

    assert (tmp_path / "ifcache" / "models" / "buffalo_l" / ".mediamind-installed.json").is_file()
    assert not (tmp_path / "appmodels" / "models" / "buffalo_l").exists()


def test_create_uses_shared_insightface_root(tmp_path):
    """create() must point FaceAnalysis at the same root is_installed() checked,
    so InsightFace never triggers its own surprise re-download."""
    entry = _pack_entry()
    pm = _pm(tmp_path, entry)
    _write_pack_files(tmp_path / "ifcache", "buffalo_l", ["det_10g.onnx", "w600k_r50.onnx"])

    provider = pm.create("insightface-buffalo-l")
    assert provider.id == "insightface-buffalo-l"
    assert provider._root == str(tmp_path / "ifcache")
    assert provider.embedding_dim == 512


# ---------------------------------------------------------------------------
# direct-archive kinds (opencv_zoo): same real-files truth
# ---------------------------------------------------------------------------

def _opencv_entry() -> CatalogEntry:
    return CatalogEntry(
        id="opencv-yunet-sface",
        name="Test",
        description="test",
        license=LicenseInfo(name="Apache-2.0", url="", commercial_use=True, summary="t"),
        downloads=[
            DownloadFile(url="https://github.com/opencv/opencv_zoo/raw/main/a.onnx", sha256=None, filename="det.onnx", size_bytes=1),
            DownloadFile(url="https://github.com/opencv/opencv_zoo/raw/main/b.onnx", sha256=None, filename="rec.onnx", size_bytes=1),
        ],
        archive="direct",
        extract_subdir="models/opencv-yunet-sface",
        embedding_dim=128,
        cluster_eps=0.5,
        kind="opencv_zoo",
    )


def test_direct_entry_requires_downloaded_files_not_marker(tmp_path):
    entry = _opencv_entry()
    pm = ProviderManager(tmp_path, catalog=[entry])
    pm.mark_installed("opencv-yunet-sface")
    assert pm.is_installed("opencv-yunet-sface") is False  # marker alone: no

    model_dir = tmp_path / "models" / "opencv-yunet-sface"
    (model_dir / "det.onnx").write_bytes(b"x")
    assert pm.is_installed("opencv-yunet-sface") is False  # partial: no

    (model_dir / "rec.onnx").write_bytes(b"x")
    assert pm.is_installed("opencv-yunet-sface") is True


def test_opencv_files_stay_in_private_models_root(tmp_path):
    """opencv_zoo has no external cache convention — it stays under models_root."""
    entry = _opencv_entry()
    pm = ProviderManager(
        tmp_path / "appmodels", catalog=[entry], insightface_root=tmp_path / "ifcache"
    )
    assert pm.model_dir(entry) == tmp_path / "appmodels" / "models" / "opencv-yunet-sface"


# ---------------------------------------------------------------------------
# download runner installs packs into the shared root
# ---------------------------------------------------------------------------

def test_zip_download_runner_extracts_into_shared_insightface_root(tmp_path):
    import asyncio
    import io
    import threading
    import zipfile

    from mediamind.core.jobs import Job, JobContext
    from mediamind.providers.downloads import make_download_runner

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("det_10g.onnx", b"det-bytes")
        zf.writestr("w600k_r50.onnx", b"rec-bytes")
    zip_bytes = buf.getvalue()

    def fake_opener(url: str, headers: dict):
        return io.BytesIO(zip_bytes)

    entry = _pack_entry()
    pm = _pm(tmp_path, entry)
    runner = make_download_runner(entry, pm, opener=fake_opener)

    loop = asyncio.new_event_loop()
    job = Job(id="j1", library_id="__app__", type="provider-download", state="running")
    ctx = JobContext(job, threading.Event(), loop, lambda j: None)
    result = runner(ctx)
    loop.close()

    assert result.get("installed") is True
    pack_dir = tmp_path / "ifcache" / "models" / "buffalo_l"
    assert (pack_dir / "det_10g.onnx").read_bytes() == b"det-bytes"
    assert (pack_dir / "w600k_r50.onnx").read_bytes() == b"rec-bytes"
    # Single copy on disk: nothing lands in MediaMind's private models dir.
    assert not (tmp_path / "appmodels" / "models" / "buffalo_l").exists()
    assert pm.is_installed("insightface-buffalo-l") is True


# ---------------------------------------------------------------------------
# Catalog integrity
# ---------------------------------------------------------------------------

_TRUSTED_URL_PREFIXES = (
    "https://github.com/deepinsight/insightface/",
    "https://github.com/opencv/opencv_zoo/",
)


def test_catalog_has_expected_entries():
    ids = {e.id for e in CATALOG}
    assert {
        "opencv-yunet-sface",
        "insightface-buffalo-l",
        "insightface-buffalo-m",
        "insightface-buffalo-sc",
        "insightface-antelopev2",
    } <= ids


def test_catalog_entries_are_well_formed():
    ids = [e.id for e in CATALOG]
    assert len(ids) == len(set(ids)), "duplicate catalog ids"

    for e in CATALOG:
        assert e.kind in {"insightface_pack", "opencv_zoo", "fake"}, e.id
        assert e.archive in {"zip", "direct", "none"}, e.id
        assert e.embedding_dim > 0 and e.cluster_eps > 0, e.id
        assert e.name and e.description, e.id
        assert e.license.name and e.license.summary and e.license.url, e.id
        if e.kind == "fake":
            continue

        assert e.downloads, e.id
        for dl in e.downloads:
            assert dl.url.startswith(_TRUSTED_URL_PREFIXES), (
                f"{e.id}: download URL not from a trusted origin: {dl.url}"
            )
            assert dl.filename, e.id
            assert dl.size_bytes > 0, e.id

        if e.kind == "insightface_pack":
            # InsightFace model-zoo weights are non-commercial; the catalog
            # must say so (the UI surfaces this before download).
            assert e.license.commercial_use is False, e.id
            assert e.archive == "zip", e.id
            pack = e.id.replace("insightface-", "").replace("-", "_")
            # FaceAnalysis(name=pack, root=X) loads X/models/<pack> — the
            # extract_subdir must line up or is_installed()/create() diverge.
            assert e.extract_subdir == f"models/{pack}", e.id
            assert e.required_files, f"{e.id}: zip packs must declare required_files"
            assert all(f.endswith(".onnx") for f in e.required_files), e.id
