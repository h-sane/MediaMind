"""Embedding cache keyed by (content hash, provider id).

The biggest re-scan win from the V0 handoff: re-running a scan (e.g. after
tuning cluster strictness) skips face detection for every unchanged file,
even if it was renamed or moved, because the key is the file's content hash.

Schema v3 added frame_no and bbox columns to the embeddings table. Rows with
frame_no IS NULL and dim > 0 are pre-v3 entries — treated as cache misses so
bbox data is acquired on the next scan pass.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CachedFace:
    """One face entry as stored in the embedding cache."""

    frame_no: int
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    embedding: np.ndarray                    # float32, L2-normalized


def get_cached_faces(
    conn: sqlite3.Connection, content_hash: str, provider_id: str
) -> list[CachedFace] | None:
    """Return cached faces for a file, or None if never analyzed / pre-v3 rows.

    - None  → file was never analyzed OR has pre-v3 rows (no bbox) → re-detect.
    - []    → analyzed and face-free (no-faces sentinel row with dim=0).
    - list  → previously detected faces with full bbox data.
    """
    rows = conn.execute(
        "SELECT vector, dim, frame_no, bbox_x1, bbox_y1, bbox_x2, bbox_y2 "
        "FROM embeddings WHERE content_hash = ? AND provider_id = ?",
        (content_hash, provider_id),
    ).fetchall()
    if not rows:
        return None
    result: list[CachedFace] = []
    for row in rows:
        if row["dim"] == 0:
            continue  # no-faces sentinel; skip but still a valid cache hit
        if row["frame_no"] is None:
            # Pre-v3 row: bbox not stored → treat as cache miss so we re-detect.
            return None
        result.append(
            CachedFace(
                frame_no=int(row["frame_no"]),
                bbox=(
                    float(row["bbox_x1"]),
                    float(row["bbox_y1"]),
                    float(row["bbox_x2"]),
                    float(row["bbox_y2"]),
                ),
                embedding=np.frombuffer(row["vector"], dtype=np.float32).copy(),
            )
        )
    return result


def put_cached_faces(
    conn: sqlite3.Connection,
    content_hash: str,
    provider_id: str,
    faces: list[CachedFace],
) -> None:
    """Overwrite the cache entry for (content_hash, provider_id)."""
    conn.execute(
        "DELETE FROM embeddings WHERE content_hash = ? AND provider_id = ?",
        (content_hash, provider_id),
    )
    if faces:
        conn.executemany(
            "INSERT INTO embeddings "
            "(content_hash, provider_id, vector, dim, frame_no, bbox_x1, bbox_y1, bbox_x2, bbox_y2) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    content_hash,
                    provider_id,
                    np.asarray(f.embedding, dtype=np.float32).tobytes(),
                    int(f.embedding.shape[0]),
                    f.frame_no,
                    f.bbox[0],
                    f.bbox[1],
                    f.bbox[2],
                    f.bbox[3],
                )
                for f in faces
            ],
        )
    else:
        # No-faces sentinel: analyzed, nothing found.
        conn.execute(
            "INSERT INTO embeddings (content_hash, provider_id, vector, dim) VALUES (?, ?, ?, 0)",
            (content_hash, provider_id, b""),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Back-compat wrappers (used by existing code before M5)
# ---------------------------------------------------------------------------

def get_cached(conn: sqlite3.Connection, content_hash: str, provider_id: str) -> list[np.ndarray] | None:
    """Vector-only cache lookup (pre-M5 callers). None = miss; [] = no faces.

    Does NOT check frame_no — old rows without bboxes are valid cache hits here.
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
    """Vector-only cache write (pre-M5 callers). No bbox stored → pre-v3 compat."""
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
        conn.execute(
            "INSERT INTO embeddings (content_hash, provider_id, vector, dim) VALUES (?, ?, ?, 0)",
            (content_hash, provider_id, b""),
        )
    conn.commit()
