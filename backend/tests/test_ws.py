"""Tests for the WebSocket progress endpoint (B5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mediamind.api.app import create_app


@pytest.fixture
def token_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app(token="test-token")) as c:
        yield c


@pytest.fixture
def no_token_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app()) as c:
        yield c


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_ws_rejects_missing_token(token_client):
    with pytest.raises(Exception):
        with token_client.websocket_connect("/v1/progress"):
            pass


def test_ws_rejects_wrong_token(token_client):
    with pytest.raises(Exception):
        with token_client.websocket_connect("/v1/progress?token=wrong") as ws:
            ws.receive_text()


def test_ws_accepts_correct_token(token_client):
    # Should connect and send an empty snapshot (no active jobs).
    with token_client.websocket_connect("/v1/progress?token=test-token") as ws:
        # Connection accepted; no initial messages since no active jobs.
        pass  # clean disconnect


def test_ws_no_auth_configured_allows_any_connection(no_token_client):
    with no_token_client.websocket_connect("/v1/progress") as ws:
        pass  # clean disconnect
