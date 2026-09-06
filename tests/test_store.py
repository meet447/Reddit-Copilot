"""Basic store tests for Reddit Copilot."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rcopilot.store import Store


def _sample_post(store: Store, post_id: str = "p1", **overrides) -> None:
    store.upsert_post(
        id=post_id,
        subreddit="python",
        title=overrides.get("title", "Hello"),
        selftext=overrides.get("selftext", "body"),
        url="https://example.com",
        permalink=f"https://reddit.com/r/python/comments/{post_id}",
        created_utc=overrides.get("created_utc", 1.0),
        top_comments=overrides.get("top_comments", [{"body": "nice", "score": 5}]),
    )


def test_upsert_dedup_and_draft_flow(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.db")
    store.ensure_schema()

    _sample_post(store)
    _sample_post(store, title="Hello updated")

    assert store.get_post("p1")["title"] == "Hello updated"
    assert len(store.list_posts_without_draft()) == 1

    draft_id = store.create_draft("p1", "default", "Looks good!")
    assert store.list_posts_without_draft() == []

    store.update_draft(draft_id, status="approved")
    draft = store.get_draft(draft_id)
    assert draft is not None
    assert draft["status"] == "approved"
    assert draft["title"] == "Hello updated"


def test_post_scoring_columns_and_skip(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.db")
    store.ensure_schema()
    _sample_post(store)

    store.update_post(
        "p1",
        relevance_score=0.75,
        score_reasons=json.dumps(["question signal"]),
        keywords_matched=json.dumps(["python"]),
        skipped=1,
    )
    post = store.get_post("p1")
    assert post is not None
    assert post["relevance_score"] == 0.75
    assert post["score_reasons"] == ["question signal"]
    assert post["keywords_matched"] == ["python"]
    assert post["skipped"] is True

    skipped = store.list_posts(skipped=True)
    assert len(skipped) == 1
    not_skipped = store.list_posts(skipped=False)
    assert not_skipped == []


def test_list_posts_ordering_and_filters(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.db")
    store.ensure_schema()
    _sample_post(store, post_id="low", created_utc=1.0)
    _sample_post(store, post_id="high", created_utc=2.0)

    store.update_post("low", relevance_score=0.2)
    store.update_post("high", relevance_score=0.9)

    ordered = store.list_posts()
    assert [p["id"] for p in ordered] == ["high", "low"]

    eligible = store.list_posts(undrafted=True, skipped=False, min_score=0.5)
    assert [p["id"] for p in eligible] == ["high"]


def test_scheduled_draft_status(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.db")
    store.ensure_schema()
    _sample_post(store)
    draft_id = store.create_draft("p1", "default", "Scheduled reply")

    run_at = datetime.now(timezone.utc) + timedelta(hours=1)
    run_at_iso = run_at.replace(microsecond=0).isoformat()
    store.update_draft(draft_id, status="scheduled", run_at=run_at_iso)

    scheduled = store.list_scheduled()
    assert len(scheduled) == 1
    assert scheduled[0]["run_at"] == run_at_iso

    now_iso = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    assert store.list_scheduled_due(now_iso)[0]["id"] == draft_id

    store.cancel_schedule(draft_id)
    draft = store.get_draft(draft_id)
    assert draft is not None
    assert draft["status"] == "approved"
    assert draft["run_at"] is None


def test_audit_events(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.db")
    store.ensure_schema()
    _sample_post(store)
    draft_id = store.create_draft("p1", "default", "body")

    store.add_audit("approved", draft_id=draft_id, post_id="p1", detail={"by": "test"})
    events = store.list_audit(limit=10)
    assert len(events) == 1
    assert events[0]["action"] == "approved"
    assert events[0]["detail"] == {"by": "test"}


def test_count_drafts_by_status(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.db")
    store.ensure_schema()
    _sample_post(store, post_id="a")
    _sample_post(store, post_id="b")
    store.create_draft("a", "default", "one", status="pending")
    store.create_draft("b", "default", "two", status="approved")

    counts = store.count_drafts_by_status()
    assert counts["pending"] == 1
    assert counts["approved"] == 1
    assert counts["scheduled"] == 0
