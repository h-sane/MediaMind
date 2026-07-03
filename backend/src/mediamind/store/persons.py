"""Persist face-scan results: persons reconciliation + faces rows.

Single-responsibility: everything that touches `persons`, `faces`,
`pending_matches`, and related aggregation lives here.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field

import numpy as np

from mediamind.store.embeddings import CachedFace

MATCH_SIM_THRESHOLD = 0.5  # = 1 - clustering.DEFAULT_EPS; keep in lockstep


@dataclass(frozen=True)
class PersonSummary:
    id: int
    auto_label: str
    name: str | None
    face_count: int
    media_count: int
    sample_face_ids: list[int]  # up to 4, largest-bbox-area first


@dataclass(frozen=True)
class FaceInfo:
    id: int
    file_id: int
    path: str   # relative to library root (posix)
    kind: str
    frame_no: int
    bbox: tuple[float, float, float, float]
    person_id: int | None
    confidence: float


@dataclass(frozen=True)
class FileFaces:
    """Input to persist_face_scan: one scanned file with its cached faces."""

    file_id: int         # files.id (already upserted)
    content_hash: str    # for logging/debugging
    decoded_ok: bool
    faces: list[CachedFace]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalized_mean(vectors: list[np.ndarray]) -> np.ndarray:
    if not vectors:
        return np.zeros(vectors[0].shape[0] if vectors else 1, dtype=np.float32)
    mean = np.mean(np.stack(vectors), axis=0).astype(np.float32)
    norm = float(np.linalg.norm(mean))
    return mean / norm if norm > 0 else mean


def next_auto_label(conn: sqlite3.Connection, provider_id: str) -> str:
    """Monotonically increasing Person_NNN label (safe after deletes)."""
    row = conn.execute(
        "SELECT auto_label FROM persons WHERE provider_id = ? ORDER BY id DESC LIMIT 1",
        (provider_id,),
    ).fetchone()
    if row is None:
        return "Person_001"
    label = row["auto_label"]
    try:
        n = int(label.split("_")[-1])
    except (ValueError, IndexError):
        n = 0
    return f"Person_{n + 1:03d}"


def upsert_file(
    conn: sqlite3.Connection,
    rel_path: str,
    kind: str,
    size: int,
    mtime: float,
    content_hash: str | None,
    decoded_ok: bool | None,
) -> int:
    """INSERT or UPDATE files row; returns stable files.id for the path."""
    conn.execute(
        """
        INSERT INTO files (path, kind, size, mtime, content_hash, decoded_ok)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            kind=excluded.kind, size=excluded.size, mtime=excluded.mtime,
            content_hash=excluded.content_hash,
            decoded_ok=COALESCE(excluded.decoded_ok, files.decoded_ok)
        """,
        (rel_path, kind, size, mtime, content_hash, int(decoded_ok) if decoded_ok is not None else None),
    )
    row = conn.execute("SELECT id FROM files WHERE path = ?", (rel_path,)).fetchone()
    return int(row["id"])


# ---------------------------------------------------------------------------
# Core persist
# ---------------------------------------------------------------------------

def persist_face_scan(
    conn: sqlite3.Connection,
    *,
    scan_id: str,
    provider_id: str,
    file_faces: list[FileFaces],
    labels: np.ndarray,        # one label per face across all FileFaces, in order
    owners: list[int],         # index into file_faces per label
    started_at: float,
    finished_at: float,
    params: dict,
    summary: dict,
    pending_for_named: bool = False,
    new_file_ids: set[int] | None = None,
) -> dict:
    """Persist a completed face-scan result in a single transaction.

    Steps:
    1. Delete all existing faces (and cascade pending_matches) for this provider.
    2. Compute cluster centroids from current labels.
    3. Greedy-match clusters to existing persons by cosine similarity.
    4. Insert/update person rows.
    5. Insert faces rows; create pending_matches for named persons if requested.
    6. Upsert the scans row (replace any prior faces scan).

    Returns summary dict augmented with people/faces/pending counts.
    """
    # --- 1. snapshot rejected pairs before deleting faces (cascade clears pending_matches) ---
    # We preserve rejections by re-suppressing pending_matches for the same
    # content_hash + frame_no + person_id after the rescan.
    rejected_pairs: set[tuple[str, int, int]] = set()
    for row in conn.execute(
        """
        SELECT fi.content_hash, f.frame_no, pm.person_id
        FROM pending_matches pm
        JOIN faces f ON f.id = pm.face_id
        JOIN files fi ON fi.id = f.file_id
        WHERE pm.decision = 'rejected' AND f.provider_id = ?
        """,
        (provider_id,),
    ):
        if row["content_hash"]:
            rejected_pairs.add((row["content_hash"], row["frame_no"], row["person_id"]))

    conn.execute("DELETE FROM faces WHERE provider_id = ?", (provider_id,))

    # --- 2. cluster centroids ---
    # Group label → list of (file_faces idx, face idx within that file)
    cluster_embeddings: dict[int, list[np.ndarray]] = {}
    cluster_file_faces: dict[int, list[tuple[int, int]]] = {}  # label → [(ff_idx, face_idx)]

    flat_face_idx = 0
    for ff_idx, ff in enumerate(file_faces):
        for face_idx in range(len(ff.faces)):
            if flat_face_idx < len(labels):
                label = int(labels[flat_face_idx])
            else:
                label = -1
            if label != -1:  # noise
                cluster_embeddings.setdefault(label, []).append(ff.faces[face_idx].embedding)
                cluster_face_list = cluster_file_faces.setdefault(label, [])
                cluster_face_list.append((ff_idx, face_idx))
            flat_face_idx += 1

    cluster_centroids = {
        label: _normalized_mean(embs)
        for label, embs in cluster_embeddings.items()
    }
    cluster_sizes = {label: len(embs) for label, embs in cluster_embeddings.items()}

    # --- 3. load existing persons, greedy match (largest cluster first) ---
    existing_persons = conn.execute(
        "SELECT id, auto_label, name, centroid FROM persons WHERE provider_id = ?",
        (provider_id,),
    ).fetchall()

    # person_id → centroid ndarray
    person_centroids: dict[int, np.ndarray] = {}
    for p in existing_persons:
        if p["centroid"]:
            person_centroids[p["id"]] = np.frombuffer(p["centroid"], dtype=np.float32).copy()

    # greedy match: biggest clusters get first pick
    sorted_labels = sorted(cluster_sizes.keys(), key=lambda l: cluster_sizes[l], reverse=True)
    cluster_to_person: dict[int, int] = {}  # cluster label → person id
    matched_persons: set[int] = set()

    for label in sorted_labels:
        centroid = cluster_centroids[label]
        best_sim = MATCH_SIM_THRESHOLD
        best_pid = None
        for pid, pcent in person_centroids.items():
            if pid in matched_persons:
                continue
            sim = float(np.dot(centroid, pcent))
            if sim > best_sim:
                best_sim = sim
                best_pid = pid
        if best_pid is not None:
            cluster_to_person[label] = best_pid
            matched_persons.add(best_pid)

    # --- 4. upsert persons ---
    # update matched persons' centroids
    for label, pid in cluster_to_person.items():
        centroid_blob = cluster_centroids[label].tobytes()
        conn.execute(
            "UPDATE persons SET centroid = ? WHERE id = ?",
            (centroid_blob, pid),
        )

    # new persons for unmatched clusters
    for label in sorted_labels:
        if label not in cluster_to_person:
            auto_label = next_auto_label(conn, provider_id)
            centroid_blob = cluster_centroids[label].tobytes()
            cur = conn.execute(
                "INSERT INTO persons (auto_label, name, provider_id, centroid) VALUES (?, NULL, ?, ?)",
                (auto_label, provider_id, centroid_blob),
            )
            cluster_to_person[label] = cur.lastrowid  # type: ignore[assignment]

    # remove persons with no matching cluster
    matched_person_ids = set(cluster_to_person.values())
    for p in existing_persons:
        if p["id"] not in matched_person_ids:
            if p["name"] is None:
                conn.execute("DELETE FROM persons WHERE id = ?", (p["id"],))
            # named persons kept with 0 faces (user knows who they are)

    # --- 5. insert faces ---
    new_file_ids = new_file_ids or set()
    pending_count = 0

    # build named-person set for pending logic
    named_person_ids: set[int] = set()
    if pending_for_named:
        for p in conn.execute(
            "SELECT id FROM persons WHERE provider_id = ? AND name IS NOT NULL",
            (provider_id,),
        ):
            named_person_ids.add(p["id"])

    flat_face_idx = 0
    for ff in file_faces:
        for face_idx, cached_face in enumerate(ff.faces):
            if flat_face_idx < len(labels):
                label = int(labels[flat_face_idx])
            else:
                label = -1

            assigned_pid = cluster_to_person.get(label)  # None for noise

            embedding_blob = np.asarray(cached_face.embedding, dtype=np.float32).tobytes()
            cur = conn.execute(
                """
                INSERT INTO faces
                  (file_id, provider_id, frame_no,
                   bbox_x1, bbox_y1, bbox_x2, bbox_y2,
                   embedding, person_id, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ff.file_id,
                    provider_id,
                    cached_face.frame_no,
                    cached_face.bbox[0],
                    cached_face.bbox[1],
                    cached_face.bbox[2],
                    cached_face.bbox[3],
                    embedding_blob,
                    assigned_pid,   # will be patched below if pending
                    1.0 if assigned_pid is not None else 0.0,
                ),
            )
            face_db_id = cur.lastrowid

            # M6 pending logic: new file + assigned to a named person → stage as pending
            # Skip faces the user already rejected (same content_hash + frame_no + person).
            was_rejected = (ff.content_hash, cached_face.frame_no, assigned_pid) in rejected_pairs
            if (
                pending_for_named
                and assigned_pid in named_person_ids
                and ff.file_id in new_file_ids
                and not was_rejected
            ):
                confidence = float(np.dot(cached_face.embedding, cluster_centroids[label]))
                conn.execute(
                    "INSERT INTO pending_matches (face_id, person_id, confidence) VALUES (?, ?, ?)",
                    (face_db_id, assigned_pid, confidence),
                )
                conn.execute(
                    "UPDATE faces SET person_id = NULL WHERE id = ?",
                    (face_db_id,),
                )
                pending_count += 1

            flat_face_idx += 1

    # --- 6. upsert scan row (replace any prior faces scan) ---
    conn.execute("DELETE FROM scans WHERE type = 'faces'")
    final_summary = {**summary, "pending": pending_count}
    conn.execute(
        """
        INSERT INTO scans (id, type, state, params, started_at, finished_at, summary)
        VALUES (?, 'faces', 'succeeded', ?, ?, ?, ?)
        """,
        (
            scan_id,
            json.dumps(params),
            started_at,
            finished_at,
            json.dumps(final_summary),
        ),
    )
    conn.commit()
    return final_summary


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def latest_faces_scan(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM scans WHERE type = 'faces' ORDER BY finished_at DESC LIMIT 1"
    ).fetchone()


