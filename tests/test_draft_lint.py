"""Draft lint tests."""

from __future__ import annotations

from rcopilot.draft_lint import apply_lint, clean_draft, lint_draft


def test_clean_removes_em_dashes_and_hope_this_helps() -> None:
    raw = "You could try asyncio — it handles concurrency well. Hope this helps!"
    cleaned = clean_draft(raw)

    assert "\u2014" not in cleaned
    assert "\u2013" not in cleaned
    assert "hope this helps" not in cleaned.lower()
    assert "asyncio" in cleaned


def test_lint_flags_bullets_and_pitch_only() -> None:
    bullet_text = "Here is my advice:\n- first point\n- second point"
    bullet_result = lint_draft(bullet_text)
    assert "bullets" in bullet_result.codes
    assert not bullet_result.ok

    pitch_text = "Check out AcmeWidget Pro for your workflow automation needs."
    pitch_result = lint_draft(
        pitch_text,
        product="AcmeWidget Pro is a workflow automation tool for teams.",
    )
    assert "pitch_only" in pitch_result.codes
    assert not pitch_result.ok


def test_clean_leaves_good_short_human_comment_mostly_intact() -> None:
    raw = "I switched to pytest last year and it cut our CI time in half."
    cleaned = clean_draft(raw)
    result = apply_lint(raw)

    assert cleaned == raw
    assert result.ok
    assert result.cleaned == raw
    assert result.codes == frozenset()


def test_short_product_mention_is_not_pitch_only() -> None:
    raw = (
        "I hit the same hang on Windows. Switching off the file watcher fixed it "
        "for me — wait, commas work too."
    )
    # no em dash in this version
    raw = (
        "I hit the same hang on Windows. Switching off the file watcher fixed it "
        "for me. AcmeWidget was fine once that was gone."
    )
    result = lint_draft(
        raw,
        product="AcmeWidget Pro is a workflow automation tool for teams.",
    )
    assert "pitch_only" not in result.codes


def test_default_prompt_has_placeholders_and_anti_slop_rules() -> None:
    from rcopilot.config import DEFAULT_PROMPT_TEMPLATE, SafeDict

    filled = DEFAULT_PROMPT_TEMPLATE.format_map(
        SafeDict(
            title="t",
            selftext="b",
            comments="(none)",
            product="p",
            tone="calm",
            persona="founder",
            avoid="hype",
        )
    )
    assert "em dashes" in filled.lower() or "em dash" in filled.lower()
    assert "hope this helps" in filled.lower()
    assert "bullet" in filled.lower()
    assert "{title}" not in filled
