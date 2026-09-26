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


def test_hidden_person_leaves_the_overview_and_can_be_restored(client, tmp_path):
    _library(client, tmp_path / "a", "Nayeon")
    _library(client, tmp_path / "b", "Wonyoung")
    nayeon = next(e for e in client.get("/v1/people-view/overview").json()["entries"] if e["name"] == "Nayeon")

    client.post("/v1/people-view/pins", json={"key": nayeon["keys"][0]})
    assert client.post("/v1/people-view/hide", json={"keys": nayeon["keys"]}).status_code == 200
    body = client.get("/v1/people-view/overview").json()
    assert [e["name"] for e in body["entries"]] == ["Wonyoung"]
    assert [e["name"] for e in body["hidden"]] == ["Nayeon"]
    assert body["pins"] == []

    client.post("/v1/people-view/unhide", json={"keys": nayeon["keys"]})
    body = client.get("/v1/people-view/overview").json()
    assert {e["name"] for e in body["entries"]} == {"Nayeon", "Wonyoung"} and body["hidden"] == []


def test_merge_links_an_unnamed_person_from_another_library_into_the_named_one(client, tmp_path):
    _library(client, tmp_path / "a", "Nayeon")
    _library(client, tmp_path / "b", None)
    entries = client.get("/v1/people-view/overview").json()["entries"]
    target = next(e for e in entries if e["name"] == "Nayeon")
    source = next(e for e in entries if e["name"] is None)

    res = client.post("/v1/people-view/merge", json={"source_keys": source["keys"], "target_keys": target["keys"]})
    assert res.status_code == 200
    merged = client.get("/v1/people-view/overview").json()["entries"]
    assert len(merged) == 1 and merged[0]["name"] == "Nayeon" and len(merged[0]["members"]) == 2

    assert client.post("/v1/people-view/merge", json={"source_keys": target["keys"], "target_keys": target["keys"]}).status_code == 422


def _seed_two_faces(library_root: Path, bad_first: bool) -> None:
    """One person whose largest face lives in an undecodable file and whose smaller
    face is in a real image (or, with bad_first=False, both files undecodable)."""
    import cv2

    ok, buf = cv2.imencode(".jpg", np.full((64, 64, 3), 200, dtype=np.uint8))
    (library_root / "good.jpg").write_bytes(bytes(buf) if bad_first else b"not an image")
    (library_root / "bad.jpg").write_bytes(b"not an image")
    conn = open_library_db(library_data_dir(library_root).parent)
    ids = [upsert_file(conn, n, "photo", 100, 0.0, f"h_{n}", True) for n in ("bad.jpg", "good.jpg")]
    conn.commit()
    boxes = [(0, 0, 60, 60), (0, 0, 30, 30)]
    ff = [
        FileFaces(
            file_id=fid,
            content_hash=f"h{i}",
            decoded_ok=True,
            faces=[CachedFace(frame_no=0, bbox=box, embedding=np.array([1.0, 0.0, 0.0], dtype=np.float32))],
        )
        for i, (fid, box) in enumerate(zip(ids, boxes))
    ]
    persist_face_scan(
        conn, scan_id="s1", provider_id=PROVIDER, file_faces=ff, labels=np.array([0, 0], dtype=int),
        owners=[0, 1], started_at=time.time() - 1, finished_at=time.time(),
        params={"provider_id": PROVIDER}, summary={"files": 2, "faces": 2, "people": 1},
    )
    conn.close()


def _register(client, path: Path) -> str:
    res = client.post("/v1/libraries", json={"path": str(path)})
    assert res.status_code == 201
    return res.json()["id"]


def test_card_thumbnail_skips_an_undecodable_face_and_uses_the_next(client, tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    _seed_two_faces(root, bad_first=True)
    lib = _register(client, root)
    pid = client.get("/v1/people-view/overview").json()["entries"][0]["members"][0]["local_person_id"]

    res = client.get(f"/v1/people-view/persons/{lib}/{pid}/thumbnail")
    assert res.status_code == 200 and res.headers["content-type"] == "image/jpeg"
    assert len(client.get("/v1/people-view/overview").json()["entries"]) == 1


def test_person_with_no_croppable_face_is_dropped_from_the_view(client, tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    _seed_two_faces(root, bad_first=False)
    lib = _register(client, root)
    pid = client.get("/v1/people-view/overview").json()["entries"][0]["members"][0]["local_person_id"]

    assert client.get(f"/v1/people-view/persons/{lib}/{pid}/thumbnail").status_code == 410
    assert client.get("/v1/people-view/overview").json()["entries"] == []
    assert client.get("/v1/people-view/overview").json()["hidden"] == []


def test_missing_source_file_is_not_evidence_the_person_is_fake(client, tmp_path):
    lib = _library(client, tmp_path / "lib", "Nayeon")  # a.jpg was never written to disk
    pid = client.get("/v1/people-view/overview").json()["entries"][0]["members"][0]["local_person_id"]

    assert client.get(f"/v1/people-view/persons/{lib}/{pid}/thumbnail").status_code == 404
    assert len(client.get("/v1/people-view/overview").json()["entries"]) == 1


def test_verify_sweep_reports_and_drops_persons_with_no_croppable_face(client, tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    _seed_two_faces(root, bad_first=False)
    lib = _register(client, root)
    key = client.get("/v1/people-view/overview").json()["entries"][0]["keys"][0]

    res = client.post("/v1/people-view/verify", json={"keys": [key, "p:nope:1", "garbage"]})
    assert res.status_code == 200 and res.json() == {"unusable": [key]}
    assert client.get("/v1/people-view/overview").json()["entries"] == []
