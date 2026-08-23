"""Tests for core/folder_faces.py — the named-people-in-a-folder lookup that
drives the Explorer's face folder icons. Model-free (fake color embeddings)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from mediamind.config import library_data_dir
from mediamind.core.folder_faces import _is_under, folder_named_persons, invalidate_cache
from mediamind.store.db import library_db_path, open_db
from mediamind.store.embeddings import CachedFace
from mediamind.store.persons import FileFaces, persist_face_scan, upsert_file

PROVIDER = "fake-color"


@dataclass
class _Lib:
    id: str
    path: str
    name: str = "Lib"


class _Registry:
    def __init__(self, libs: list[_Lib]) -> None:
        self._libs = libs

    def list(self) -> list[_Lib]:
        return self._libs


def _emb(r: float, g: float, b: float) -> np.ndarray:
    v = np.array([r, g, b], dtype=np.float32)
    return v / (np.linalg.norm(v) or 1.0)


def _face(r: float, g: float, b: float) -> CachedFace:
    return CachedFace(frame_no=0, bbox=(0.0, 0.0, 64.0, 64.0), embedding=_emb(r, g, b))


def _seed_two_person_family(conn) -> tuple[int, int]:
    """Alice (red) under Family/Alice, Bob (green) under Family/Bob. Returns
    (alice_person_id, bob_person_id); both start unnamed."""
    specs: list[tuple[str, int, tuple[float, float, float]]] = []
    specs += [(f"Family/Alice/a{i}.jpg", 0, (1, 0, 0)) for i in range(6)]
    specs += [(f"Family/Bob/b{i}.jpg", 1, (0, 1, 0)) for i in range(6)]

    file_faces, labels = [], []
    for rel, label, color in specs:
        fid = upsert_file(conn, rel, "photo", 100, 0.0, rel, True)
        file_faces.append(FileFaces(file_id=fid, content_hash=rel, decoded_ok=True, faces=[_face(*color)]))
        labels.append(label)
    conn.commit()

    persist_face_scan(
        conn,
        scan_id="s1",
        provider_id=PROVIDER,
        file_faces=file_faces,
        labels=np.array(labels, dtype=int),
        owners=list(range(len(specs))),
        started_at=time.time() - 1,
        finished_at=time.time(),
        params={"provider_id": PROVIDER},
        summary={"files": len(specs), "faces": len(specs), "people": 2},
    )

    def pid_under(prefix: str) -> int:
        return conn.execute(
            "SELECT DISTINCT f.person_id FROM faces f JOIN files fi ON fi.id = f.file_id "
            "WHERE fi.path LIKE ? AND f.provider_id = ?",
            (prefix + "%", PROVIDER),
        ).fetchone()[0]

    return pid_under("Family/Alice"), pid_under("Family/Bob")


@pytest.fixture
def registry(tmp_path: Path):
    invalidate_cache()  # module-level cache is keyed by library id — don't leak across tests
    root = tmp_path / "media"
    root.mkdir()
    (root / "Family" / "Alice").mkdir(parents=True)
    (root / "Family" / "Bob").mkdir(parents=True)
    conn = open_db(library_db_path(library_data_dir(root)))
    try:
        alice, bob = _seed_two_person_family(conn)
        yield _Registry([_Lib(id="lib1", path=str(root))]), root, conn, alice, bob
    finally:
        conn.close()


def test_is_under():
    assert _is_under("Family/Alice/a.jpg", "Family")
    assert _is_under("Family/Alice/a.jpg", "Family/Alice")
    assert not _is_under("Family/Bob/b.jpg", "Family/Alice")
    assert _is_under("anything.jpg", "")  # library root contains everything


def test_leaf_folder_shows_only_its_named_person(registry):
    reg, root, conn, alice, _bob = registry
    conn.execute("UPDATE persons SET name = 'Alice' WHERE id = ?", (alice,))
    conn.commit()

    result = folder_named_persons(reg, root / "Family" / "Alice")
    assert result is not None
    assert result.library_id == "lib1"
    assert [p.name for p in result.persons] == ["Alice"]
    assert result.total_persons == 1
    assert result.persons[0].sample_face_id > 0


def test_parent_folder_ignores_unnamed_person(registry):
    reg, root, conn, alice, _bob = registry
    conn.execute("UPDATE persons SET name = 'Alice' WHERE id = ?", (alice,))
    conn.commit()

    # Bob is still unnamed -> the recursive Family view shows only Alice.
    result = folder_named_persons(reg, root / "Family")
    assert result is not None
    assert [p.name for p in result.persons] == ["Alice"]
    assert result.total_persons == 1


def test_parent_folder_shows_group_once_both_named(registry):
    reg, root, conn, alice, bob = registry
    conn.execute("UPDATE persons SET name = 'Alice' WHERE id = ?", (alice,))
    conn.execute("UPDATE persons SET name = 'Bob' WHERE id = ?", (bob,))
    conn.commit()

    result = folder_named_persons(reg, root / "Family")
    assert result is not None
    assert result.total_persons == 2
    assert {p.name for p in result.persons} == {"Alice", "Bob"}


def test_folder_outside_any_library_returns_none(tmp_path, registry):
    reg, _root, _conn, _alice, _bob = registry
    assert folder_named_persons(reg, tmp_path / "somewhere-else") is None


def test_no_named_people_returns_none(registry):
    reg, root, _conn, _alice, _bob = registry
    # Neither person named -> nothing to show, fall back to the plain icon.
    assert folder_named_persons(reg, root / "Family") is None
