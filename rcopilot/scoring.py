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


def _is_question(title: str) -> bool:
    lowered = title.strip().lower()
    if "?" in title:
        return True
    return any(lowered.startswith(prefix) for prefix in QUESTION_STARTS)


def _looking_for_tool(text: str) -> bool:
    return any(phrase in text for phrase in LOOKING_FOR_PHRASES)


def intent_terms_from_product(product: str, *, limit: int = 12) -> list[str]:
    """Turn a product blurb into short phrases/tokens to match against threads."""
    tokens = [
        token
        for token in _TOKEN.findall(product.lower())
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


def score_post(
    post: dict[str, Any],
    keywords: list[str],
    product: str = "",
) -> tuple[float, list[str], list[str]]:
    """Score a post 0..1 using intent heuristics.

    Heuristics:
    - keyword hits in title+selftext: +0.15 each, cap +0.5
    - product-blurb term hits: +0.12 each, cap +0.36
    - looking-for-tool phrasing: +0.2
    - question signal: +0.2
    - light discussion (0-1 top comments): +0.15
    - freshness: <6h +0.15, <24h +0.05
    """
    score = 0.0
    reasons: list[str] = []
    matched: list[str] = []

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

    product_terms = intent_terms_from_product(product)
    if product_terms:
        product_score = 0.0
        for term in product_terms:
            if term in text:
                matched.append(term)
                product_score += 0.12
        product_score = min(product_score, 0.36)
        if product_score:
            score += product_score
            reasons.append(f"product match (+{product_score:.2f})")

    if _looking_for_tool(text):
        score += 0.2
        reasons.append("looking-for-tool (+0.20)")

    title = post.get("title") or ""
    if _is_question(title):
        score += 0.2
        reasons.append("question signal (+0.20)")

    comments = post.get("top_comments") or []
    if isinstance(comments, str):
        comments = json.loads(comments)
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

    if (keywords or product_terms) and not matched:
        score = min(score, 0.2)
        reasons.append("weak intent fit (capped)")

    return min(score, 1.0), reasons, matched


def apply_scores(
    store: Store,
    posts: list[dict[str, Any]],
    discovery: DiscoveryConfig,
    product: str = "",
) -> None:
    """Compute and persist scores for *posts*."""
    for post in posts:
        score, reasons, matched = score_post(post, discovery.keywords, product=product)
        store.update_post(
            post["id"],
            relevance_score=score,
            score_reasons=json.dumps(reasons),
            keywords_matched=json.dumps(matched),
        )
