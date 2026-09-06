"""PRAW wrapper for fetching posts, OAuth, and posting comments."""

from __future__ import annotations

import logging
from typing import Any

import praw
from praw.exceptions import RedditAPIException

from rcopilot.config import Account

logger = logging.getLogger(__name__)

OAUTH_SCOPES = ["identity", "read", "submit"]
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8000/api/oauth/callback"


def _base_kwargs(account: Account) -> dict[str, str]:
    if not account.client_id:
        raise ValueError("Missing REDDIT_CLIENT_ID. Create a Reddit web app and paste the client id.")
    return {
        "client_id": account.client_id,
        "client_secret": account.client_secret or "",
        "user_agent": account.user_agent,
    }


def get_reddit(account: Account, *, redirect_uri: str | None = None) -> praw.Reddit:
    """Return an authenticated PRAW Reddit instance for *account*."""
    kwargs = _base_kwargs(account)
    if account.refresh_token:
        return praw.Reddit(**kwargs, refresh_token=account.refresh_token)
    if account.username and account.password:
        return praw.Reddit(**kwargs, username=account.username, password=account.password)
    if redirect_uri:
        return praw.Reddit(**kwargs, redirect_uri=redirect_uri)
    raise ValueError(
        "Reddit is not connected. Use Connect Reddit in onboarding or Settings (OAuth)."
    )


def oauth_authorize_url(account: Account, redirect_uri: str, state: str) -> str:
    """Return Reddit's consent URL for the authorization-code flow."""
    reddit = praw.Reddit(**_base_kwargs(account), redirect_uri=redirect_uri)
    return reddit.auth.url(scopes=OAUTH_SCOPES, state=state, duration="permanent")


def oauth_exchange_code(account: Account, redirect_uri: str, code: str) -> tuple[str, str]:
    """Exchange an OAuth code for a refresh token and Reddit username."""
    reddit = praw.Reddit(**_base_kwargs(account), redirect_uri=redirect_uri)
    refresh_token = reddit.auth.authorize(code)
    if not refresh_token:
        raise ValueError(
            "Reddit did not return a refresh token. Create a web app and set duration to permanent."
        )
    me = reddit.user.me()
    username = str(getattr(me, "name", "") or "")
    return refresh_token, username


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


def _submission_to_post(
    submission: praw.models.Submission,
    *,
    subreddit_name: str | None = None,
    include_comments: bool = True,
) -> dict[str, Any]:
    name = subreddit_name or str(getattr(submission.subreddit, "display_name", "") or submission.subreddit)
    return {
        "id": submission.id,
        "subreddit": name,
        "title": submission.title or "",
        "selftext": submission.selftext or "",
        "url": submission.url or "",
        "permalink": f"https://www.reddit.com{submission.permalink}",
        "created_utc": float(submission.created_utc or 0),
        "top_comments": _top_comments(submission) if include_comments else [],
    }


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
            posts.append(_submission_to_post(submission, subreddit_name=subreddit_name))

    logger.info("Fetched %d posts from %d subreddit(s)", len(posts), len(subreddits))
    return posts


def search_posts(
    reddit: praw.Reddit,
    subreddits: list[str],
    queries: list[str],
    *,
    limit_per_query: int = 10,
) -> list[dict[str, Any]]:
    """Search configured subreddits with LLM/fallback queries."""
    cleaned = [query.strip() for query in queries if query and query.strip()]
    if not subreddits or not cleaned:
        return []

    combo = "+".join(subreddits)
    target = reddit.subreddit(combo)
    posts: list[dict[str, Any]] = []
    seen: set[str] = set()

    for query in cleaned:
        logger.info("Searching r/%s for %r (limit=%d)", combo, query, limit_per_query)
        try:
            iterator = target.search(
                query,
                sort="new",
                time_filter="month",
                limit=limit_per_query,
            )
        except Exception as exc:
            logger.exception("Search failed for %r: %s", query, exc)
            continue

        for submission in iterator:
            if submission.id in seen:
                continue
            seen.add(submission.id)
            posts.append(_submission_to_post(submission, include_comments=False))

    logger.info("Search returned %d post(s) from %d quer(y/ies)", len(posts), len(cleaned))
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
