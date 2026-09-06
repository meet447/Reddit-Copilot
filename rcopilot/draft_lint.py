"""Strip common AI-slop tells from Reddit comment drafts and flag remaining risks.

Detects em dashes, bot-like closers, markdown structure, and pitch-only replies,
cleans what it can automatically, and returns structured lint results for the UI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BOT_PHRASES: frozenset[str] = frozenset(
    {
        "hope this helps",
        "hope that helps",
        "let me know if you have any questions",
        "feel free to ask",
        "happy to help",
        "great question",
        "as an ai",
        "as a language model",
    }
)

_PITCH_STARTS = (
    "check out",
    "i built",
    "try my",
    "my tool",
    "our product",
)

_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "and",
        "for",
        "with",
        "your",
        "that",
        "this",
        "are",
        "was",
        "were",
        "has",
        "have",
        "had",
        "you",
        "our",
        "my",
    }
)

_EM_DASH = "\u2014"
_EN_DASH = "\u2013"
_CURLY_OPEN_DOUBLE = "\u201c"
_CURLY_CLOSE_DOUBLE = "\u201d"
_CURLY_OPEN_SINGLE = "\u2018"
_CURLY_CLOSE_SINGLE = "\u2019"

_HEADING_LINE = re.compile(r"^\s*#+\s")
_BULLET_LINE = re.compile(r"^\s*([-*+]|\d+\.)\s+", re.MULTILINE)
_EN_DASH_RANGE = re.compile(r"(\d)\s*\u2013\s*(\d)")
_WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class LintIssue:
    code: str
    message: str


@dataclass
class LintResult:
    issues: list[LintIssue] = field(default_factory=list)
    cleaned: str = ""

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def codes(self) -> frozenset[str]:
        return frozenset(issue.code for issue in self.issues)


def clean_draft(text: str) -> str:
    """Normalize and strip common AI-draft artifacts from comment text."""
    cleaned = text
    cleaned = _normalize_quotes(cleaned)
    cleaned = _replace_dashes(cleaned)
    cleaned = _strip_heading_lines(cleaned)
    cleaned = _remove_bot_closers(cleaned)
    cleaned = _collapse_blank_lines(cleaned)
    cleaned = _strip_wrapping_quotes(cleaned)
    return cleaned.strip()


def lint_draft(text: str, *, product: str = "") -> LintResult:
    """Lint a draft, auto-cleaning where possible and reporting issue codes."""
    cleaned = clean_draft(text)
    issues: list[LintIssue] = []
    seen: set[str] = set()

    def add(code: str, message: str) -> None:
        if code not in seen:
            seen.add(code)
            issues.append(LintIssue(code=code, message=message))

    if _EM_DASH in text or _EN_DASH in text:
        add("em_dash", "Contains em/en dashes (auto-cleaned)")

    if _contains_bot_phrase(text):
        add("bot_phrase", "Contains bot-like closing phrase (auto-cleaned)")

    if _BULLET_LINE.search(text):
        add("bullets", "Contains markdown bullet/list lines")

    if _has_markdown_heading(text):
        add("heading", "Contains markdown heading")

    if not cleaned:
        add("empty", "Draft is empty after cleaning")
    elif product and _is_pitch_only(cleaned, product):
        add("pitch_only", "Draft looks like a product pitch with little substance")

    return LintResult(issues=issues, cleaned=cleaned)


def apply_lint(text: str, *, product: str = "") -> LintResult:
    """Clean a draft and return lint results (alias for lint_draft)."""
    return lint_draft(text, product=product)


def _normalize_quotes(text: str) -> str:
    return (
        text.replace(_CURLY_OPEN_DOUBLE, '"')
        .replace(_CURLY_CLOSE_DOUBLE, '"')
        .replace(_CURLY_OPEN_SINGLE, "'")
        .replace(_CURLY_CLOSE_SINGLE, "'")
    )


def _replace_dashes(text: str) -> str:
    text = _EN_DASH_RANGE.sub(r"\1 - \2", text)
    text = text.replace(_EM_DASH, ", ")
    text = text.replace(_EN_DASH, ", ")
    text = re.sub(r",\s*,", ", ", text)
    text = re.sub(r" {2,}", " ", text)
    return text


def _strip_heading_lines(text: str) -> str:
    lines = text.splitlines()
    while lines and _HEADING_LINE.match(lines[0]):
        lines.pop(0)
    while lines and _HEADING_LINE.match(lines[-1]):
        lines.pop()
    return "\n".join(lines)


def _remove_bot_closers(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return stripped

    parts = _SENTENCE_SPLIT.split(stripped)
    while parts:
        last = parts[-1].lower()
        if any(phrase in last for phrase in BOT_PHRASES):
            parts.pop()
            continue
        break

    return " ".join(parts).strip()


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


def _strip_wrapping_quotes(text: str) -> str:
    stripped = text.strip()
    if len(stripped) < 2:
        return stripped

    pairs = (('"', '"'), ("'", "'"))
    for open_q, close_q in pairs:
        if stripped.startswith(open_q) and stripped.endswith(close_q):
            inner = stripped[1:-1].strip()
            if inner:
                return inner
    return stripped


def _contains_bot_phrase(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in BOT_PHRASES)


def _has_markdown_heading(text: str) -> bool:
    return any(_HEADING_LINE.match(line) for line in text.splitlines())


def _content_words(text: str) -> list[str]:
    return [word.lower() for word in _WORD.findall(text) if word.lower() not in _STOPWORDS]


def _product_tokens(product: str) -> list[str]:
    tokens = [
        word.lower()
        for word in _WORD.findall(product)
        if len(word) > 3 and word.lower() not in _STOPWORDS
    ]
    return list(dict.fromkeys(tokens))


def _is_pitch_only(cleaned: str, product: str) -> bool:
    tokens = _product_tokens(product)
    if not tokens:
        return False

    lower = cleaned.lower()
    if not any(token in lower for token in tokens):
        return False

    words = _content_words(cleaned)
    word_count = len(words)
    if word_count == 0:
        return False

    matched = sum(1 for word in words if word in tokens)
    density = matched / word_count
    opener = lower[:48]

    if any(prefix in opener for prefix in _PITCH_STARTS):
        return True
    if density > 0.25:
        return True
    # Short replies that mostly name the product read as pitches.
    if word_count < 25 and density >= 0.2:
        return True
    return False
