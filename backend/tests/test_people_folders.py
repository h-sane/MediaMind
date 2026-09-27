"""People folders: counts, primary folder by name, moving, group pictures, auto-filing."""

import time
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from mediamind.api.app import create_app
from mediamind.core.faces import teach
from mediamind.core.hashing import hash_file
from mediamind.store import rejected_matches
from mediamind.store.db import open_library_db

P = "fake"


def _file(conn, root, rel, kind="image"):
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_bytes(rel.encode())
    return conn.execute("INSERT INTO files (path, kind, size, mtime, content_hash, decoded_ok) VALUES (?, ?, 1, 0, ?, 1)",
                        (rel, kind, "h" + rel)).lastrowid


def _face(conn, fid, x=0):
    return conn.execute("INSERT INTO faces (file_id, provider_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, embedding)"
                        " VALUES (?, ?, ?, 0, ?, 100, ?)", (fid, P, x, x + 100, np.ones(4, np.float32).tobytes())).lastrowid


def test_people_folders_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    aespa, downloads = tmp_path / "AESPA", tmp_path / "Downloads"
    aespa.mkdir(); downloads.mkdir()
    with TestClient(create_app()) as client:
        a_id = client.post("/v1/libraries", json={"path": str(aespa)}).json()["id"]
        d_id = client.post("/v1/libraries", json={"path": str(downloads)}).json()["id"]
        conn = open_library_db(aespa)
        solo = [_file(conn, aespa, f"{i}.jpg") for i in range(3)]
        group = _file(conn, aespa, "group.jpg")
        stranger = _file(conn, aespa, "stranger.jpg")
        _file(conn, aespa, "landscape.jpg")
        karina = teach.add_examples(conn, [_face(conn, f) for f in solo], name="Karina")
        teach.add_examples(conn, [_face(conn, group)], name="Karina")
        winter = teach.add_examples(conn, [_face(conn, group, 200)], name="Winter")
        _face(conn, stranger)
        conn.commit()
        conn.close()

        assert client.get(f"/v1/libraries/{a_id}/teach/stats").json() == {"total": 6, "sorted": 4, "unsorted": 1, "no_faces": 1}
        assert [f["path"] for f in client.get(f"/v1/libraries/{a_id}/teach/no-faces").json()] == ["landscape.jpg"]

        (aespa / "KARINA").mkdir(); (aespa / "WINTER").mkdir()
        for pid, folder in ((karina, "KARINA"), (winter, "WINTER")):
            res = client.put(f"/v1/libraries/{a_id}/teach/people/{pid}/primary-location", json={"path": str(aespa / folder)})
            assert res.status_code == 200, res.text
        assert client.put(f"/v1/libraries/{a_id}/teach/people/{karina}/primary-location",
                          json={"path": str(tmp_path / "nope")}).status_code == 422

        plan = client.get(f"/v1/libraries/{a_id}/teach/people/{karina}/move-plan").json()
        assert (plan["moves"], plan["groups_waiting"]) == (3, 1)
        job = client.post(f"/v1/libraries/{a_id}/teach/people/{karina}/move", json={"expected_plan_hash": plan["plan_hash"]}).json()
        for _ in range(100):
            snap = client.get(f"/v1/libraries/{a_id}/scans/{job['id']}").json()
            if snap["state"] in ("succeeded", "failed"):
                break
            time.sleep(0.05)
        assert snap["state"] == "succeeded", snap
        assert sorted(p.name for p in (aespa / "KARINA").iterdir()) == ["0.jpg", "1.jpg", "2.jpg"]
        conn = open_library_db(aespa)  # the index follows the files, faces and names included
        assert conn.execute("SELECT COUNT(*) FROM files f JOIN faces x ON x.file_id = f.id WHERE f.path LIKE 'KARINA/%'").fetchone()[0] == 3
        conn.close()

        groups = client.get(f"/v1/libraries/{a_id}/teach/groups").json()
        assert [(g["people"], g["new_folder_parent"]) for g in groups] == [(["Karina", "Winter"], str(aespa))]
        res = client.post(f"/v1/libraries/{a_id}/teach/groups/place",
                          json={"file_id": group, "choice": "new", "folder_name": "OT2", "remember": True}).json()
        assert res["moved"] == 1 and (aespa / "OT2" / "group.jpg").exists()
        assert client.get(f"/v1/libraries/{a_id}/teach/groups").json() == []

        # A watched folder, opted in: a new picture of Karina is filed into her folder.
        assert client.put(f"/v1/libraries/{d_id}/auto-file", json={"enabled": True}).json() == {"enabled": True}
        from mediamind.core import placement
        from mediamind.store import global_people as gp_store
        conn = open_library_db(downloads)
        new = _file(conn, downloads, "new.jpg")
        teach.add_examples(conn, [_face(conn, new)], name="karina ")
        gp = gp_store.open_global_db()
        moves = placement.auto_file_moves(gp, conn, d_id, downloads, [str(downloads / "new.jpg")])
        assert [(m.file.file_id, m.dest) for m in moves] == [(new, str((aespa / "KARINA").resolve()))]
        placement.execute_moves(gp, client.app.state.registry, moves, label="auto-file")
        gp.close()
        assert (aespa / "KARINA" / "new.jpg").exists() and not (downloads / "new.jpg").exists()
        assert conn.execute("SELECT COUNT(*) FROM files WHERE id = ?", (new,)).fetchone()[0] == 0  # left its library
        conn.close()


