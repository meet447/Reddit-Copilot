"""Project workspace store and API tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rcopilot.api import create_app
from rcopilot.config import write_example_config
from rcopilot.projects import seed_projects_from_config
from rcopilot.config import load_config
from rcopilot.store import DEFAULT_PROJECT_ID, Store


def _sample_post(store: Store, post_id: str = "p1", *, project_id: str = DEFAULT_PROJECT_ID) -> None:
    store.upsert_post(
        id=post_id,
        project_id=project_id,
        subreddit="python",
        title="Hello",
        selftext="body",
        url="https://example.com",
        permalink=f"https://reddit.com/r/python/comments/{post_id}",
        created_utc=1.0,
        top_comments=[],
    )


def test_seed_default_project_from_yaml_voice(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_example_config(config_path)
    text = config_path.read_text(encoding="utf-8")
    text = text.replace("db_path: rcopilot.db", f"db_path: {tmp_path / 'test.db'}")
    config_path.write_text(text, encoding="utf-8")

    config = load_config(config_path)
    config.voice.product = "Reddit Copilot local assistant"
    config.onboarding_complete = True
    store = Store(config.db_path)
    store.ensure_schema()
    seeded = seed_projects_from_config(store, config)
    assert seeded is not None
    assert seeded["briefing"] == "Reddit Copilot local assistant"
    assert seeded["purpose"] == "product"
    assert seeded["complete"] is True
    assert "python" in seeded["subreddits"]

    again = seed_projects_from_config(store, config)
    assert again is None


def test_same_reddit_id_in_two_projects(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.db")
    store.ensure_schema()
    other = store.create_project(
        purpose="personal",
        name="Personal",
        briefing="I am a designer",
        project_id="personal",
    )
    _sample_post(store, "shared", project_id=DEFAULT_PROJECT_ID)
    _sample_post(store, "shared", project_id=other["id"])

    a = store.get_post("shared", project_id=DEFAULT_PROJECT_ID)
    b = store.get_post("shared", project_id=other["id"])
    assert a is not None and b is not None
    store.update_post("shared", project_id=DEFAULT_PROJECT_ID, skipped=1)
    assert store.get_post("shared", project_id=DEFAULT_PROJECT_ID)["skipped"] is True
    assert store.get_post("shared", project_id=other["id"])["skipped"] is False

    store.create_draft("shared", "default", "one", project_id=DEFAULT_PROJECT_ID)
    store.create_draft("shared", "default", "two", project_id=other["id"])
    assert len(store.list_drafts(project_id=DEFAULT_PROJECT_ID)) == 1
    assert len(store.list_drafts(project_id=other["id"])) == 1


def test_list_posts_scoped_to_project(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.db")
    store.ensure_schema()
    other = store.create_project(
        purpose="custom",
        name="Custom",
        briefing="Collect recipes",
        project_id="custom",
    )
    _sample_post(store, "a", project_id=DEFAULT_PROJECT_ID)
    _sample_post(store, "b", project_id=other["id"])
    assert [p["id"] for p in store.list_posts(project_id=DEFAULT_PROJECT_ID)] == ["a"]
    assert [p["id"] for p in store.list_posts(project_id=other["id"])] == ["b"]


def test_projects_api_create_and_active(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_example_config(config_path)
    text = config_path.read_text(encoding="utf-8")
    text = text.replace("db_path: rcopilot.db", f"db_path: {tmp_path / 'test.db'}")
    config_path.write_text(text, encoding="utf-8")
    (tmp_path / ".env").write_text("LLM_API_KEY=test-key\n", encoding="utf-8")
    client = TestClient(create_app(config_path=str(config_path)))

    created = client.post("/api/projects", json={"purpose": "personal"})
    assert created.status_code == 200, created.text
    data = created.json()
    assert data["purpose"] == "personal"
    assert data["interview_messages"]
    assert data["interview_messages"][0]["role"] == "assistant"
    assert data["setup_step"] == 4
    assert client.get("/api/config").json()["setup_project"]["id"] == data["id"]

    listed = client.get("/api/projects")
    assert listed.status_code == 200
    listed_ids = [item["id"] for item in listed.json()["projects"]]
    assert data["id"] not in listed_ids

    second = client.post("/api/projects", json={"purpose": "custom"}).json()
    assert second["id"] != data["id"]
    listed = client.get("/api/projects").json()
    assert listed["active_project_id"] != second["id"]
    assert second["id"] not in [item["id"] for item in listed["projects"]]

    switched = client.put("/api/projects/active", json={"id": second["id"]})
    assert switched.status_code == 200
    assert switched.json()["active_project_id"] == second["id"]

def test_complete_project_extracts_briefing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.yaml"
    write_example_config(config_path)
    text = config_path.read_text(encoding="utf-8")
    text = text.replace("db_path: rcopilot.db", f"db_path: {tmp_path / 'test.db'}")
    config_path.write_text(text, encoding="utf-8")
    (tmp_path / ".env").write_text("LLM_API_KEY=test-key\n", encoding="utf-8")
    client = TestClient(create_app(config_path=str(config_path)))
    created = client.post("/api/projects", json={"purpose": "product"}).json()

    monkeypatch.setattr(
        "rcopilot.api.complete_workspace",
        lambda llm, *, purpose, messages, count=12: {
            "name": "Acme",
            "briefing": "Acme is a notes app.",
            "goals": ["helpful comments"],
            "keywords": ["notes app"],
            "tone": "direct",
            "persona": "founder",
            "avoid": "hype",
            "subreddits": ["productivity"],
        },
    )
    response = client.post(f"/api/projects/{created['id']}/complete")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["briefing"] == "Acme is a notes app."
    assert data["goals"] == ["helpful comments"]
    assert data["subreddits"] == ["productivity"]
    assert data["setup_step"] == 5

    config = client.get("/api/config").json()
    setup = config.get("setup_project") or {}
    assert setup.get("id") == created["id"]
    assert setup.get("setup_step") == 5
    assert setup.get("briefing") == "Acme is a notes app."

    finished = client.patch(
        f"/api/projects/{created['id']}", json={"complete": True}
    )
    assert finished.status_code == 200
    assert finished.json()["setup_step"] == 0
    assert client.get("/api/config").json().get("setup_project") is None


def test_posts_and_drafts_api_honor_active_project(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_example_config(config_path)
    text = config_path.read_text(encoding="utf-8")
    text = text.replace("db_path: rcopilot.db", f"db_path: {tmp_path / 'test.db'}")
    config_path.write_text(text, encoding="utf-8")
    (tmp_path / ".env").write_text("LLM_API_KEY=test-key\n", encoding="utf-8")
    client = TestClient(create_app(config_path=str(config_path)))

    first = client.post("/api/projects", json={"purpose": "product"}).json()
    second = client.post("/api/projects", json={"purpose": "personal"}).json()
    config = load_config(config_path)
    store = Store(config.db_path)
    _sample_post(store, "alpha", project_id=first["id"])
    _sample_post(store, "beta", project_id=second["id"])
    store.create_draft("alpha", "default", "one", project_id=first["id"])
    store.create_draft("beta", "default", "two", project_id=second["id"])

    switched = client.put("/api/projects/active", json={"id": first["id"]})
    assert switched.status_code == 200
    posts = client.get("/api/posts").json()["posts"]
    assert [item["id"] for item in posts] == ["alpha"]
    drafts = client.get("/api/drafts?status=all").json()["drafts"]
    assert [item["post_id"] for item in drafts] == ["alpha"]

    client.put("/api/projects/active", json={"id": second["id"]})
    posts = client.get("/api/posts").json()["posts"]
    assert [item["id"] for item in posts] == ["beta"]
    drafts = client.get("/api/drafts?status=all").json()["drafts"]
    assert [item["post_id"] for item in drafts] == ["beta"]

