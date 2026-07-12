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


def test_concurrent_writer_waits_instead_of_failing(tmp_path: Path):
    """Two connections — as two concurrent scan jobs hold — must not fail with
    'database is locked': the second writer waits (busy_timeout) for the first
    writer's transaction to commit, then completes."""
    import threading

    db = library_db_path(tmp_path)
    conn1 = open_db(db)

    # conn1 takes the write lock and holds it, mid-transaction.
    conn1.execute("BEGIN IMMEDIATE")
    conn1.execute(
        "INSERT INTO scans (id, type, state) VALUES ('s-dedupe', 'dedupe', 'succeeded')"
    )

    errors: list[Exception] = []
    wrote = threading.Event()

    def second_writer():
        # Own connection in its own thread, exactly like a second scan runner.
        conn2 = open_db(db)
        try:
            conn2.execute(
                "INSERT INTO scans (id, type, state) VALUES ('s-faces', 'faces', 'succeeded')"
            )
            conn2.commit()
            wrote.set()
        except Exception as exc:
            errors.append(exc)
        finally:
            conn2.close()

    t = threading.Thread(target=second_writer, daemon=True)
    t.start()
    # Give the second writer time to hit the held write lock, then release it.
    import time
    time.sleep(0.3)
    conn1.commit()

    t.join(timeout=10)
    assert not t.is_alive(), "second writer never finished"
    assert errors == [], f"second writer failed: {errors}"
    assert wrote.is_set()

    types = {r["type"] for r in conn1.execute("SELECT type FROM scans").fetchall()}
    assert types == {"dedupe", "faces"}
    conn1.close()
