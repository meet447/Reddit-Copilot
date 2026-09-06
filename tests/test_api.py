"""FastAPI endpoint tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rcopilot.api import create_app
from rcopilot.config import write_example_config


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    config_path = tmp_path / "config.yaml"
    write_example_config(config_path)
    (tmp_path / ".env").write_text("LLM_API_KEY=test-key\n", encoding="utf-8")
    app = create_app(config_path=str(config_path))
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["version"] == "1.0.0"


def test_list_drafts_empty(client: TestClient) -> None:
    response = client.get("/api/drafts")
    assert response.status_code == 200
    assert response.json()["drafts"] == []


def test_approve_not_found(client: TestClient) -> None:
    response = client.post("/api/drafts/999/approve")
    assert response.status_code == 404
    assert "error" in response.json()


def test_oauth_start_requires_client_id(client: TestClient) -> None:
    response = client.post("/api/oauth/start", json={})
    assert response.status_code == 400
    assert "client ID" in response.json()["error"]


def test_oauth_start_returns_reddit_url(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_example_config(config_path)
    (tmp_path / ".env").write_text(
        "REDDIT_CLIENT_ID=test-client-id\nREDDIT_CLIENT_SECRET=test-secret\n",
        encoding="utf-8",
    )
    app = create_app(config_path=str(config_path))
    client = TestClient(app)
    response = client.post("/api/oauth/start", json={"next": "/onboarding"})
    assert response.status_code == 200
    data = response.json()
    assert "reddit.com" in data["authorize_url"]
    assert "state=" in data["authorize_url"]
    assert "duration=permanent" in data["authorize_url"]
    assert data["redirect_uri"].endswith("/api/oauth/callback")


def test_oauth_callback_rejects_bad_state(client: TestClient) -> None:
    response = client.get(
        "/api/oauth/callback",
        params={"code": "abc", "state": "not-a-real-state"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert "reddit=error" in location
    assert "onboarding" in location