def _wait(client, lib, job_id):
    for _ in range(200):
        snap = client.get(f"/v1/libraries/{lib}/scans/{job_id}").json()
        if snap["state"] in ("succeeded", "failed", "cancelled"):
            return snap
        time.sleep(0.05)
    raise AssertionError(snap)


def test_move_skips_copies_answered_groups_and_ignored_faces(tmp_path, monkeypatch):
    """Hussain, 2026-09-27: a file already copied into Karina's folder isn't copied again; a group
    picture answered once isn't asked again for Winter; Winter ignored in a video doesn't make it
    a group picture."""
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    aespa = tmp_path / "AESPA"
    (aespa / "KARINA").mkdir(parents=True)
    (aespa / "WINTER").mkdir()
    with TestClient(create_app()) as client:
        a_id = client.post("/v1/libraries", json={"path": str(aespa)}).json()["id"]
        conn = open_library_db(aespa)
        copied = _file(conn, aespa, "copied.jpg")
        (aespa / "KARINA" / "copied (old).jpg").write_bytes(b"copied.jpg")          # the same bytes, already there
        conn.execute("UPDATE files SET size = ?, content_hash = ? WHERE id = ?",
                     (len(b"copied.jpg"), hash_file(aespa / "copied.jpg"), copied))
        solo = _file(conn, aespa, "solo.jpg")
        video = _file(conn, aespa, "video.mp4", kind="video")
        group = _file(conn, aespa, "group.jpg")
        karina = teach.add_examples(conn, [_face(conn, f) for f in (copied, solo, video, group)], name="Karina")
        winter_face = _face(conn, video, 200)
        winter = teach.add_examples(conn, [_face(conn, group, 200)], name="Winter")
        conn.execute("UPDATE faces SET person_id = ? WHERE id = ?", (winter, winter_face))
        rejected_matches.record(conn, "hvideo.mp4", P, (200, 0, 300, 100), winter)  # "Ignore" in review
        conn.commit()
        conn.close()
        for pid, folder in ((karina, "KARINA"), (winter, "WINTER")):
            client.put(f"/v1/libraries/{a_id}/teach/people/{pid}/primary-location", json={"path": str(aespa / folder)})

        job = client.post(f"/v1/libraries/{a_id}/teach/people/{karina}/move-plan").json()
        plan = _wait(client, a_id, job["id"])
        assert plan["state"] == "succeeded" and plan["phase"] == "comparing", plan
        p = plan["result"]
        assert (p["moves"], p["already_there"], p["groups_waiting"]) == (2, 1, 1)   # solo + video; group waits
        assert p == client.get(f"/v1/libraries/{a_id}/teach/people/{karina}/move-plan").json()

        # Folders already there (an OT4 made earlier) are offered, not only a new one.
        (aespa / "OT4").mkdir()
        (aespa / ".mediamind").mkdir(exist_ok=True)
        q = client.get(f"/v1/libraries/{a_id}/teach/groups").json()[0]
        names = [Path(f).name for f in q["existing_folders"]]
        assert "OT4" in names and "KARINA" in names and ".mediamind" not in names, names
        assert client.post(f"/v1/libraries/{a_id}/teach/groups/place", json={
            "file_id": group, "choice": "existing", "folder_path": str(aespa / "nope"), "remember": False}).status_code == 422
        res = client.post(f"/v1/libraries/{a_id}/teach/groups/place", json={
            "file_id": group, "choice": "existing", "folder_path": str(aespa / "OT4"), "remember": False})
        assert res.status_code == 200, res.text
        assert res.json()["moved"] == 1 and (aespa / "OT4" / "group.jpg").exists()
        assert client.get(f"/v1/libraries/{a_id}/teach/people/{winter}/move-plan").json()["groups_waiting"] == 0
        assert client.get(f"/v1/libraries/{a_id}/teach/groups").json() == []

        # Not scanned here: the sort job refuses at once, like the blocking route.
        assert client.post(f"/v1/libraries/{a_id}/teach/apply-job").status_code == 409
        conn = open_library_db(aespa)
        conn.execute("INSERT INTO scans (id, type, state, finished_at) VALUES ('s', 'faces', 'succeeded', 1)")
        conn.commit()
        conn.close()
        sort = _wait(client, a_id, client.post(f"/v1/libraries/{a_id}/teach/apply-job").json()["id"])
        assert sort["state"] == "succeeded" and "people" in sort["result"], sort