def list_person_summaries(conn: sqlite3.Connection, provider_id: str) -> list[PersonSummary]:
    persons = conn.execute(
        "SELECT id, auto_label, name FROM persons WHERE provider_id = ?",
        (provider_id,),
    ).fetchall()

    result = []
    for p in persons:
        pid = p["id"]
        face_count = conn.execute(
            "SELECT COUNT(*) FROM faces WHERE person_id = ? AND provider_id = ?",
            (pid, provider_id),
        ).fetchone()[0]
        media_count = conn.execute(
            "SELECT COUNT(DISTINCT file_id) FROM faces WHERE person_id = ? AND provider_id = ?",
            (pid, provider_id),
        ).fetchone()[0]
        # Sample faces: up to 4, largest bbox area first
        sample_rows = conn.execute(
            """
            SELECT id, (bbox_x2 - bbox_x1) * (bbox_y2 - bbox_y1) AS area
            FROM faces WHERE person_id = ? AND provider_id = ?
            ORDER BY area DESC LIMIT 4
            """,
            (pid, provider_id),
        ).fetchall()
        sample_face_ids = [r["id"] for r in sample_rows]
        result.append(
            PersonSummary(
                id=pid,
                auto_label=p["auto_label"],
                name=p["name"],
                face_count=face_count,
                media_count=media_count,
                sample_face_ids=sample_face_ids,
            )
        )
    return result


