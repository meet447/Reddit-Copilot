"""Interview briefing helpers (no live LLM)."""

from __future__ import annotations

from rcopilot.interview import (
    EXTRACT_PROMPT,
    READY_MARKER,
    _parse_briefing_json,
    opening_message,
    split_ready_marker,
    visible_interview_stream,
)
from rcopilot.llm import build_search_query_prompt
from rcopilot.research import extract_urls


def test_opening_prompts_differ_by_purpose() -> None:
    product = opening_message("product")["content"].lower()
    personal = opening_message("personal")["content"].lower()
    custom = opening_message("custom")["content"].lower()
    assert "product" in product
    assert "yourself" in personal
    assert "aim" in custom


def test_extract_urls_skips_reddit() -> None:
    text = "See https://example.com/docs and https://www.reddit.com/r/python plus https://redd.it/abc"
    urls = extract_urls(text)
    assert urls == ["https://example.com/docs"]


def test_parse_briefing_json() -> None:
    raw = """```json
{"name": "Copilot", "briefing": "A local assistant", "goals": ["helpful comments"], "keywords": ["reddit"], "tone": "direct", "persona": "founder", "avoid": "hype"}
```"""
    data = _parse_briefing_json(raw)
    assert data["name"] == "Copilot"
    assert data["goals"] == ["helpful comments"]


def test_search_query_prompt_differs_for_personal() -> None:
    product = build_search_query_prompt(
        product="A scheduling tool",
        keywords=["looking for"],
        subreddits=["SaaS"],
        purpose="product",
        goals=["signups"],
    )
    personal = build_search_query_prompt(
        product="I am a staff designer",
        keywords=["portfolio"],
        subreddits=["design"],
        purpose="personal",
        goals=["share critique"],
    )
    assert "need this product" in product
    assert "Purpose: product" in product
    assert "not buying-intent" in personal
    assert "Purpose: personal" in personal
    assert "1–3 words" in EXTRACT_PROMPT
    assert "self promotion" in EXTRACT_PROMPT


def test_ready_marker_is_stripped() -> None:
    text = f"I'll set up the workspace from this.\n{READY_MARKER}\n"
    visible, ready = split_ready_marker(text)
    assert ready is True
    assert visible == "I'll set up the workspace from this."
    assert READY_MARKER not in visible
    leftover, not_ready = split_ready_marker("What kind of design do you do?")
    assert not_ready is False
    assert leftover.startswith("What kind")


def test_stream_hides_partial_ready_marker() -> None:
    prefix = "I'll set this up now.\nREADY_FOR_WORK"
    assert visible_interview_stream(prefix) == "I'll set this up now."
    assert visible_interview_stream(f"I'll set this up now.\n{READY_MARKER}") == "I'll set this up now."
    assert "READY" not in visible_interview_stream("What is the aim?")

