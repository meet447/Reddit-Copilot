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


def test_product_blurb_matches_intent() -> None:
    post = _post(
        title="Looking for a local Reddit engagement assistant",
        selftext="I want something that drafts replies I can approve.",
    )
    score, reasons, matched = score_post(
        post,
        [],
        product="Reddit Copilot — a local-first Reddit engagement assistant.",
    )
    assert score >= 0.2
    assert any(term in matched for term in ("engagement assistant", "copilot", "assistant", "engagement"))
    assert any("product match" in reason for reason in reasons)
    assert any("looking-for-tool" in reason for reason in reasons)


def test_unrelated_thread_does_not_get_product_match() -> None:
    score, reasons, matched = score_post(
        _post(title="Best RAM for a homelab NAS", selftext="ECC vs non-ECC?"),
        ["looking for"],
        product="Reddit Copilot — a local-first Reddit engagement assistant.",
    )
    assert "product match" not in " ".join(reasons)
    assert "copilot" not in matched
    assert score <= 0.2
    assert any("weak intent" in reason for reason in reasons)