def rename_person(conn: sqlite3.Connection, person_id: int, name: str | None) -> bool:
    cur = conn.execute(
        "UPDATE persons SET name = ? WHERE id = ?",
        (name if name and name.strip() else None, person_id),
    )
    conn.commit()
    return cur.rowcount > 0


def merge_persons(conn: sqlite3.Connection, source_id: int, target_id: int) -> bool:
    """Move all faces from source to target, recompute centroid, delete source."""
    if source_id == target_id:
        return False
    source = conn.execute("SELECT provider_id FROM persons WHERE id = ?", (source_id,)).fetchone()
    target = conn.execute("SELECT provider_id FROM persons WHERE id = ?", (target_id,)).fetchone()
    if source is None or target is None:
        return False
    if source["provider_id"] != target["provider_id"]:
        return False

    conn.execute(
        "UPDATE faces SET person_id = ? WHERE person_id = ?",
        (target_id, source_id),
    )
    conn.execute("DELETE FROM persons WHERE id = ?", (source_id,))

    # Recompute centroid for target from its faces' embeddings
    rows = conn.execute(
        "SELECT embedding FROM faces WHERE person_id = ?", (target_id,)
    ).fetchall()
    if rows:
        vectors = [np.frombuffer(r["embedding"], dtype=np.float32).copy() for r in rows]
        new_centroid = _normalized_mean(vectors)
        conn.execute(
            "UPDATE persons SET centroid = ? WHERE id = ?",
            (new_centroid.tobytes(), target_id),
        )

    conn.commit()
    return True


