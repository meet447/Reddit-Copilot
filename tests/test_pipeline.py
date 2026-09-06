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
from rcopilot.pipeline import approve_draft, cancel_schedule, reject_draft, schedule_draft
from rcopilot.store import Store


def _config() -> AppConfig:
    return AppConfig(
        subreddits=["python"],
        listing="hot",
        fetch_limit=25,
        db_path="unused.db",
        accounts=[Account(name="default", user_agent="test/1.0")],
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
