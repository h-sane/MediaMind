"""Teach who's who: user-named example faces drive person assignment.

An *example* is any face the user explicitly put on a person — a durable
`face_assignments` row with `source='user'` (taught here, confirmed from
review, or moved by hand). Examples are pooled across every registered
library by person name, so Karina taught once is recognised everywhere
(the watched Downloads folder included).

`apply_teaching` re-sorts one library's already-detected faces against those
examples with `classify.classify` — no rescan, pure numpy. Confident matches
are attached, borderline ones become pending review (never silent), and faces
that no longer match a taught person are detached from it.
See docs/PEOPLE_TEACHING_DESIGN.md.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from mediamind.core.faces import classify as clf
from mediamind.store import face_assignments, rejected_matches
from mediamind.store.persons import next_auto_label


@dataclass(frozen=True)
class Example:
    face_id: int
    person_id: int
    name: str | None
    embedding: np.ndarray


def name_key(name: str) -> str:
    return " ".join(name.split()).casefold()


def _faces_with_hash(conn: sqlite3.Connection, provider_id: str):
    return conn.execute(
        """
        SELECT f.id, f.file_id, f.person_id, f.embedding,
               f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, fi.content_hash
        FROM faces f JOIN files fi ON fi.id = f.file_id
        WHERE f.provider_id = ?
        """,
        (provider_id,),
    ).fetchall()


def library_examples(conn: sqlite3.Connection, provider_id: str, rows=None) -> list[Example]:
    """Faces in this library that carry a user assignment to their current person."""
    by_hash: dict[str, list[face_assignments.Assignment]] = defaultdict(list)
    for a in conn.execute(
        """SELECT id, content_hash, bbox_x1, bbox_y1, bbox_x2, bbox_y2, person_id, source
           FROM face_assignments WHERE provider_id = ? AND source = 'user'""",
        (provider_id,),
    ):
        by_hash[a["content_hash"]].append(face_assignments.Assignment(
            id=a["id"], person_id=a["person_id"], source=a["source"],
            bbox=(a["bbox_x1"], a["bbox_y1"], a["bbox_x2"], a["bbox_y2"]),
        ))
    if not by_hash:
        return []
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM persons")}
    out = []
    for r in rows if rows is not None else _faces_with_hash(conn, provider_id):
        cands = by_hash.get(r["content_hash"])
        if not cands:
            continue
        m = face_assignments.find_assignment(cands, (r["bbox_x1"], r["bbox_y1"], r["bbox_x2"], r["bbox_y2"]))
        if m is not None and m.person_id == r["person_id"]:
            out.append(Example(r["id"], m.person_id, names.get(m.person_id),
                               np.frombuffer(r["embedding"], dtype=np.float32)))
    return out


def named_examples(conn: sqlite3.Connection, provider_id: str) -> dict[str, list[np.ndarray]]:
    """This library's examples for *named* people, keyed by name — what other
    libraries borrow."""
    out: dict[str, list[np.ndarray]] = defaultdict(list)
    for e in library_examples(conn, provider_id):
        if e.name:
            out[name_key(e.name)].append(e.embedding)
    return dict(out)


def pool_foreign_examples(
    open_conns: Iterable[Callable[[], sqlite3.Connection]], provider_id: str,
) -> tuple[dict[str, list[np.ndarray]], dict[str, str]]:
    """Named examples from other libraries. Unreachable libraries are skipped
    (an offline drive must never block sorting). Returns (examples, display names)."""
    pooled: dict[str, list[np.ndarray]] = defaultdict(list)
    display: dict[str, str] = {}
    for opener in open_conns:
        try:
            conn = opener()
        except (OSError, sqlite3.Error, Exception):  # LibraryOffline and friends
            continue
        try:
            names = {name_key(r["name"]): r["name"] for r in conn.execute(
                "SELECT name FROM persons WHERE name IS NOT NULL AND provider_id = ?", (provider_id,))}
            for k, embs in named_examples(conn, provider_id).items():
                pooled[k].extend(embs)
                display.setdefault(k, names.get(k, k))
        except sqlite3.Error:
            pass
        finally:
            conn.close()
    return dict(pooled), display


def _ensure_person(conn: sqlite3.Connection, provider_id: str, name: str) -> int:
    for r in conn.execute("SELECT id, name FROM persons WHERE name IS NOT NULL AND provider_id = ? ORDER BY id",
                          (provider_id,)):
        if name_key(r["name"]) == name_key(name):
            return r["id"]
    cur = conn.execute(
        "INSERT INTO persons (auto_label, name, provider_id) VALUES (?, ?, ?)",
        (next_auto_label(conn, provider_id), " ".join(name.split()), provider_id),
    )
    return cur.lastrowid


def add_examples(conn: sqlite3.Connection, face_ids: list[int], *, person_id: int | None = None,
                 name: str | None = None) -> int:
    """Mark faces as examples of a person (existing id, or a name — found or created)."""
    row = conn.execute("SELECT provider_id FROM faces WHERE id = ?", (face_ids[0],)).fetchone() if face_ids else None
    if row is None:
        raise ValueError("unknown face")
    if person_id is None:
        if not name or not name.strip():
            raise ValueError("a person id or a name is required")
        person_id = _ensure_person(conn, row["provider_id"], name)
    for fid in face_ids:
        f = conn.execute(
            """SELECT f.provider_id, f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, fi.content_hash
               FROM faces f JOIN files fi ON fi.id = f.file_id WHERE f.id = ?""", (fid,)).fetchone()
        if f is None:
            continue
        conn.execute("UPDATE faces SET person_id = ? WHERE id = ?", (person_id, fid))
        conn.execute("DELETE FROM pending_matches WHERE face_id = ? AND decision IS NULL", (fid,))
        if f["content_hash"]:
            face_assignments.record_assignment(
                conn, f["content_hash"], f["provider_id"],
                (f["bbox_x1"], f["bbox_y1"], f["bbox_x2"], f["bbox_y2"]), person_id, source="user")
    conn.commit()
    return person_id


def remove_examples(conn: sqlite3.Connection, face_ids: list[int]) -> None:
    """Un-teach: drop the user assignment and detach the face (the next sort decides again)."""
    for fid in face_ids:
        f = conn.execute(
            """SELECT f.provider_id, f.person_id, f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, fi.content_hash
               FROM faces f JOIN files fi ON fi.id = f.file_id WHERE f.id = ?""", (fid,)).fetchone()
        if f is None or f["person_id"] is None:
            continue
        existing = face_assignments.assignments_for(conn, f["content_hash"], f["provider_id"])
        m = face_assignments.find_assignment(existing, (f["bbox_x1"], f["bbox_y1"], f["bbox_x2"], f["bbox_y2"]))
        if m is not None:
            conn.execute("DELETE FROM face_assignments WHERE id = ?", (m.id,))
        conn.execute("UPDATE faces SET person_id = NULL WHERE id = ?", (fid,))
    conn.commit()


def apply_teaching(
    conn: sqlite3.Connection,
    provider_id: str,
    foreign: dict[str, list[np.ndarray]] | None = None,
    foreign_display: dict[str, str] | None = None,
) -> dict:
    """Re-sort this library's faces against every example (local + foreign).
    Returns {"people": [{person_id, name, files, examples}], "attached", "pending", "detached"}."""
    rows = _faces_with_hash(conn, provider_id)
    local = library_examples(conn, provider_id, rows)
    example_ids = {e.face_id for e in local}

    # key -> embeddings; key is a name for named people (pooled everywhere),
    # ("pid", id) for an unnamed local person that has examples.
    pool: dict = defaultdict(list)
    key_person: dict = {}
    for e in local:
        key = name_key(e.name) if e.name else ("pid", e.person_id)
        pool[key].append(e.embedding)
        key_person.setdefault(key, e.person_id)
    for k, embs in (foreign or {}).items():
        pool[k].extend(embs)
    if not pool:
        return {"people": [], "attached": 0, "pending": 0, "detached": 0}
    examples = {k: np.asarray(v, dtype=np.float32) for k, v in pool.items()}

    todo = [r for r in rows if r["id"] not in example_ids]
    verdicts = clf.classify(
        np.asarray([np.frombuffer(r["embedding"], dtype=np.float32) for r in todo], dtype=np.float32).reshape(len(todo), -1),
        examples,
    ) if todo else []

    def person_for(key) -> int:
        if key not in key_person:
            key_person[key] = _ensure_person(conn, provider_id, (foreign_display or {}).get(key, key))
        return key_person[key]

    rejected = {(r["face_id"], r["person_id"]) for r in conn.execute(
        "SELECT face_id, person_id FROM pending_matches WHERE decision = 'rejected'")}
    said_no = rejected_matches.load(conn, provider_id)  # the same Nos, surviving rescans
    conn.execute(
        "DELETE FROM pending_matches WHERE decision IS NULL AND face_id IN (SELECT id FROM faces WHERE provider_id = ?)",
        (provider_id,))
    for k in list(examples):  # resolve local ids for foreign-only names that already exist here
        if isinstance(k, str) and k not in key_person:
            for r in conn.execute("SELECT id, name FROM persons WHERE name IS NOT NULL AND provider_id = ?", (provider_id,)):
                if name_key(r["name"]) == k:
                    key_person[k] = r["id"]
                    break
    taught_ids = set(key_person.values())

    attached = pending = detached = 0
    for r, v in zip(todo, verdicts):
        bbox = (r["bbox_x1"], r["bbox_y1"], r["bbox_x2"], r["bbox_y2"])
        target = person_for(v.person) if v.decision in (clf.AUTO, clf.PENDING) else None
        refused = (r["id"], target) in rejected or (
            target is not None and rejected_matches.is_rejected(said_no, r["content_hash"], bbox, target))
        if v.decision == clf.AUTO and not refused:
            if r["person_id"] != target:
                conn.execute("UPDATE faces SET person_id = ? WHERE id = ?", (target, r["id"]))
                attached += 1
            if r["content_hash"]:
                face_assignments.record_assignment(conn, r["content_hash"], provider_id, bbox, target, source="cluster")
            continue
        if r["person_id"] is not None and r["person_id"] in taught_ids | ({target} if target else set()):
            conn.execute("UPDATE faces SET person_id = NULL WHERE id = ?", (r["id"],))
            if r["content_hash"]:
                conn.execute(
                    """DELETE FROM face_assignments WHERE content_hash = ? AND provider_id = ?
                       AND person_id = ? AND source = 'cluster'""",
                    (r["content_hash"], provider_id, r["person_id"]))
            detached += 1
        if v.decision == clf.PENDING and not refused:
            conn.execute(
                "INSERT INTO pending_matches (face_id, person_id, confidence, decision) VALUES (?, ?, ?, NULL)",
                (r["id"], target, v.score))
            pending += 1

    for key, pid in key_person.items():
        c = examples[key].mean(axis=0)
        conn.execute("UPDATE persons SET centroid = ? WHERE id = ?",
                     ((c / max(np.linalg.norm(c), 1e-12)).astype(np.float32).tobytes(), pid))
    conn.commit()

    people = []
    for key, pid in key_person.items():
        r = conn.execute(
            "SELECT p.name, p.auto_label, COUNT(DISTINCT f.file_id) AS n FROM persons p "
            "LEFT JOIN faces f ON f.person_id = p.id WHERE p.id = ? GROUP BY p.id", (pid,)).fetchone()
        people.append({"person_id": pid, "name": r["name"] or r["auto_label"], "files": r["n"],
                       "examples": len(examples[key])})
    people.sort(key=lambda p: -p["files"])
    return {"people": people, "attached": attached, "pending": pending, "detached": detached}


def apply_in_registry(registry, library_id: str, conn: sqlite3.Connection, provider_id: str) -> dict:
    """apply_teaching with examples pooled from every other registered library."""
    from mediamind.store.db import open_library_db

    openers = [(lambda p=lib.path: open_library_db(Path(p))) for lib in registry.list() if lib.id != library_id]
    foreign, display = pool_foreign_examples(openers, provider_id)
    return apply_teaching(conn, provider_id, foreign, display)
