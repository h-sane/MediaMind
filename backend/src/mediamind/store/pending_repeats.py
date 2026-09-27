"""Which review questions are asked: one per file and person, never one already answered.

Every open pending match is checked against the user's durable answers first. It is not asked if:
  - that face already has a user answer (face_assignments, source 'user');
  - the same file content was already confirmed for that person (a Yes on one face of a video
    settles the video for that person; its other frames add nothing the user needs to answer);
  - the user said No (or ignored a face) for that person anywhere in the same file content
    (rejected_matches, which survives rescans). Asking the next frame after a No read as the
    same question again (2026-09-27); a second real face of that person in the file is the
    rarer loss.
Answers are keyed by content hash (+ bbox), so all of this survives rescans and rebuilds.

The rest are bucketed by file content and suggested person, and one question per bucket is
shown: the most confident. Faces in the bucket that look like the same individual (cosine >=
SAME_FACE_SIM to it) are folded into it and decided with it. Any answer to it settles the
bucket.

SAME_FACE_SIM comes from the kpop library (2026-09-27): 99.9% of pairs of different named
people score <= 0.44, so 0.45 folds frames of one person without folding lookalikes.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

import numpy as np

from mediamind.store.face_assignments import ASSIGNMENT_IOU_THRESHOLD
from mediamind.store.rejected_faces import _iou

SAME_FACE_SIM = 0.45

_ROWS = """
    SELECT pm.id, pm.person_id, pm.confidence, f.embedding, f.provider_id,
           f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, fi.content_hash,
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


def _bbox(r) -> tuple[float, float, float, float]:
    return (r["bbox_x1"], r["bbox_y1"], r["bbox_x2"], r["bbox_y2"])


def fold(rows: list[sqlite3.Row]) -> dict[int, list[int]]:
    """Map each question to ask (pending id) to the pending ids decided with it.

    `rows` need id, person_id, confidence, embedding and file_key. Ids that are folded into
    another one, or that wait behind it, do not appear as keys.
    """
    buckets: dict[tuple[str, int], list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        buckets[(r["file_key"], r["person_id"])].append(r)

    folded: dict[int, list[int]] = {}
    for bucket in buckets.values():
        rep, *rest = sorted(bucket, key=lambda r: -r["confidence"])
        v = _unit(rep["embedding"])
        folded[rep["id"]] = [r["id"] for r in rest if float(v @ _unit(r["embedding"])) >= SAME_FACE_SIM]
    return folded


def _answered(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> set[int]:
    """Pending ids the user has in effect already answered (see the module docstring)."""
    user: dict[str, list] = defaultdict(list)
    for a in conn.execute(
        "SELECT content_hash, bbox_x1, bbox_y1, bbox_x2, bbox_y2, person_id FROM face_assignments WHERE source = 'user'"
    ):
        user[a["content_hash"]].append(((a["bbox_x1"], a["bbox_y1"], a["bbox_x2"], a["bbox_y2"]), a["person_id"]))
    said_no = {(a["content_hash"], a["person_id"]) for a in conn.execute("SELECT content_hash, person_id FROM rejected_matches")}

    done: set[int] = set()
    for r in rows:
        ch, bbox = r["content_hash"], _bbox(r)
        if not ch:
            continue
        answers = user.get(ch, [])
        if (any(pid == r["person_id"] for _, pid in answers)
                or any(_iou(b, bbox) >= ASSIGNMENT_IOU_THRESHOLD for b, _ in answers)
                or (ch, r["person_id"]) in said_no):
            done.add(r["id"])
    return done


def open_folded(conn: sqlite3.Connection) -> dict[int, list[int]]:
    """The questions to ask now, over every undecided pending match."""
    rows = conn.execute(_ROWS).fetchall()
    done = _answered(conn, rows)
    return fold([r for r in rows if r["id"] not in done])
