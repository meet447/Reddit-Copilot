"""Scoring heuristic tests."""

from __future__ import annotations

from datetime import datetime, timezone

from rcopilot.scoring import classify_intent, score_post


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
    score, reasons, matched, labels = score_post(_post(), ["python", "learn"])
    assert score >= 0.3
    assert "python" in matched
    assert any("keyword" in reason for reason in reasons)
    assert "question" in labels


def test_question_scoring_without_keywords() -> None:
    score, reasons, matched, labels = score_post(_post(), [])
    assert score >= 0.2
    assert matched == []
    assert any("question" in reason for reason in reasons)
    assert "question" in labels
    assert "unanswered" in labels


def test_empty_keywords_still_scores_other_signals() -> None:
    score, _, matched, labels = score_post(
        _post(title="What is async?", top_comments=[]),
        [],
    )
    assert score > 0
    assert matched == []
    assert "question" in labels


def test_question_in_selftext() -> None:
    labels = classify_intent(
        _post(title="Need advice", selftext="How do I fix this deploy?", top_comments=[])
    )
    assert "question" in labels
    assert "unanswered" in labels


def test_looking_for_tool_label() -> None:
    labels = classify_intent(
        _post(
            title="Alternative to Buffer?",
            selftext="Looking for a scheduling tool for Reddit.",
            top_comments=[{"body": "try x"}],
        )
    )
    assert "looking-for-tool" in labels
    assert "unanswered" not in labels


def test_complaint_label() -> None:
    labels = classify_intent(
        _post(
            title="Fed up with manual replies",
            selftext="I'm frustrated with how slow this is.",
            top_comments=[{"body": "same"}],
        )
    )
    assert "complaint" in labels


def test_unanswered_question_boost() -> None:
    score, reasons, _, labels = score_post(
        _post(title="How do I automate Reddit replies?", top_comments=[]),
        [],
    )
    assert "question" in labels
    assert "unanswered" in labels
    assert any("unanswered question (+0.15)" in reason for reason in reasons)
    assert score >= 0.5  # question + unanswered + light discussion


def test_answered_question_skips_radar_boost() -> None:
    score, reasons, _, labels = score_post(
        _post(
            title="How do I automate Reddit replies?",
            top_comments=[{"body": "use praw"}, {"body": "or scripts"}],
        ),
        [],
    )
    assert "question" in labels
    assert "unanswered" not in labels
    assert not any("unanswered question" in reason for reason in reasons)


def test_num_comments_marks_answered_without_comment_bodies() -> None:
    labels = classify_intent(
        _post(title="How do I learn Python?", top_comments=[], num_comments=4)
    )
    assert "question" in labels
    assert "unanswered" not in labels


def test_num_comments_zero_is_unanswered() -> None:
    labels = classify_intent(
        _post(title="How do I learn Python?", top_comments=[{"body": "stale"}], num_comments=0)
    )
    assert "unanswered" in labels


def test_product_blurb_matches_intent() -> None:
    post = _post(
        title="Looking for a local Reddit engagement assistant",
        selftext="I want something that drafts replies I can approve.",
    )
    score, reasons, matched, labels = score_post(
        post,
        [],
        product="Reddit Copilot — a local-first Reddit engagement assistant.",
    )
    assert score >= 0.2
    assert any(term in matched for term in ("engagement assistant", "copilot", "assistant", "engagement"))
    assert any("context match" in reason for reason in reasons)
    assert any("looking-for-tool" in reason for reason in reasons)
    assert "looking-for-tool" in labels


def test_unrelated_thread_does_not_get_product_match() -> None:
    score, reasons, matched, labels = score_post(
        _post(title="Best RAM for a homelab NAS", selftext="ECC vs non-ECC?"),
        ["looking for"],
        product="Reddit Copilot — a local-first Reddit engagement assistant.",
    )
    assert "context match" not in " ".join(reasons)
    assert "copilot" not in matched
    assert score <= 0.2
    assert any("weak intent" in reason for reason in reasons)
    assert "question" in labels


def test_briefing_terms_skip_github_urls() -> None:
    from rcopilot.scoring import intent_terms_from_briefing

    terms = intent_terms_from_briefing(
        "Reddit Copilot (https://github.com/meet447/Reddit-Copilot) is a "
        "local-first Reddit engagement assistant."
    )
    blob = " ".join(terms)
    assert "github" not in blob
    assert "meet447" not in blob
    assert "https" not in blob
    assert any("engagement" in term for term in terms)


def test_long_keyword_matches_natural_reddit_wording() -> None:
    score, reasons, matched, _ = score_post(
        _post(
            title="My Saas audience is on reddit",
            selftext="Where should I post without getting banned?",
        ),
        ["promote product on reddit", "reddit marketing tool"],
        product="Reddit Copilot (https://github.com/meet447/Reddit-Copilot) is a local-first engagement assistant.",
        search_queries=["how to promote my saas on reddit without getting banned"],
    )
    assert score >= 0.25
    assert matched
    assert not any("weak intent" in reason for reason in reasons)


def test_search_hit_boosts_when_query_matches() -> None:
    post = _post(
        title="How do you find relevant threads to comment on?",
        selftext="",
        created_utc=1.0,
        top_comments=[{"body": "try this"}, {"body": "or that"}],
        num_comments=5,
    )
    keywords = ["promote product on reddit"]
    queries = ["how do you find relevant threads to comment on"]
    listed, _, _, _ = score_post(post, keywords, search_queries=queries, from_search=False)
    searched, reasons, _, _ = score_post(post, keywords, search_queries=queries, from_search=True)
    assert searched >= 0.25
    assert searched > listed
    assert any("search result" in reason for reason in reasons)


def test_search_noise_without_overlap_stays_capped() -> None:
    score, reasons, matched, _ = score_post(
        _post(title="Best RAM for a homelab NAS", selftext="ECC vs non-ECC?"),
        ["promote product on reddit"],
        search_queries=["how to promote my saas on reddit without getting banned"],
        from_search=True,
    )
    assert matched == []
    assert score <= 0.2
    assert any("weak intent" in reason for reason in reasons)
