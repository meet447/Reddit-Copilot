"""Tests for AI original-post generation helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from rcopilot.config import (
    Account,
    AppConfig,
    DiscoveryConfig,
    LLMConfig,
    RateLimits,
    VoiceConfig,
    WorkerConfig,
)
from rcopilot.llm import parse_submission_payload
from rcopilot.pipeline import generate_submission_ideas, iter_generate_submission_ideas
from rcopilot.store import Store


def _config() -> AppConfig:
    return AppConfig(
        subreddits=["python"],
        listing="hot",
        fetch_limit=25,
        db_path="unused.db",
        accounts=[
            Account(
                name="default",
                user_agent="test/1.0",
                client_id="cid",
                client_secret="secret",
                refresh_token="token",
            )
        ],
        llm=LLMConfig(base_url="https://example.com/v1", model="test", api_key="test-key"),
        rate_limits=RateLimits(),
        voice=VoiceConfig(),
        discovery=DiscoveryConfig(min_score=0.25),
        worker=WorkerConfig(),
        prompt_template="test {title}",
    )


def test_parse_submission_payload() -> None:
    title, body = parse_submission_payload(
        '{"title": "Anyone else struggle with X?", "body": "I tried Y and it helped a bit."}'
    )
    assert "struggle" in title.lower()
    assert "tried" in body.lower()


def test_parse_submission_payload_fenced() -> None:
    raw = """```json
{"title": "Lesson from shipping", "body": "We shipped late. Here is what I would do again."}
```"""
    title, body = parse_submission_payload(raw)
    assert title.startswith("Lesson")
    assert "shipped" in body.lower()


def test_generate_submission_ideas_mocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path / "gen.db")
    store.ensure_schema()
    config = _config()
    config.subreddits = ["python", "startups"]

    calls: list[str] = []

    def fake_generate(llm, *, subreddit, **kwargs):
        calls.append(subreddit)
        return (f"Title for {subreddit}", f"Body for {subreddit}")

    monkeypatch.setattr("rcopilot.pipeline.generate_submission", fake_generate)

    ids = generate_submission_ideas(config, store, count=3)
    assert len(ids) == 3
    assert calls == ["python", "startups", "python"]

    draft = store.get_draft(ids[0])
    assert draft is not None
    assert draft["kind"] == "submission"
    assert draft["target_subreddit"] == "python"
    assert draft["title"] == "Title for python"


def test_iter_generate_submission_ideas_yields_each_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path / "gen-iter.db")
    store.ensure_schema()
    config = _config()
    config.subreddits = ["python", "startups"]

    monkeypatch.setattr(
        "rcopilot.pipeline.generate_submission",
        lambda llm, *, subreddit, **kwargs: (f"Title for {subreddit}", f"Body for {subreddit}"),
    )

    events = list(iter_generate_submission_ideas(config, store, count=2))
    types = [event["type"] for event in events]
    assert types == ["started", "draft", "draft", "done"]
    drafts = [event["draft"] for event in events if event["type"] == "draft"]
    assert [row["target_subreddit"] for row in drafts] == ["python", "startups"]
    assert events[-1]["created"] == 2
