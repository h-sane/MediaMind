"""Tests for core/ingest.py — the shared per-file ingest pipeline
(Performance & Ingest V4 Phase 1/3). Model-free (FakeColorProvider), no DB
migration surprises since open_db() always applies every migration.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from mediamind.core.ingest import ingest_file, ingest_path
from mediamind.core.scanner import KIND_IMAGE, ScannedFile, scan_folder
from mediamind.providers.fake import FakeColorProvider
from mediamind.store.db import open_db

PROVIDER = "fake-color"


@pytest.fixture
def conn(tmp_path: Path):
    c = open_db(tmp_path / ".mediamind" / "index.db")
    yield c
    c.close()


def _scanned(root: Path, rel: str) -> ScannedFile:
    path = root / rel
    stat = path.stat()
    from mediamind.core.scanner import kind_of

    return ScannedFile(path=path, kind=kind_of(path), size=stat.st_size, mtime=stat.st_mtime)


# ---------------------------------------------------------------------------
# Step 1: cache-hit skips rehashing
# ---------------------------------------------------------------------------


def test_cache_hit_skips_rehashing(tmp_path: Path, conn, monkeypatch):
    Image.new("RGB", (64, 64), (255, 0, 0)).save(tmp_path / "red.jpg")
    scanned = _scanned(tmp_path, "red.jpg")

    outcome1 = ingest_file(conn, tmp_path, scanned, warm_thumbnail=False)
    assert outcome1.was_cached is False
    assert outcome1.content_hash is not None

    import mediamind.core.ingest as ingest_mod

    calls = {"n": 0}
    real_hash_file = ingest_mod.hash_file

    def spy_hash_file(path):
        calls["n"] += 1
        return real_hash_file(path)

    monkeypatch.setattr(ingest_mod, "hash_file", spy_hash_file)

    # Re-ingest the same, unchanged file (same size+mtime) — must not re-read it.
    outcome2 = ingest_file(conn, tmp_path, scanned, warm_thumbnail=False)
    assert outcome2.was_cached is True
    assert outcome2.content_hash == outcome1.content_hash
    assert calls["n"] == 0, "hash_file() must not be called again for an unchanged file"


def test_changed_file_is_rehashed(tmp_path: Path, conn):
    Image.new("RGB", (64, 64), (255, 0, 0)).save(tmp_path / "red.jpg")
    scanned = _scanned(tmp_path, "red.jpg")
    outcome1 = ingest_file(conn, tmp_path, scanned, warm_thumbnail=False)

    # Overwrite with different content but keep the same mtime — the
    # fixture only needs a size change to trigger a cache miss deterministically.
    Image.new("RGB", (64, 64), (0, 255, 0), ).save(tmp_path / "red.jpg")
    import time

    time.sleep(0.01)
    (tmp_path / "red.jpg").touch()
    scanned2 = _scanned(tmp_path, "red.jpg")

    outcome2 = ingest_file(conn, tmp_path, scanned2, warm_thumbnail=False)
    assert outcome2.was_cached is False


# ---------------------------------------------------------------------------
# Step 2 (Phase 3): duplicate flagging
# ---------------------------------------------------------------------------


def test_exact_duplicate_is_flagged(tmp_path: Path, conn):
    original = Image.new("RGB", (64, 64), (255, 0, 0))
    original.save(tmp_path / "a.jpg")
    original.save(tmp_path / "b.jpg")

    ingest_file(conn, tmp_path, _scanned(tmp_path, "a.jpg"), warm_thumbnail=False)
    outcome = ingest_file(conn, tmp_path, _scanned(tmp_path, "b.jpg"), warm_thumbnail=False)

    assert outcome.duplicate_of == "a.jpg"
    assert outcome.match_type == "exact"

    from mediamind.store.duplicate_flags import list_flags

    flags = list_flags(conn, tmp_path)
    assert len(flags) == 1
    assert flags[0].path == "b.jpg"
    assert flags[0].match_path == "a.jpg"
    assert flags[0].match_type == "exact"


def test_near_duplicate_image_is_flagged(tmp_path: Path, conn):
    import numpy as np

    rng = np.random.default_rng(7)
    arr = rng.integers(0, 256, (128, 128, 3), dtype=np.uint8)
    original = Image.fromarray(arr)
    original.save(tmp_path / "orig.png")
    # Near-duplicate: resized + re-encoded, byte-different but perceptually close.
    original.resize((96, 96)).save(tmp_path / "resized.jpg", quality=90)

    ingest_file(conn, tmp_path, _scanned(tmp_path, "orig.png"), warm_thumbnail=False)
    outcome = ingest_file(conn, tmp_path, _scanned(tmp_path, "resized.jpg"), warm_thumbnail=False)

    assert outcome.match_type == "near"
    assert outcome.duplicate_of == "orig.png"


def test_unrelated_files_not_flagged(tmp_path: Path, conn):
    # Solid-color images legitimately phash alike (documented behavior, see
    # core.dedupe's module docstring) — use distinct noise images, same as
    # test_dedupe.py's fixtures, so this only exercises "genuinely different
    # images don't flag," not the solid-color near-match edge case.
    import numpy as np

    rng_a = np.random.default_rng(1)
    Image.fromarray(rng_a.integers(0, 256, (64, 64, 3), dtype=np.uint8)).save(tmp_path / "a.png")
    rng_b = np.random.default_rng(2)
    Image.fromarray(rng_b.integers(0, 256, (64, 64, 3), dtype=np.uint8)).save(tmp_path / "b.png")

    ingest_file(conn, tmp_path, _scanned(tmp_path, "a.png"), warm_thumbnail=False)
    outcome = ingest_file(conn, tmp_path, _scanned(tmp_path, "b.png"), warm_thumbnail=False)

    assert outcome.duplicate_of is None
    assert outcome.match_type is None


def test_repeat_flag_is_idempotent(tmp_path: Path, conn):
    """Re-ingesting the same unchanged duplicate must not create a second
    duplicate_flags row (unique index on path+match_path)."""
    original = Image.new("RGB", (64, 64), (255, 0, 0))
    original.save(tmp_path / "a.jpg")
    original.save(tmp_path / "b.jpg")

    ingest_file(conn, tmp_path, _scanned(tmp_path, "a.jpg"), warm_thumbnail=False)
    ingest_file(conn, tmp_path, _scanned(tmp_path, "b.jpg"), warm_thumbnail=False)
    ingest_file(conn, tmp_path, _scanned(tmp_path, "b.jpg"), warm_thumbnail=False)

    from mediamind.store.duplicate_flags import list_flags

    assert len(list_flags(conn, tmp_path)) == 1


# ---------------------------------------------------------------------------
# Step 3 (Phase 4): face step gated behind an injected provider
# ---------------------------------------------------------------------------


def test_no_provider_skips_face_step(tmp_path: Path, conn):
    Image.new("RGB", (64, 64), (255, 0, 0)).save(tmp_path / "red.jpg")
    outcome = ingest_file(conn, tmp_path, _scanned(tmp_path, "red.jpg"), warm_thumbnail=False)
    assert outcome.new_faces == 0
    assert outcome.pending_faces == 0
    assert conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0] == 0


def test_provider_given_detects_and_stores_faces(tmp_path: Path, conn):
    Image.new("RGB", (64, 64), (255, 0, 0)).save(tmp_path / "red.jpg")
    outcome = ingest_file(
        conn, tmp_path, _scanned(tmp_path, "red.jpg"),
        provider=FakeColorProvider(), provider_id=PROVIDER, warm_thumbnail=False,
    )
    assert outcome.new_faces == 1
    assert outcome.pending_faces == 0  # no existing persons yet -> unmatched, person_id NULL
    row = conn.execute("SELECT person_id FROM faces").fetchone()
    assert row["person_id"] is None


def test_face_free_image_yields_no_faces(tmp_path: Path, conn):
    Image.new("RGB", (64, 64), (0, 0, 0)).save(tmp_path / "black.jpg")  # below FakeColorProvider's brightness threshold
    outcome = ingest_file(
        conn, tmp_path, _scanned(tmp_path, "black.jpg"),
        provider=FakeColorProvider(), provider_id=PROVIDER, warm_thumbnail=False,
    )
    assert outcome.new_faces == 0


# ---------------------------------------------------------------------------
# ingest_path — the frozen external entry point
# ---------------------------------------------------------------------------


def test_ingest_path_stats_and_ingests(tmp_path: Path, conn):
    Image.new("RGB", (64, 64), (255, 0, 0)).save(tmp_path / "red.jpg")
    outcome = ingest_path(conn, tmp_path, tmp_path / "red.jpg", warm_thumbnail=False)
    assert outcome.file_id is not None
    assert outcome.content_hash is not None


def test_ingest_path_missing_file_returns_empty_outcome(tmp_path: Path, conn):
    outcome = ingest_path(conn, tmp_path, tmp_path / "nope.jpg", warm_thumbnail=False)
    assert outcome.file_id is None
    assert outcome.content_hash is None


# ---------------------------------------------------------------------------
# Non-media files still hash+cache (step 1 applies to every file)
# ---------------------------------------------------------------------------


def test_non_media_file_is_hashed_but_not_dedupe_checked(tmp_path: Path, conn):
    (tmp_path / "notes.txt").write_text("hello")
    (tmp_path / "notes_copy.txt").write_text("hello")

    ingest_file(conn, tmp_path, _scanned(tmp_path, "notes.txt"), warm_thumbnail=False)
    outcome = ingest_file(conn, tmp_path, _scanned(tmp_path, "notes_copy.txt"), warm_thumbnail=False)

    # Hashed and cached (files row exists)...
    row = conn.execute("SELECT content_hash FROM files WHERE path = ?", ("notes_copy.txt",)).fetchone()
    assert row["content_hash"] is not None
    # ...but not dedupe-checked (dedupe is scoped to media, matching core.dedupe).
    assert outcome.duplicate_of is None
