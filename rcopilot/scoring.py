"""Heuristic scoring for discovered Reddit posts."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from rcopilot.config import DiscoveryConfig
from rcopilot.store import Store

QUESTION_STARTS = (
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
    "looking",
    "anyone",
    "recommend",
)

LOOKING_FOR_PHRASES = (
    "looking for",
    "alternative to",
    "anyone using",
    "anyone know",
    "recommend a",
    "recommend me",
    "tool for",
    "app for",
    "how do you",
    "what do you use",
)

COMPLAINT_PHRASES = (
    "frustrated with",
    "doesn't work",
    "does not work",
    "broken",
    "hate that",
    "wish there was",
    "problem with",
    "struggling with",
    "fed up",
)

INTENT_LABELS = (
    "question",
    "looking-for-tool",
    "complaint",
    "unanswered",
)

_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "then",
        "than",
        "that",
        "this",
        "these",
        "those",
        "to",
        "of",
        "in",
        "on",
        "for",
        "with",
        "from",
        "your",
        "you",
        "we",
        "i",
        "it",
        "its",
        "is",
        "are",
        "be",
        "been",
        "being",
        "as",
        "at",
        "by",
        "into",
        "about",
        "over",
        "after",
        "before",
        "between",
        "when",
        "where",
        "who",
        "what",
        "why",
        "how",
        "not",
        "no",
        "so",
        "just",
        "only",
        "also",
        "can",
        "will",
        "want",
        "people",
        "help",
        "like",
        "make",
        "makes",
        "using",
        "use",
        "used",
        "dont",
        "does",
        "did",
        "have",
        "has",
        "had",
        "they",
        "their",
        "them",
        "our",
        "ours",
        "was",
        "were",
        "would",
        "should",
        "could",
        "really",
        "very",
        "more",
        "most",
        "some",
        "any",
        "all",
    }
)
_GENERIC = frozenset(
    {
        "reddit",
        "thread",
        "threads",
        "post",
        "posts",
        "comment",
        "comments",
        "subreddit",
        "sub",
        "here",
        "there",
        "something",
        "things",
        "thing",
    }
)


def _normalize_comments(post: dict[str, Any]) -> list[Any]:
    comments = post.get("top_comments") or []
    if isinstance(comments, str):
        try:
            comments = json.loads(comments)
        except json.JSONDecodeError:
            comments = []
    return comments if isinstance(comments, list) else []


def _is_question_text(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return False
    if "?" in text:
        return True
    first_line = lowered.splitlines()[0].strip()
    return any(first_line.startswith(prefix) for prefix in QUESTION_STARTS)


def _is_question(post: dict[str, Any]) -> bool:
    title = post.get("title") or ""
    selftext = post.get("selftext") or ""
    return _is_question_text(title) or _is_question_text(selftext)


def _looking_for_tool(text: str) -> bool:
    return any(phrase in text for phrase in LOOKING_FOR_PHRASES)


def _is_complaint(text: str) -> bool:
    return any(phrase in text for phrase in COMPLAINT_PHRASES)


def classify_intent(post: dict[str, Any]) -> list[str]:
    """Return stable intent label slugs for a post."""
    text = f"{post.get('title', '')} {post.get('selftext', '')}".lower()
    comments = _normalize_comments(post)
    labels: list[str] = []

    if _is_question(post):
        labels.append("question")
    if _looking_for_tool(text):
        labels.append("looking-for-tool")
    if _is_complaint(text):
        labels.append("complaint")
    if len(comments) == 0:
        labels.append("unanswered")

    return labels


def intent_terms_from_briefing(briefing: str, *, limit: int = 12) -> list[str]:
    """Turn a workspace briefing into short phrases/tokens to match against threads."""
    tokens = [
        token
        for token in _TOKEN.findall(briefing.lower())
        if len(token) >= 4 and token not in _STOPWORDS and token not in _GENERIC
    ]
    terms: list[str] = []
    seen: set[str] = set()
    for left, right in zip(tokens, tokens[1:]):
        phrase = f"{left} {right}"
        if phrase not in seen:
            seen.add(phrase)
            terms.append(phrase)
    for token in tokens:
        if token not in seen:
            seen.add(token)
            terms.append(token)
    return terms[:limit]


def intent_terms_from_product(product: str, *, limit: int = 12) -> list[str]:
    """Alias for briefing terms (legacy name)."""
    return intent_terms_from_briefing(product, limit=limit)


def score_post(
    post: dict[str, Any],
    keywords: list[str],
    product: str = "",
) -> tuple[float, list[str], list[str], list[str]]:
    """Score a post 0..1 using intent heuristics.

    Returns (score, reasons, matched_keywords, intent_labels).

    Heuristics:
    - keyword hits in title+selftext: +0.15 each, cap +0.5
    - product-blurb term hits: +0.12 each, cap +0.36
    - looking-for-tool phrasing: +0.2
    - question signal: +0.2
    - unanswered question (question radar): +0.15
    - light discussion (0-1 top comments): +0.15
    - freshness: <6h +0.15, <24h +0.05
    """
    score = 0.0
    reasons: list[str] = []
    matched: list[str] = []
    labels = classify_intent(post)

    text = f"{post.get('title', '')} {post.get('selftext', '')}".lower()

    if keywords:
        keyword_score = 0.0
        for keyword in keywords:
            kw = keyword.strip().lower()
            if kw and kw in text:
                matched.append(keyword)
                keyword_score += 0.15
        keyword_score = min(keyword_score, 0.5)
        if keyword_score:
            score += keyword_score
            reasons.append(f"keyword match (+{keyword_score:.2f})")

    briefing_terms = intent_terms_from_briefing(product)
    if briefing_terms:
        briefing_score = 0.0
        for term in briefing_terms:
            if term in text:
                matched.append(term)
                briefing_score += 0.12
        briefing_score = min(briefing_score, 0.36)
        if briefing_score:
            score += briefing_score
            reasons.append(f"context match (+{briefing_score:.2f})")

    if "looking-for-tool" in labels:
        score += 0.2
        reasons.append("looking-for-tool (+0.20)")

    if "question" in labels:
        score += 0.2
        reasons.append("question signal (+0.20)")

    if "question" in labels and "unanswered" in labels:
        score += 0.15
        reasons.append("unanswered question (+0.15)")

    comments = _normalize_comments(post)
    if len(comments) <= 1:
        score += 0.15
        reasons.append("light discussion (+0.15)")

    created_utc = float(post.get("created_utc") or 0)
    if created_utc:
        age_hours = (datetime.now(timezone.utc).timestamp() - created_utc) / 3600
        if age_hours < 6:
            score += 0.15
            reasons.append("fresh (<6h) (+0.15)")
        elif age_hours < 24:
            score += 0.05
            reasons.append("recent (<24h) (+0.05)")

    if (keywords or briefing_terms) and not matched:
        score = min(score, 0.2)
        reasons.append("weak intent fit (capped)")

    return min(score, 1.0), reasons, matched, labels


def apply_scores(
    store: Store,
    posts: list[dict[str, Any]],
    discovery: DiscoveryConfig,
    product: str = "",
    *,
    project_id: str | None = None,
) -> None:
    """Compute and persist scores for *posts*."""
    from rcopilot.store import DEFAULT_PROJECT_ID

    scoped_id = project_id or DEFAULT_PROJECT_ID
    for post in posts:
        score, reasons, matched, labels = score_post(
            post, discovery.keywords, product=product
        )
        store.update_post(
            post["id"],
            project_id=scoped_id,
            relevance_score=score,
            score_reasons=json.dumps(reasons),
            keywords_matched=json.dumps(matched),
            intent_labels=json.dumps(labels),
        )
