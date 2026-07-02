"""Embedding cache keyed by (content hash, provider id).

The biggest re-scan win from the V0 handoff: re-running a scan (e.g. after
tuning cluster strictness) skips face detection for every unchanged file,
even if it was renamed or moved, because the key is the file's content hash.
"""

from __future__ import annotations

import sqlite3

import numpy as np


def get_cached(conn: sqlite3.Connection, content_hash: str, provider_id: str) -> list[np.ndarray] | None:
    """Cached embeddings for a file, or None if this file was never analyzed.

    A file analyzed and found face-free is cached as an empty list (a
    sentinel row with an empty vector) so it isn't re-analyzed either.
    """
    rows = conn.execute(
        "SELECT vector, dim FROM embeddings WHERE content_hash = ? AND provider_id = ?",
        (content_hash, provider_id),
    ).fetchall()
    if not rows:
        return None
    result: list[np.ndarray] = []
    for row in rows:
        if row["dim"] == 0:
            continue  # no-faces sentinel
        result.append(np.frombuffer(row["vector"], dtype=np.float32).copy())
    return result


def put_cached(
    conn: sqlite3.Connection,
    content_hash: str,
    provider_id: str,
    embeddings: list[np.ndarray],
) -> None:
    conn.execute(
        "DELETE FROM embeddings WHERE content_hash = ? AND provider_id = ?",
        (content_hash, provider_id),
    )
    if embeddings:
        conn.executemany(
            "INSERT INTO embeddings (content_hash, provider_id, vector, dim) VALUES (?, ?, ?, ?)",
            [
                (content_hash, provider_id, np.asarray(e, dtype=np.float32).tobytes(), int(e.shape[0]))
                for e in embeddings
            ],
        )
    else:
        # no-faces sentinel: analyzed, nothing found
        conn.execute(
            "INSERT INTO embeddings (content_hash, provider_id, vector, dim) VALUES (?, ?, ?, 0)",
            (content_hash, provider_id, b""),
        )
    conn.commit()
