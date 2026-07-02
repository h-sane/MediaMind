from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import mediamind.api.routes.libraries as libraries_module
from mediamind.api.app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Isolate the library registry into a temp app-data dir.
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.setattr(libraries_module, "_registry", None)
    return TestClient(create_app())


def test_health(client: TestClient):
    body = client.get("/v1/health").json()
    assert body["status"] == "ok"


def test_token_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.setattr(libraries_module, "_registry", None)
    c = TestClient(create_app(token="s3cret"))
    assert c.get("/v1/health").status_code == 401
    assert c.get("/v1/health", headers={"X-MediaMind-Token": "s3cret"}).status_code == 200


def test_library_lifecycle(client: TestClient, tmp_path: Path):
    folder = tmp_path / "photos"
    folder.mkdir()

    created = client.post("/v1/libraries", json={"path": str(folder)})
    assert created.status_code == 201
    lib = created.json()
    assert lib["name"] == "photos"
    assert (folder / ".mediamind").is_dir()

    listed = client.get("/v1/libraries").json()
    assert [l["id"] for l in listed] == [lib["id"]]

    # adding the same folder again is idempotent
    again = client.post("/v1/libraries", json={"path": str(folder)})
    assert again.json()["id"] == lib["id"]
    assert len(client.get("/v1/libraries").json()) == 1

    assert client.delete(f"/v1/libraries/{lib['id']}").status_code == 204
    assert client.get("/v1/libraries").json() == []
    assert folder.is_dir()  # unregistering never touches user files


def test_add_nonexistent_folder_rejected(client: TestClient, tmp_path: Path):
    res = client.post("/v1/libraries", json={"path": str(tmp_path / "nope")})
    assert res.status_code == 400


def test_remove_unknown_library_404(client: TestClient):
    assert client.delete("/v1/libraries/doesnotexist").status_code == 404
