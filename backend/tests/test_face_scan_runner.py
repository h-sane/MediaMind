"""Tests for core/faces/scan.py's make_face_scan_runner — model-free (FakeColorProvider).

Nothing in the existing suite calls this runner directly: test_scans_api.py only
exercises "dedupe" jobs through the API, and the persons/organize test files call
persist_face_scan directly, bypassing the runner's phase-1/phase-2 logic entirely.
That left three session-7 fixes (COALESCE on decoded_ok, not caching decode
failures, stale-faces pruning) with no coverage of the code that actually
contains them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from mediamind.config import library_data_dir
from mediamind.core.faces.scan import make_face_scan_runner
from mediamind.providers.fake import FakeColorProvider
from mediamind.store.db import library_db_path, open_db

PROVIDER = "fake-color"


class _StubCtx:
    """Minimal JobContext stand-in — the runner only needs job_id, cancelled(), report_progress()."""

    job_id = "test-scan"

    def cancelled(self) -> bool:
        return False

    def report_progress(self, done: int, total: int, phase: str = "") -> None:
        pass


@pytest.fixture
def conn(tmp_path: Path):
    c = open_db(library_db_path(library_data_dir(tmp_path)))
    yield c
    c.close()


def _run(library_root: Path):
    runner = make_face_scan_runner(
        library_root, lambda: FakeColorProvider(), PROVIDER, pending_for_named=True
    )
    return runner(_StubCtx())


# ---------------------------------------------------------------------------
# Basic sanity
# ---------------------------------------------------------------------------

def test_runner_persists_summary_and_faces(tmp_path: Path, conn):
    Image.new("RGB", (64, 64), (255, 0, 0)).save(tmp_path / "red.jpg")
    Image.new("RGB", (64, 64), (0, 0, 255)).save(tmp_path / "blue.jpg")

    summary = _run(tmp_path)
    assert summary["files"] == 2
    assert summary["faces"] == 2
    assert summary["people"] == 0  # DBSCAN needs >= min_samples (2) per cluster; 1 each -> noise

    faces = conn.execute("SELECT COUNT(*) FROM faces WHERE provider_id = ?", (PROVIDER,)).fetchone()[0]
    assert faces == 2


def test_runner_flags_corrupt_file_unreadable(tmp_path: Path, conn):
    (tmp_path / "corrupt.jpg").write_bytes(b"not a jpeg" * 10)

    summary = _run(tmp_path)
    assert summary["unreadable_files"] == 1
    row = conn.execute("SELECT decoded_ok FROM files WHERE path = ?", ("corrupt.jpg",)).fetchone()
    assert row["decoded_ok"] == 0


# ---------------------------------------------------------------------------
# Fix 4a — upsert_file COALESCE must not clobber decoded_ok on a cache-hit rescan
# ---------------------------------------------------------------------------

def test_rescan_preserves_decoded_ok_on_cache_hit(tmp_path: Path, conn):
    Image.new("RGB", (64, 64), (255, 0, 0)).save(tmp_path / "red.jpg")

    _run(tmp_path)
    row = conn.execute("SELECT decoded_ok FROM files WHERE path = ?", ("red.jpg",)).fetchone()
    assert row["decoded_ok"] == 1

    # Rescan: file unchanged -> phase 2 takes the cache-hit branch and never
    # calls upsert_file again. Phase 1 still upserts decoded_ok=None for every
    # file on every scan; without the COALESCE fix this would null it out.
    _run(tmp_path)
    row = conn.execute("SELECT decoded_ok FROM files WHERE path = ?", ("red.jpg",)).fetchone()
    assert row["decoded_ok"] == 1, "decoded_ok was clobbered by a cache-hit rescan"


# ---------------------------------------------------------------------------
# Fix 4b — decode failures must never be cached, so they're retried every scan
# ---------------------------------------------------------------------------

def test_decode_failure_not_cached(tmp_path: Path, conn):
    (tmp_path / "corrupt.jpg").write_bytes(b"garbage" * 20)

    s1 = _run(tmp_path)
    assert s1["unreadable_files"] == 1

    content_hash = conn.execute("SELECT content_hash FROM files WHERE path = ?", ("corrupt.jpg",)).fetchone()[0]
    cached = conn.execute(
        "SELECT COUNT(*) FROM embeddings WHERE content_hash = ? AND provider_id = ?",
        (content_hash, PROVIDER),
    ).fetchone()[0]
    assert cached == 0, "a decode failure must not create a cache entry (not even a no-faces sentinel)"

    # Rescan (file still unreadable, unchanged bytes): must be retried, not
    # silently treated as a permanent "no faces" cache hit.
    s2 = _run(tmp_path)
    assert s2["unreadable_files"] == 1


# ---------------------------------------------------------------------------
# Fix 13 — stale faces rows pruned when a file disappears between scans
# ---------------------------------------------------------------------------

def test_stale_faces_pruned_after_external_delete(tmp_path: Path, conn):
    Image.new("RGB", (64, 64), (255, 0, 0)).save(tmp_path / "red.jpg")
    Image.new("RGB", (64, 64), (0, 0, 255)).save(tmp_path / "blue.jpg")

    _run(tmp_path)
    red_id = conn.execute("SELECT id FROM files WHERE path = ?", ("red.jpg",)).fetchone()["id"]
    assert conn.execute("SELECT COUNT(*) FROM faces WHERE file_id = ?", (red_id,)).fetchone()[0] == 1

    (tmp_path / "red.jpg").unlink()
    _run(tmp_path)

    assert conn.execute("SELECT COUNT(*) FROM faces WHERE file_id = ?", (red_id,)).fetchone()[0] == 0
    blue_id = conn.execute("SELECT id FROM files WHERE path = ?", ("blue.jpg",)).fetchone()["id"]
    assert conn.execute("SELECT COUNT(*) FROM faces WHERE file_id = ?", (blue_id,)).fetchone()[0] == 1
