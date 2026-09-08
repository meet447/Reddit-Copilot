"""Comment variant parsing tests (no network)."""

from __future__ import annotations

import json

import pytest

from rcopilot.llm import parse_comment_variants


def test_parse_comment_variants_json() -> None:
    raw = json.dumps(
        [
            {
                "label": "Direct answer",
                "body": "I would start with pytest and a tiny fixture.",
            },
            {
                "label": "Lived experience",
                "body": "I hit this last year and switched off the watcher.",
            },
            {
                "label": "Concise take",
                "body": "Skip the plugin. A conftest hook is enough.",
            },
        ]
    )
    variants = parse_comment_variants(raw)
    assert [item["id"] for item in variants] == ["v1", "v2", "v3"]
    assert variants[0]["label"] == "Direct answer"
    assert "pytest" in variants[0]["body"]
    assert "—" not in variants[1]["body"]


def test_parse_comment_variants_caps_at_three() -> None:
    raw = json.dumps(
        [
            {"label": "A", "body": "First angle stays short and useful here."},
            {"label": "B", "body": "Second angle is a lived Windows story."},
            {"label": "C", "body": "Third angle just names the actual fix."},
            {"label": "D", "body": "Fourth should be dropped."},
        ]
    )
    variants = parse_comment_variants(raw)
    assert len(variants) == 3


def test_parse_comment_variants_plain_text_fallback() -> None:
    variants = parse_comment_variants(
        "I switched to pytest last year and it cut our CI time in half."
    )
    assert len(variants) == 1
    assert variants[0]["id"] == "v1"
    assert "pytest" in variants[0]["body"]


def test_parse_comment_variants_empty_list_errors() -> None:
    with pytest.raises(ValueError, match="no usable comment variants"):
        parse_comment_variants("[]")
