"""Tests for LLM subreddit suggestion parsing."""

from __future__ import annotations

from rcopilot.llm import parse_subreddit_list


def test_parse_subreddit_list() -> None:
    names = parse_subreddit_list(
        '["startups", "r/SaaS", "/indiehackers", "startups", "??"]'
    )
    assert names == ["startups", "SaaS", "indiehackers"]


def test_parse_subreddit_list_fenced() -> None:
    raw = """```json
["python", "learnpython", "MachineLearning"]
```"""
    assert parse_subreddit_list(raw) == ["python", "learnpython", "MachineLearning"]
