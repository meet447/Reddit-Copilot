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
    _queries_fingerprint,
    approve_draft,
    cancel_schedule,
    create_submission_draft,
    draft_pending,
    fetch_and_store,
    generate_draft_variants,
    iter_fetch_and_store,
    poll_outcomes,
    post_due_scheduled,
    reject_draft,
    run_once,
    schedule_draft,
    select_draft_variant,
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


def test_schedule_and_post_due_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path / "pipeline.db")
    store.ensure_schema()
    config = _config()
    draft_id = create_submission_draft(
        config,
        store,
        subreddit="python",
        title="Launch notes",
        body="We shipped a thing.",
    )

    run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    schedule_draft(store, draft_id, run_at)

    monkeypatch.setattr(
        "rcopilot.reddit_client.get_reddit",
        lambda account: object(),
    )
    monkeypatch.setattr(
        "rcopilot.reddit_client.post_submission",
        lambda reddit, subreddit, title, selftext: (
            "https://reddit.com/r/python/comments/abc123/launch_notes/",
            "abc123",
        ),
    )

    results = post_due_scheduled(config, store)
    assert len(results) == 1
    assert results[0]["ok"] is True
    assert results[0]["submission_id"] == "abc123"

    draft = store.get_draft(draft_id)
    assert draft is not None
    assert draft["status"] == "posted"
    assert draft["submission_id"] == "abc123"
    assert draft["permalink"].endswith("/launch_notes/")


