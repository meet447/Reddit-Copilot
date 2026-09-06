"""PRAW wrapper for fetching posts and posting comments."""

from __future__ import annotations

import logging
from typing import Any

import praw
from praw.exceptions import RedditAPIException

from rcopilot.config import Account

logger = logging.getLogger(__name__)


def get_reddit(account: Account) -> praw.Reddit:
    """Return an authenticated PRAW Reddit instance for *account*."""
    return praw.Reddit(
        client_id=account.client_id,
        client_secret=account.client_secret,
        username=account.username,
        password=account.password,
        user_agent=account.user_agent,
    )


def _listing_method(reddit: praw.Reddit, subreddit_name: str, listing: str):
    subreddit = reddit.subreddit(subreddit_name)
    if listing == "new":
        return subreddit.new
    if listing == "hot":
        return subreddit.hot
    raise ValueError(f"Invalid listing '{listing}'; must be 'hot' or 'new'")


def _top_comments(submission: praw.models.Submission, limit: int = 4) -> list[dict[str, Any]]:
    submission.comment_sort = "top"
    submission.comments.replace_more(limit=0)
    comments: list[dict[str, Any]] = []
    for comment in submission.comments:
        if getattr(comment, "body", None) in (None, "[deleted]", "[removed]"):
            continue
        comments.append({"body": comment.body, "score": int(comment.score or 0)})
    comments.sort(key=lambda item: item["score"], reverse=True)
    return comments[:limit]


def fetch_posts(
    reddit: praw.Reddit,
    subreddits: list[str],
    listing: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Fetch recent submissions from *subreddits*."""
    posts: list[dict[str, Any]] = []
    seen: set[str] = set()

    for subreddit_name in subreddits:
        logger.info("Fetching %s/%s (limit=%d)", listing, subreddit_name, limit)
        try:
            iterator = _listing_method(reddit, subreddit_name, listing)(limit=limit)
        except Exception as exc:
            logger.exception("Failed to fetch r/%s: %s", subreddit_name, exc)
            continue

        for submission in iterator:
            if submission.id in seen:
                continue
            seen.add(submission.id)

            posts.append(
                {
                    "id": submission.id,
                    "subreddit": subreddit_name,
                    "title": submission.title or "",
                    "selftext": submission.selftext or "",
                    "url": submission.url or "",
                    "permalink": f"https://www.reddit.com{submission.permalink}",
                    "created_utc": float(submission.created_utc or 0),
                    "top_comments": _top_comments(submission),
                }
            )

    logger.info("Fetched %d posts from %d subreddit(s)", len(posts), len(subreddits))
    return posts


def post_comment(reddit: praw.Reddit, post_id: str, body: str) -> str:
    """Post *body* as a comment on *post_id*; return the comment permalink."""
    if not body.strip():
        raise ValueError("Comment body must not be empty")

    submission = reddit.submission(id=post_id)
    try:
        comment = submission.reply(body)
    except RedditAPIException as exc:
        for item in exc.items:
            error_type = getattr(item, "error_type", "") or ""
            message = getattr(item, "message", str(exc)) or str(exc)
            if error_type == "RATELIMIT":
                raise RuntimeError(f"Reddit rate limit exceeded: {message}") from exc
            if error_type == "THREAD_LOCKED":
                raise RuntimeError(f"Thread is locked and cannot be commented on: {message}") from exc
        raise

    permalink = getattr(comment, "permalink", None)
    if permalink:
        if permalink.startswith("http"):
            return permalink
        return f"https://www.reddit.com{permalink}"

    logger.warning("Comment posted but permalink unavailable for post %s", post_id)
    return submission.permalink
