from pathlib import Path

import numpy as np

from mediamind.core.hashing import hash_file
from mediamind.store.db import library_db_path, open_db
from mediamind.store.embeddings import get_cached, put_cached


def test_hash_is_content_based(tmp_path: Path):
    a = tmp_path / "a.bin"
    b = tmp_path / "renamed.bin"
    a.write_bytes(b"same content")
    b.write_bytes(b"same content")
    c = tmp_path / "c.bin"
    c.write_bytes(b"different")
    assert hash_file(a) == hash_file(b)
    assert hash_file(a) != hash_file(c)


def test_embedding_cache_roundtrip(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    vecs = [np.random.rand(512).astype(np.float32) for _ in range(3)]
    put_cached(conn, "hash1", "buffalo_l", vecs)

    got = get_cached(conn, "hash1", "buffalo_l")
    assert got is not None and len(got) == 3
    for original, cached in zip(vecs, got):
        assert np.allclose(original, cached)


def test_cache_miss_vs_no_faces_sentinel(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    assert get_cached(conn, "never-seen", "p") is None  # miss -> must analyze

    put_cached(conn, "analyzed-empty", "p", [])  # analyzed, zero faces
    assert get_cached(conn, "analyzed-empty", "p") == []  # hit -> skip re-analysis


def test_cache_is_per_provider(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    put_cached(conn, "h", "provider-a", [np.ones(4, dtype=np.float32)])
    assert get_cached(conn, "h", "provider-b") is None


def test_reput_replaces(tmp_path: Path):
    conn = open_db(library_db_path(tmp_path))
    put_cached(conn, "h", "p", [np.ones(4, dtype=np.float32)])
    put_cached(conn, "h", "p", [np.zeros(4, dtype=np.float32), np.ones(4, dtype=np.float32)])
    got = get_cached(conn, "h", "p")
    assert got is not None and len(got) == 2


def test_db_opens_twice_idempotently(tmp_path: Path):
    from mediamind.store.db import SCHEMA_VERSION
    open_db(library_db_path(tmp_path)).close()
    conn = open_db(library_db_path(tmp_path))
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    assert row["value"] == str(SCHEMA_VERSION)
