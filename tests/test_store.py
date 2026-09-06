"""Basic store tests for Reddit Copilot."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

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
        intent_labels=json.dumps(["question", "unanswered"]),
        skipped=1,
    )
    post = store.get_post("p1")
    assert post is not None
    assert post["relevance_score"] == 0.75
    assert post["score_reasons"] == ["question signal"]
    assert post["keywords_matched"] == ["python"]
    assert post["intent_labels"] == ["question", "unanswered"]
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
    assert draft["status"] == "pending"
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


def test_draft_outcome_columns_and_list_for_poll(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.db")
    store.ensure_schema()
    _sample_post(store, post_id="a")
    _sample_post(store, post_id="b")
    _sample_post(store, post_id="c")
    id_a = store.create_draft("a", "default", "one")
    id_b = store.create_draft("b", "default", "two")
    id_c = store.create_draft("c", "default", "three")

    store.update_draft(id_a, status="posted", comment_id="cmt_a", permalink="https://reddit.com/r/x/comments/a/slug/cmt_a")
    store.update_draft(
        id_b,
        status="posted",
        comment_id="cmt_b",
        outcome_score=3,
        outcome_replies=1,
        outcome_removed=0,
        outcomes_polled_at="2026-01-01T00:00:00+00:00",
    )
    store.update_draft(id_c, status="pending")

    store.update_draft(
        id_a,
        outcome_score=12,
        outcome_replies=2,
        outcome_removed=0,
        outcomes_polled_at="2026-01-02T00:00:00+00:00",
    )
    draft = store.get_draft(id_a)
    assert draft is not None
    assert draft["comment_id"] == "cmt_a"
    assert draft["outcome_score"] == 12
    assert draft["outcome_replies"] == 2
    assert draft["outcome_removed"] is False
    assert draft["outcomes_polled_at"] == "2026-01-02T00:00:00+00:00"

    # Never-polled posted draft should come first
    store.update_draft(id_a, outcomes_polled_at=None, outcome_score=None, outcome_replies=None)
    ordered = store.list_posted_for_outcomes(limit=10)
    assert [d["id"] for d in ordered] == [id_a, id_b]


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


def test_submission_draft_null_post_id(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.db")
    store.ensure_schema()

    draft_id = store.create_submission_draft(
        account_name="default",
        subreddit="python",
        title="Ship notes",
        body="Here is what we learned.",
    )
    draft = store.get_draft(draft_id)
    assert draft is not None
    assert draft["kind"] == "submission"
    assert draft["post_id"] is None
    assert draft["title"] == "Ship notes"
    assert draft["target_subreddit"] == "python"
    assert draft["subreddit"] == "python"

    # Multiple submissions with null post_id are allowed
    second = store.create_submission_draft(
        account_name="default",
        subreddit="python",
        title="Another",
        body="More text.",
    )
    assert second != draft_id


def test_comment_post_id_unique_still_enforced(tmp_path: Path) -> None:
    store = Store(tmp_path / "test.db")
    store.ensure_schema()
    _sample_post(store)
    store.create_draft("p1", "default", "first")

    with pytest.raises(sqlite3.IntegrityError):
        store.create_draft("p1", "default", "duplicate")
