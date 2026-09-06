"""Reddit client helper unit tests (no network)."""

from __future__ import annotations

from rcopilot.reddit_client import comment_id_from_permalink


def test_comment_id_from_permalink_standard() -> None:
    url = "https://www.reddit.com/r/python/comments/abc123/how_to_learn/def456/"
    assert comment_id_from_permalink(url) == "def456"


def test_comment_id_from_permalink_query_and_no_trailing_slash() -> None:
    url = "https://reddit.com/r/python/comments/abc123/slug/xyz789?utm=1"
    assert comment_id_from_permalink(url) == "xyz789"


def test_comment_id_from_permalink_thread_only() -> None:
    url = "https://www.reddit.com/r/python/comments/abc123/how_to_learn/"
    assert comment_id_from_permalink(url) is None


def test_comment_id_from_permalink_empty() -> None:
    assert comment_id_from_permalink(None) is None
    assert comment_id_from_permalink("") is None