def test_run_once_does_not_auto_draft(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = Store(tmp_path / "run_once.db")
    store.ensure_schema()
    drafted: list[int] = []
    monkeypatch.setattr("rcopilot.pipeline.fetch_and_store", lambda *args, **kwargs: 2)
    monkeypatch.setattr(
        "rcopilot.pipeline.draft_pending",
        lambda *args, **kwargs: drafted.append(1) or 3,
    )
    monkeypatch.setattr("rcopilot.pipeline.post_due_scheduled", lambda *args, **kwargs: [])
    monkeypatch.setattr("rcopilot.pipeline.poll_outcomes", lambda *args, **kwargs: 0)

    result = run_once(_config(), store)
    assert drafted == []
    assert result["drafted"] == 0
    assert result["fetched"] == 2


def test_draft_pending_only_fills_queued_empty_drafts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = Store(tmp_path / "pending.db")
    store.ensure_schema()
    store.upsert_post(
        id="discover-only",
        subreddit="python",
        title="Anyone using pytest?",
        selftext="Need a fixture tip.",
        url="https://example.com",
        permalink="https://reddit.com/r/python/comments/discover-only",
        created_utc=1.0,
        top_comments=[],
    )
    queued_id = _seed_draft(store, body="")
    config = _config()
    config.llm.api_key = "test-key"
    monkeypatch.setattr(
        "rcopilot.pipeline.generate_comment_variants",
        lambda *args, **kwargs: [
            {"id": "v1", "label": "Direct", "body": "I would start with a tiny fixture."},
            {"id": "v2", "label": "Lived", "body": "I hit this last year on Windows."},
        ],
    )

    created = draft_pending(config, store)
    assert created == 1
    assert store.get_post("discover-only") is not None
    assert store.list_posts_without_draft()
    queued = store.get_draft(queued_id)
    assert queued is not None
    assert queued["body"] == ""
    assert len(queued["variants"]) == 2


def test_generate_and_select_variants(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = Store(tmp_path / "variants.db")
    store.ensure_schema()
    draft_id = _seed_draft(store, body="")
    config = _config()
    config.llm.api_key = "test-key"
    monkeypatch.setattr(
        "rcopilot.pipeline.generate_comment_variants",
        lambda *args, **kwargs: [
            {"id": "v1", "label": "Direct", "body": "I would start with pytest."},
            {"id": "v2", "label": "Lived", "body": "I hit this last year on Windows."},
        ],
    )

    variants = generate_draft_variants(config, store, draft_id)
    draft = store.get_draft(draft_id)
    assert draft is not None
    assert draft["body"] == ""
    assert [item["id"] for item in variants] == ["v1", "v2"]
    assert draft["variants"][1]["label"] == "Lived"

    select_draft_variant(store, draft_id, "v2")
    draft = store.get_draft(draft_id)
    assert draft is not None
    assert draft["body"] == "I hit this last year on Windows."

    with pytest.raises(ValueError, match="Unknown variant"):
        select_draft_variant(store, draft_id, "nope")


def _discover_post(post_id: str, title: str) -> dict:
    return {
        "id": post_id,
        "subreddit": "python",
        "title": title,
        "selftext": "Looking for a fixture tip.",
        "url": f"https://example.com/{post_id}",
        "permalink": f"https://reddit.com/r/python/comments/{post_id}",
        "created_utc": 1.0,
        "top_comments": [],
        "num_comments": 0,
    }


def test_iter_fetch_and_store_yields_each_thread(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = Store(tmp_path / "fetch.db")
    store.ensure_schema()
    config = _config()
    listing = _discover_post("list1", "How do I learn Python?")
    search = _discover_post("search1", "Looking for a pytest fixture pattern?")
    monkeypatch.setattr("rcopilot.pipeline.reddit_client.get_reddit", lambda account: object())
    monkeypatch.setattr(
        "rcopilot.pipeline.reddit_client.iter_listing_posts",
        lambda *args, **kwargs: iter([listing]),
    )
    monkeypatch.setattr(
        "rcopilot.pipeline.reddit_client.iter_search_posts",
        lambda *args, **kwargs: iter([search]),
    )
    monkeypatch.setattr("rcopilot.pipeline.persist_queries_to_project", lambda *args, **kwargs: None)

    events = list(iter_fetch_and_store(config, store))
    types = [event["type"] for event in events]
    assert types[0] == "started"
    assert types[-1] == "done"
    ids = [event["post"]["id"] for event in events if event["type"] == "post"]
    assert ids == ["list1", "search1"]
    assert events[-1]["fetched"] == 2
    assert events[-1]["shown"] == 2
    assert store.get_post("list1") is not None
    assert store.get_post("search1") is not None


def test_iter_fetch_and_store_searches_first_when_queries_cached(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = Store(tmp_path / "fetch-search.db")
    store.ensure_schema()
    config = _config()
    config.discovery.search_queries = ["fixture"]
    config.discovery.queries_fingerprint = _queries_fingerprint(config)
    listing = _discover_post("list1", "How do I learn Python?")
    search = _discover_post("search1", "Looking for a pytest fixture pattern?")
    monkeypatch.setattr("rcopilot.pipeline.reddit_client.get_reddit", lambda account: object())
    monkeypatch.setattr(
        "rcopilot.pipeline.reddit_client.iter_listing_posts",
        lambda *args, **kwargs: iter([listing]),
    )
    monkeypatch.setattr(
        "rcopilot.pipeline.reddit_client.iter_search_posts",
        lambda *args, **kwargs: iter([search]),
    )
    monkeypatch.setattr("rcopilot.pipeline.persist_queries_to_project", lambda *args, **kwargs: None)

    events = list(iter_fetch_and_store(config, store))
    ids = [event["post"]["id"] for event in events if event["type"] == "post"]
    assert ids == ["search1", "list1"]


def test_fetch_and_store_returns_new_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = Store(tmp_path / "fetch2.db")
    store.ensure_schema()
    config = _config()
    monkeypatch.setattr("rcopilot.pipeline.reddit_client.get_reddit", lambda account: object())
    monkeypatch.setattr(
        "rcopilot.pipeline.reddit_client.iter_listing_posts",
        lambda *args, **kwargs: iter([_discover_post("only", "How do I learn Python?")]),
    )
    monkeypatch.setattr(
        "rcopilot.pipeline.reddit_client.iter_search_posts",
        lambda *args, **kwargs: iter([]),
    )
    monkeypatch.setattr("rcopilot.pipeline.persist_queries_to_project", lambda *args, **kwargs: None)
    assert fetch_and_store(config, store) == 1
    assert fetch_and_store(config, store) == 0
