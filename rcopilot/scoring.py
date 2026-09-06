"""Heuristic scoring for discovered Reddit posts."""

from __future__ import annotations

import json
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


def _is_question(title: str) -> bool:
    lowered = title.strip().lower()
    if "?" in title:
        return True
    return any(lowered.startswith(prefix) for prefix in QUESTION_STARTS)


def score_post(post: dict[str, Any], keywords: list[str]) -> tuple[float, list[str], list[str]]:
    """Score a post 0..1 using simple heuristics.

    Heuristics:
    - keyword hits in title+selftext (case-insensitive): +0.15 each, cap +0.5
    - question signal: +0.2
    - light discussion (0-1 top comments): +0.15
    - freshness: <6h +0.15, <24h +0.05

    If keywords is empty, skip the keyword component (other signals still apply).
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

    return min(score, 1.0), reasons, matched


def apply_scores(store: Store, posts: list[dict[str, Any]], discovery: DiscoveryConfig) -> None:
    """Compute and persist scores for *posts*."""
    for post in posts:
        score, reasons, matched = score_post(post, discovery.keywords)
        store.update_post(
            post["id"],
            relevance_score=score,
            score_reasons=json.dumps(reasons),
            keywords_matched=json.dumps(matched),
        )
