"""People folders: counts, primary folder by name, moving, group pictures, auto-filing."""

import time

import numpy as np
from fastapi.testclient import TestClient

from mediamind.api.app import create_app
from mediamind.core.faces import teach
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
