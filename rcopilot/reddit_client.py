"""PRAW wrapper for fetching posts, OAuth, and posting comments."""

from __future__ import annotations

import html
import logging
import time
from datetime import datetime, timezone
from typing import Any, Iterator

import praw
from praw.exceptions import RedditAPIException

from rcopilot.config import Account

logger = logging.getLogger(__name__)

OAUTH_SCOPES = ["identity", "read", "submit"]
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8000/api/oauth/callback"

# Reddit comment permalinks: /r/sub/comments/POSTID/slug/COMMENTID/
_REMOVED_BODIES = frozenset({None, "[removed]", "[deleted]"})


def comment_id_from_permalink(url: str | None) -> str | None:
    """Extract a Reddit comment id from a comment permalink, if present."""
    if not url:
        return None
    parts = [p for p in url.split("?")[0].rstrip("/").split("/") if p]
    try:
        idx = next(i for i, part in enumerate(parts) if part.lower() == "comments")
    except StopIteration:
        return None
    after = parts[idx + 1 :]
    # Thread: /comments/POSTID/slug — comment: /comments/POSTID/slug/COMMENTID
    if len(after) >= 3:
        return after[2]
    return None


def fetch_comment_outcome(reddit: praw.Reddit, comment_id: str) -> dict[str, Any]:
    """Fetch score / reply count / removed state for a posted comment."""
    bare_id = comment_id.removeprefix("t1_")
    try:
        comment = reddit.comment(id=bare_id)
        comment.refresh()
    except Exception as exc:
        logger.warning("Could not fetch comment %s: %s", bare_id, exc)
        return {
            "score": None,
            "replies": 0,
            "removed": True,
            "permalink": None,
        }

    body = getattr(comment, "body", None)
    removed = body in _REMOVED_BODIES

    replies = 0
    try:
        comment.replies.replace_more(limit=0)
        replies = len(list(comment.replies))
    except Exception:
        replies = int(getattr(comment, "num_replies", 0) or 0)

    permalink = getattr(comment, "permalink", None)
    if permalink and not str(permalink).startswith("http"):
        permalink = f"https://www.reddit.com{permalink}"

    score = getattr(comment, "score", None)
    try:
        score = int(score) if score is not None else None
    except (TypeError, ValueError):
        score = None

    return {
        "score": score,
        "replies": replies,
        "removed": removed,
        "permalink": permalink,
    }


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
    try:
        num_comments = int(getattr(submission, "num_comments", 0) or 0)
    except (TypeError, ValueError):
        num_comments = 0
    return {
        "id": submission.id,
        "subreddit": name,
        "title": submission.title or "",
        "selftext": submission.selftext or "",
        "url": submission.url or "",
        "permalink": f"https://www.reddit.com{submission.permalink}",
        "created_utc": float(submission.created_utc or 0),
        "top_comments": _top_comments(submission) if include_comments else [],
        "num_comments": num_comments,
    }


def iter_listing_posts(
    reddit: praw.Reddit,
    subreddits: list[str],
    listing: str,
    limit: int,
    *,
    include_comments: bool = True,
) -> Iterator[dict[str, Any]]:
    """Yield recent submissions from *subreddits* as Reddit returns them."""
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
            yield _submission_to_post(
                submission,
                subreddit_name=subreddit_name,
                include_comments=include_comments,
            )