def get_face(conn: sqlite3.Connection, face_id: int) -> FaceInfo | None:
    row = conn.execute(
        """
        SELECT f.id, f.file_id, fi.path, fi.kind,
               f.frame_no, f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2,
               f.person_id, f.confidence
        FROM faces f JOIN files fi ON fi.id = f.file_id
        WHERE f.id = ?
        """,
        (face_id,),
    ).fetchone()
    if row is None:
        return None
    return FaceInfo(
        id=row["id"],
        file_id=row["file_id"],
        path=row["path"],
        kind=row["kind"],
        frame_no=row["frame_no"],
        bbox=(row["bbox_x1"], row["bbox_y1"], row["bbox_x2"], row["bbox_y2"]),
        person_id=row["person_id"],
        confidence=row["confidence"],
    )


def person_media(conn: sqlite3.Connection, person_id: int) -> list[FaceInfo]:
    """One FaceInfo per distinct file for this person (the face with largest bbox)."""
    rows = conn.execute(
        """
        SELECT f.id, f.file_id, fi.path, fi.kind,
               f.frame_no, f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2,
               f.person_id, f.confidence
        FROM faces f JOIN files fi ON fi.id = f.file_id
        WHERE f.person_id = ?
          AND f.id = (
              SELECT f2.id FROM faces f2
              WHERE f2.file_id = f.file_id AND f2.person_id = ?
              ORDER BY (f2.bbox_x2 - f2.bbox_x1) * (f2.bbox_y2 - f2.bbox_y1) DESC
              LIMIT 1
          )
        ORDER BY fi.path
        """,
        (person_id, person_id),
    ).fetchall()
    return [
        FaceInfo(
            id=r["id"],
            file_id=r["file_id"],
            path=r["path"],
            kind=r["kind"],
            frame_no=r["frame_no"],
            bbox=(r["bbox_x1"], r["bbox_y1"], r["bbox_x2"], r["bbox_y2"]),
            person_id=r["person_id"],
            confidence=r["confidence"],
        )
        for r in rows
    ]


def file_ids_with_faces(conn: sqlite3.Connection, provider_id: str) -> set[int]:
    """Return file_ids that already have faces rows for this provider."""
    rows = conn.execute(
        "SELECT DISTINCT file_id FROM faces WHERE provider_id = ?", (provider_id,)
    ).fetchall()
    return {r["file_id"] for r in rows}
