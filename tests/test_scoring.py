"""Scoring heuristic tests."""

from __future__ import annotations

from datetime import datetime, timezone

from rcopilot.scoring import score_post


def _post(**overrides):
    base = {
        "title": "How do I learn Python?",
        "selftext": "Looking for resources",
        "created_utc": datetime.now(timezone.utc).timestamp(),
        "top_comments": [],
    }
    base.update(overrides)
    return base


def test_keyword_scoring() -> None:
    score, reasons, matched = score_post(_post(), ["python", "learn"])
    assert score >= 0.3
    assert "python" in matched
    assert any("keyword" in reason for reason in reasons)


def test_question_scoring_without_keywords() -> None:
    score, reasons, matched = score_post(_post(), [])
    assert score >= 0.2
    assert matched == []
    assert any("question" in reason for reason in reasons)


def test_empty_keywords_still_scores_other_signals() -> None:
    score, _, matched = score_post(
        _post(title="What is async?", top_comments=[]),
        [],
    )
    assert score > 0
    assert matched == []