def fetch_posts(
    reddit: praw.Reddit,
    subreddits: list[str],
    listing: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Fetch recent submissions from *subreddits*."""
    posts = list(iter_listing_posts(reddit, subreddits, listing, limit))
    logger.info("Fetched %d posts from %d subreddit(s)", len(posts), len(subreddits))
    return posts


def iter_search_posts(
    reddit: praw.Reddit,
    subreddits: list[str],
    queries: list[str],
    *,
    limit_per_query: int = 10,
) -> Iterator[dict[str, Any]]:
    """Yield search matches as Reddit returns them."""
    cleaned = [query.strip() for query in queries if query and query.strip()]
    if not subreddits or not cleaned:
        return

    combo = "+".join(subreddits)
    target = reddit.subreddit(combo)
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
            yield _submission_to_post(submission, include_comments=False)


def search_posts(
    reddit: praw.Reddit,
    subreddits: list[str],
    queries: list[str],
    *,
    limit_per_query: int = 10,
) -> list[dict[str, Any]]:
    """Search configured subreddits with LLM/fallback queries."""
    posts = list(
        iter_search_posts(
            reddit,
            subreddits,
            queries,
            limit_per_query=limit_per_query,
        )
    )
    logger.info("Search returned %d post(s) from %d quer(y/ies)", len(posts), len(queries))
    return posts


def post_comment(reddit: praw.Reddit, post_id: str, body: str) -> tuple[str, str | None]:
    """Post *body* as a comment on *post_id*; return (permalink, comment_id)."""
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

    comment_id = getattr(comment, "id", None)
    permalink = getattr(comment, "permalink", None)
    if permalink:
        if not str(permalink).startswith("http"):
            permalink = f"https://www.reddit.com{permalink}"
        return str(permalink), str(comment_id) if comment_id else None

    logger.warning("Comment posted but permalink unavailable for post %s", post_id)
    fallback = getattr(submission, "permalink", None) or ""
    if fallback and not str(fallback).startswith("http"):
        fallback = f"https://www.reddit.com{fallback}"
    return str(fallback), str(comment_id) if comment_id else None


def post_submission(
    reddit: praw.Reddit,
    subreddit: str,
    title: str,
    selftext: str,
) -> tuple[str, str | None]:
    """Create a self-text submission; return (permalink, submission_id)."""
    cleaned_sub = subreddit.strip().lstrip("r/")
    if not cleaned_sub:
        raise ValueError("Subreddit is required")
    if not title.strip():
        raise ValueError("Title must not be empty")
    if not selftext.strip():
        raise ValueError("Post body must not be empty")

    target = reddit.subreddit(cleaned_sub)
    try:
        submission = target.submit(title=title.strip(), selftext=selftext.strip())
    except RedditAPIException as exc:
        for item in exc.items:
            error_type = getattr(item, "error_type", "") or ""
            message = getattr(item, "message", str(exc)) or str(exc)
            if error_type == "RATELIMIT":
                raise RuntimeError(f"Reddit rate limit exceeded: {message}") from exc
        raise

    submission_id = getattr(submission, "id", None)
    permalink = getattr(submission, "permalink", None)
    if permalink:
        if not str(permalink).startswith("http"):
            permalink = f"https://www.reddit.com{permalink}"
        return str(permalink), str(submission_id) if submission_id else None

    logger.warning("Submission created but permalink unavailable for r/%s", cleaned_sub)
    return f"https://www.reddit.com/r/{cleaned_sub}/", str(submission_id) if submission_id else None


def sample_subreddit_post_hours(
    reddit: praw.Reddit,
    subreddit: str,
    *,
    limit: int = 100,
) -> list[int]:
    """Return UTC hour-of-day (0-23) for recent posts in *subreddit*."""
    cleaned_sub = subreddit.strip().lstrip("r/")
    if not cleaned_sub:
        return []
    hours: list[int] = []
    try:
        for submission in reddit.subreddit(cleaned_sub).new(limit=limit):
            created = float(getattr(submission, "created_utc", 0) or 0)
            if not created:
                continue
            hours.append(int(datetime.fromtimestamp(created, tz=timezone.utc).hour))
    except Exception as exc:
        logger.warning("Could not sample hours for r/%s: %s", cleaned_sub, exc)
        return []
    return hours


_ICON_CACHE: dict[str, tuple[float, str | None]] = {}
_ICON_CACHE_TTL_SECONDS = 60 * 60 * 24  # 24h


def _clean_icon_url(value: object) -> str | None:
    if not value:
        return None
    url = html.unescape(str(value)).strip()
    if not url or url in {"default", "self"}:
        return None
    if url.startswith("//"):
        url = f"https:{url}"
    if not url.startswith("http"):
        return None
    return url


def fetch_subreddit_icon(reddit: praw.Reddit, subreddit: str) -> str | None:
    """Return a community icon URL for *subreddit*, or None."""
    cleaned = subreddit.strip().lstrip("r/")
    if not cleaned:
        return None
    key = cleaned.lower()
    cached = _ICON_CACHE.get(key)
    now = time.time()
    if cached and now - cached[0] < _ICON_CACHE_TTL_SECONDS:
        return cached[1]

    icon: str | None = None
    try:
        sub = reddit.subreddit(cleaned)
        icon = (
            _clean_icon_url(getattr(sub, "community_icon", None))
            or _clean_icon_url(getattr(sub, "icon_img", None))
            or _clean_icon_url(getattr(sub, "header_img", None))
        )
    except Exception as exc:
        logger.debug("Could not fetch icon for r/%s: %s", cleaned, exc)
        icon = None

    _ICON_CACHE[key] = (now, icon)
    return icon


def fetch_subreddit_icons(
    reddit: praw.Reddit,
    names: list[str],
    *,
    limit: int = 40,
) -> dict[str, str | None]:
    """Batch-resolve icon URLs keyed by original cleaned name."""
    results: dict[str, str | None] = {}
    seen: set[str] = set()
    for raw in names:
        cleaned = raw.strip().lstrip("r/")
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        results[cleaned] = fetch_subreddit_icon(reddit, cleaned)
        if len(results) >= limit:
            break
    return results
