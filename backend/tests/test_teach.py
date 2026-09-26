"""Teach who's who: examples, pooled sorting, lookalike review, idempotence."""

import numpy as np

from mediamind.core.faces import teach
from mediamind.store.db import open_library_db

P = "fake"


def _unit(v):
    return (v / np.linalg.norm(v)).astype(np.float32)


def _add_face(conn, n, emb, person_id=None):
    fid = conn.execute(
        "INSERT INTO files (path, kind, size, mtime, content_hash, decoded_ok) VALUES (?, 'image', 1, 0, ?, 1)",
        (f"A/{n}.jpg", f"h{n}")).lastrowid
    return conn.execute(
        "INSERT INTO faces (file_id, provider_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, embedding, person_id)"
        " VALUES (?, ?, 0, 0, 100, 100, ?, ?)", (fid, P, emb.tobytes(), person_id)).lastrowid


def test_teach_sorts_pools_and_sends_lookalikes_to_review(tmp_path):
    rng = np.random.default_rng(1)
    a, b = _unit(rng.normal(size=64)), _unit(rng.normal(size=64))
    near = lambda c: _unit(c + rng.normal(scale=0.05, size=64))

    (tmp_path / "lib1").mkdir(); (tmp_path / "lib2").mkdir()
    c1 = open_library_db(tmp_path / "lib1")
    ex_a = [_add_face(c1, i, near(a)) for i in range(3)]
    ex_b = [_add_face(c1, 10 + i, near(b)) for i in range(3)]
    teach.add_examples(c1, ex_a, name="Karina")
    teach.add_examples(c1, ex_b, name=" winter ")
    assert len(teach.library_examples(c1, P)) == 6
    blob = c1.execute("INSERT INTO persons (auto_label, provider_id) VALUES ('Person_009', ?)", (P,)).lastrowid
    fa = _add_face(c1, 20, near(a), person_id=blob)
    look = _add_face(c1, 21, _unit(a + b), person_id=blob)
    c1.commit()

    res = teach.apply_teaching(c1, P)
    names = {r["id"]: r["name"] for r in c1.execute("SELECT id, name FROM persons")}
    person_of = lambda f: names.get(c1.execute("SELECT person_id FROM faces WHERE id=?", (f,)).fetchone()[0])
    assert person_of(fa) == "Karina"
    assert person_of(look) != "Karina" and person_of(look) != "winter"   # never silently glued
    assert c1.execute("SELECT COUNT(*) FROM pending_matches WHERE face_id=?", (look,)).fetchone()[0] == 1
    assert res["attached"] == 1
    assert teach.apply_teaching(c1, P)["attached"] == 0                  # idempotent

    # Another library (e.g. watched Downloads) recognises Karina from lib1's examples.
    c2 = open_library_db(tmp_path / "lib2")
    new = _add_face(c2, 1, near(a)); c2.commit()
    foreign, display = teach.pool_foreign_examples([lambda: open_library_db(tmp_path / "lib1")], P)
    teach.apply_teaching(c2, P, foreign, display)
    row = c2.execute("SELECT p.name FROM faces f JOIN persons p ON p.id=f.person_id WHERE f.id=?", (new,)).fetchone()
    assert row["name"] == "Karina"

    teach.remove_examples(c1, ex_a[:1])
    assert len(teach.library_examples(c1, P)) == 5
