"""Pipeline tests with mocked store (no network)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from rcopilot.pipeline import (
    approve_draft,
    cancel_schedule,
    poll_outcomes,
    reject_draft,
    schedule_draft,
)
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
        llm=LLMConfig(base_url="https://example.com/v1", model="test"),
        rate_limits=RateLimits(),
        voice=VoiceConfig(),
        discovery=DiscoveryConfig(min_score=0.25),
        worker=WorkerConfig(),
        prompt_template="test {title}",
    )


def _seed_draft(store: Store, body: str = "Nice post!", status: str = "pending") -> int:
    store.upsert_post(
        id="p1",
        subreddit="python",
        title="Title",
        selftext="body",
        url="https://example.com",
        permalink="https://reddit.com/r/python/comments/p1",
        created_utc=1.0,
        top_comments=[],
    )
    return store.create_draft("p1", "default", body, status=status)


def test_approve_reject_flow(tmp_path: Path) -> None:
    store = Store(tmp_path / "pipeline.db")
    store.ensure_schema()
    draft_id = _seed_draft(store)

    approve_draft(store, draft_id)
    draft = store.get_draft(draft_id)
    assert draft is not None
    assert draft["status"] == "approved"

    reject_draft(store, draft_id)
    draft = store.get_draft(draft_id)
    assert draft is not None
    assert draft["status"] == "rejected"


def test_schedule_and_unschedule(tmp_path: Path) -> None:
    store = Store(tmp_path / "pipeline.db")
    store.ensure_schema()
    draft_id = _seed_draft(store)
    approve_draft(store, draft_id)

    run_at = datetime.now(timezone.utc) + timedelta(hours=2)
    schedule_draft(store, draft_id, run_at)

    draft = store.get_draft(draft_id)
    assert draft is not None
    assert draft["status"] == "scheduled"
    assert draft["run_at"] is not None

    cancel_schedule(store, draft_id)
    draft = store.get_draft(draft_id)
    assert draft is not None
    assert draft["status"] == "pending"
    assert draft["run_at"] is None


def test_approve_requires_body(tmp_path: Path) -> None:
    store = Store(tmp_path / "pipeline.db")
    store.ensure_schema()
    draft_id = _seed_draft(store, body="")

    with pytest.raises(ValueError, match="empty body"):
        approve_draft(store, draft_id)


def test_poll_outcomes_updates_draft(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = Store(tmp_path / "pipeline.db")
    store.ensure_schema()
    draft_id = _seed_draft(store, status="posted")
    store.update_draft(
        draft_id,
        permalink="https://www.reddit.com/r/python/comments/p1/slug/cmt99/",
    )

    monkeypatch.setattr(
        "rcopilot.reddit_client.get_reddit",
        lambda account: object(),
    )
    monkeypatch.setattr(
        "rcopilot.reddit_client.fetch_comment_outcome",
        lambda reddit, comment_id: {
            "score": 7,
            "replies": 2,
            "removed": False,
            "permalink": "https://www.reddit.com/r/python/comments/p1/slug/cmt99/",
        },
    )

    assert poll_outcomes(_config(), store) == 1
    draft = store.get_draft(draft_id)
    assert draft is not None
    assert draft["comment_id"] == "cmt99"
    assert draft["outcome_score"] == 7
    assert draft["outcome_replies"] == 2
    assert draft["outcome_removed"] is False
    assert draft["outcomes_polled_at"]

    events = store.list_audit(limit=10)
    assert any(e["action"] == "outcome_updated" for e in events)


def test_poll_outcomes_skips_without_id_or_permalink(tmp_path: Path) -> None:
    store = Store(tmp_path / "pipeline.db")
    store.ensure_schema()
    draft_id = _seed_draft(store, status="posted")
    store.update_draft(draft_id, permalink=None, comment_id=None)

    assert poll_outcomes(_config(), store) == 0
    draft = store.get_draft(draft_id)
    assert draft is not None
    assert draft["outcomes_polled_at"] is None