def test_cancelled_move_puts_everything_back(tmp_path, monkeypatch):
    """Hussain, 2026-09-27: cancel must undo what was done, safely. A move cancelled after two
    of four files puts both back, removes the folder it created, and leaves the index as it was."""
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    from mediamind.core import placement
    from mediamind.core.libraries import LibraryRegistry
    from mediamind.store import global_people as gp_store

    lib = tmp_path / "AESPA"
    lib.mkdir()
    registry = LibraryRegistry()
    lib_id = registry.add(lib).id
    conn = open_library_db(lib)
    ids = [_file(conn, lib, f"{i}.jpg") for i in range(4)]
    conn.commit()
    before = sorted(tuple(r) for r in conn.execute("SELECT id, path FROM files"))
    conn.close()

    dest = lib / "NEW" / "KARINA"
    moves = [placement.Placement(placement.NamedFile(lib_id, lib, fid, f"{i}.jpg", {"karina": "Karina"}), str(dest))
             for i, fid in enumerate(ids)]
    progress = []
    gp = gp_store.open_global_db()
    result = placement.execute_moves(gp, registry, moves, label="test", on_progress=lambda d, t: progress.append(d),
                                     should_cancel=lambda: len(progress) >= 2)
    gp.close()

    assert result["cancelled"] and result["rolled_back"] == 2 and result["moved"] == 0, result
    assert sorted(p.name for p in lib.glob("*.jpg")) == ["0.jpg", "1.jpg", "2.jpg", "3.jpg"]
    assert all((lib / f"{i}.jpg").read_bytes() == f"{i}.jpg".encode() for i in range(4))
    assert not (lib / "NEW").exists()                                   # the folders it made are gone
    conn = open_library_db(lib)
    assert sorted(tuple(r) for r in conn.execute("SELECT id, path FROM files")) == before
    conn.close()


def test_suggestions_only_ask_about_what_the_watcher_picked_up(tmp_path, monkeypatch):
    """Hussain, 2026-09-27: Suggestions is for what watched folders just picked up; a scan he
    ran himself is answered in Who's who, never mixed into Suggestions."""
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    lib = tmp_path / "BABY M"
    lib.mkdir()
    with TestClient(create_app()) as client:
        lib_id = client.post("/v1/libraries", json={"path": str(lib)}).json()["id"]
        conn = open_library_db(lib)
        scanned, arrived = _file(conn, lib, "scanned.jpg"), _file(conn, lib, "new/arrived.jpg")
        karina = teach.add_examples(conn, [_face(conn, _file(conn, lib, "example.jpg"))], name="Karina")
        for fid in (scanned, arrived):
            conn.execute("INSERT INTO pending_matches (face_id, person_id, confidence) VALUES (?, ?, 0.7)",
                         (_face(conn, fid, 300), karina))
        conn.execute("INSERT INTO watch_arrivals (path, arrived_at) VALUES ('new/arrived.jpg', ?)", (time.time(),))
        conn.execute("INSERT INTO watch_arrivals (path, arrived_at) VALUES ('scanned.jpg', 0)")  # long ago
        conn.commit()
        conn.close()

        everything = client.get(f"/v1/libraries/{lib_id}/pending").json()
        just_arrived = client.get(f"/v1/libraries/{lib_id}/pending?arrived=true").json()
        assert sorted(p["path"] for p in everything) == ["new/arrived.jpg", "scanned.jpg"]
        assert [p["path"] for p in just_arrived] == ["new/arrived.jpg"]
