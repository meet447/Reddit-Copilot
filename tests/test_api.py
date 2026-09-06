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
    # Keep the DB inside tmp_path — example config uses a relative rcopilot.db.
    text = config_path.read_text(encoding="utf-8")
    text = text.replace("db_path: rcopilot.db", f"db_path: {tmp_path / 'test.db'}")
    config_path.write_text(text, encoding="utf-8")
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


def test_onboarding_progress_persists(client: TestClient) -> None:
    response = client.put(
        "/api/config",
        json={
            "onboarding_step": 2,
            "voice": {
                "product": "Reddit Copilot",
                "tone": "Helpful and direct",
                "persona": "Founder in the comments",
            },
            "subreddits": ["startups", "SaaS"],
            "discovery": {"keywords": ["looking for", "recommend"]},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["onboarding_step"] == 2
    assert data["voice"]["product"] == "Reddit Copilot"
    assert data["subreddits"] == ["startups", "SaaS"]
    assert data["discovery"]["keywords"] == ["looking for", "recommend"]

    reload = client.get("/api/config")
    assert reload.status_code == 200
    saved = reload.json()
    assert saved["onboarding_step"] == 2
    assert saved["voice"]["tone"] == "Helpful and direct"


def test_onboarding_step_clamps(client: TestClient) -> None:
    response = client.put("/api/config", json={"onboarding_step": 99})
    assert response.status_code == 200
    assert response.json()["onboarding_step"] == 4


def test_create_submission(client: TestClient) -> None:
    response = client.post(
        "/api/submissions",
        json={
            "subreddit": "python",
            "title": "Hello self-post",
            "body": "This is the body.",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["kind"] == "submission"
    assert data["title"] == "Hello self-post"
    assert data["target_subreddit"] == "python"
    assert data["subreddit"] == "python"
    assert data["body"] == "This is the body."
    assert data["post_id"] is None
    assert data["status"] == "pending"


def test_best_times_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from rcopilot.best_times import clear_hour_cache

    clear_hour_cache()
    monkeypatch.setattr(
        "rcopilot.reddit_client.get_reddit",
        lambda account: object(),
    )
    monkeypatch.setattr(
        "rcopilot.reddit_client.sample_subreddit_post_hours",
        lambda reddit, subreddit, limit=100: [18] * 10 + [12] * 3,
    )

    response = client.get(
        "/api/best-times",
        params={"subreddit": "python", "tz_offset_minutes": 0, "count": 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["subreddit"] == "python"
    assert data["sample_size"] == 13
    assert len(data["suggestions"]) == 2
    assert "run_at" in data["suggestions"][0]
    assert "label" in data["suggestions"][0]


def test_generate_submissions_api(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "rcopilot.pipeline.generate_submission",
        lambda llm, *, subreddit, **kwargs: (
            f"Idea for {subreddit}",
            f"Body about {subreddit}",
        ),
    )
    # Ensure API config has an llm key and subreddits via env already from fixture
    response = client.post("/api/submissions/generate", json={"count": 2})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["created"] == 2
    assert len(data["drafts"]) == 2
    assert data["drafts"][0]["kind"] == "submission"
    assert data["drafts"][0]["title"].startswith("Idea for")
