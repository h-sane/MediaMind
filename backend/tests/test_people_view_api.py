"""People view API end to end over real per-library DBs: separately scanned
sibling folders group under their shared parent, and pins/collections work
through HTTP."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from mediamind.api.app import create_app
from mediamind.config import library_data_dir
from mediamind.store.db import open_library_db
from mediamind.store.embeddings import CachedFace
from mediamind.store.persons import FileFaces, persist_face_scan, rename_person, upsert_file

PROVIDER = "fake-color"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app()) as c:
        yield c


def _seed(library_root: Path, name: str | None) -> None:
    """One face scan with a single person, optionally named."""
    conn = open_library_db(library_data_dir(library_root).parent)
    fid = upsert_file(conn, "a.jpg", "photo", 100, 0.0, "h_a", True)
    conn.commit()
    ff = [
        FileFaces(
            file_id=fid,
            content_hash="h_a",
            decoded_ok=True,
            faces=[CachedFace(frame_no=0, bbox=(0, 0, 64, 64), embedding=np.array([1.0, 0.0, 0.0], dtype=np.float32))],
        )
    ]
    persist_face_scan(
        conn,
        scan_id="s1",
        provider_id=PROVIDER,
        file_faces=ff,
        labels=np.array([0], dtype=int),
        owners=[0],
        started_at=time.time() - 1,
        finished_at=time.time(),
        params={"provider_id": PROVIDER},
        summary={"files": 1, "faces": 1, "people": 1},
    )
    if name:
        pid = conn.execute("SELECT id FROM persons LIMIT 1").fetchone()["id"]
        rename_person(conn, pid, name)
    conn.close()


def _library(client, path: Path, name: str | None) -> str:
    path.mkdir(parents=True)
    _seed(path, name)
    res = client.post("/v1/libraries", json={"path": str(path)})
    assert res.status_code == 201
    return res.json()["id"]


def test_sibling_libraries_group_under_shared_parent_and_collections_move_people(client, tmp_path):
    _library(client, tmp_path / "kpop" / "twice", "Nayeon")
    _library(client, tmp_path / "kpop" / "ive", "Wonyoung")

    body = client.get("/v1/people-view/overview").json()
    assert {e["name"] for e in body["entries"]} == {"Nayeon", "Wonyoung"}
    assert [n["name"] for n in body["tree"]] == ["kpop"]
    assert [g["name"] for g in body["tree"][0]["subgroups"]] == ["ive", "twice"]

    nayeon = next(e for e in body["entries"] if e["name"] == "Nayeon")
    coll = client.post("/v1/people-view/collections", json={"name": "Favourites"}).json()
    assert client.post(f"/v1/people-view/collections/{coll['id']}/members", json={"keys": nayeon["keys"]}).status_code == 200
    client.post("/v1/people-view/pins", json={"key": nayeon["keys"][0]})

    body = client.get("/v1/people-view/overview").json()
    assert [n["name"] for n in body["tree"]][:1] == ["Favourites"]
    assert body["tree"][0]["person_ids"] == [nayeon["id"]]
    moved = next(e for e in body["entries"] if e["name"] == "Nayeon")
    assert moved["collection_id"] == coll["id"] and moved["pinned"] is True
    assert body["pins"][0]["available"] is True and body["pins"][0]["label"] == "Nayeon"

    client.post("/v1/people-view/collections/remove-members", json={"keys": nayeon["keys"]})
    body = client.get("/v1/people-view/overview").json()
    assert next(e for e in body["entries"] if e["name"] == "Nayeon")["collection_id"] is None


def test_unknown_collection_is_404_and_blank_name_is_422(client):
    assert client.post("/v1/people-view/collections/nope/members", json={"keys": ["p:a:1"]}).status_code == 404
    assert client.post("/v1/people-view/collections", json={"name": "  "}).status_code == 422
