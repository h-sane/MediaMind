"""Fold repeated review questions: the same person's face in several frames of one video
(or in byte-identical copies of one file) is one question, not one per frame.

A file key (content hash, else file id) and a suggested person define a bucket. Within it,
the most confident question stands for every face that looks like the same individual
(cosine similarity >= SAME_FACE_SIM to it). Faces below that stay separate questions: a
video can hold two people who were both suggested as the same name.

SAME_FACE_SIM comes from the kpop library (2026-09-27): 99.9% of pairs of different named
people score <= 0.44, so 0.45 folds frames of one person without folding lookalikes.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

import numpy as np

SAME_FACE_SIM = 0.45

_ROWS = """
    SELECT pm.id, pm.person_id, pm.confidence, f.embedding,
           COALESCE(fi.content_hash, 'file:' || fi.id) AS file_key
    FROM pending_matches pm
    JOIN faces f ON f.id = pm.face_id
    JOIN files fi ON fi.id = f.file_id
    WHERE pm.decision IS NULL
"""


def _unit(blob: bytes) -> np.ndarray:
    v = np.frombuffer(blob, dtype=np.float32)
    n = np.linalg.norm(v)
    return v / n if n else v


def fold(rows: list[sqlite3.Row]) -> dict[int, list[int]]:
    """Map each representative pending id to the pending ids it stands for (itself excluded).

    `rows` need id, person_id, confidence, embedding and file_key. Ids that are folded
    into another one do not appear as keys.
    """
    buckets: dict[tuple[str, int], list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        buckets[(r["file_key"], r["person_id"])].append(r)

    folded: dict[int, list[int]] = {}
    for bucket in buckets.values():
        left = sorted(bucket, key=lambda r: -r["confidence"])
        while left:
            rep, rest = left[0], left[1:]
            v = _unit(rep["embedding"])
            same = [r for r in rest if float(v @ _unit(r["embedding"])) >= SAME_FACE_SIM]
            folded[rep["id"]] = [r["id"] for r in same]
            left = [r for r in rest if r not in same]
    return folded


def open_folded(conn: sqlite3.Connection) -> dict[int, list[int]]:
    """`fold` over every undecided pending match."""
    return fold(conn.execute(_ROWS).fetchall())


def siblings_of(conn: sqlite3.Connection, pending_id: int) -> list[int]:
    """Undecided pending ids folded into `pending_id` (empty if it stands alone)."""
    return open_folded(conn).get(pending_id, [])
