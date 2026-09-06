"""Orchestration pipeline: fetch, draft, approve, schedule, and post comments."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from rcopilot import reddit_client
from rcopilot.config import AppConfig, Account
from rcopilot.llm import generate_comment
from rcopilot.scoring import apply_scores
from rcopilot.store import Store

logger = logging.getLogger(__name__)


def _resolve_account(config: AppConfig, account_name: str | None) -> Account:
    if not config.accounts:
        raise ValueError("No accounts configured. Add an account in config.yaml and set Reddit credentials in .env")
    if account_name:
        for account in config.accounts:
            if account.name == account_name:
                return account
        raise ValueError(f"Unknown account: {account_name}")
    return config.accounts[0]


def _voice_kwargs(config: AppConfig) -> dict[str, str]:
    return {
        "product": config.voice.product,
        "tone": config.voice.tone,
        "persona": config.voice.persona,
        "avoid": config.voice.avoid,
    }


def fetch_and_store(config: AppConfig, store: Store) -> int:
    """Fetch posts from Reddit, persist, and score them. Returns count of new posts."""
    store.ensure_schema()
    if not config.subreddits:
        raise ValueError("No subreddits configured in config.yaml")
    account = _resolve_account(config, None)
    if not account.client_id or not account.client_secret:
        raise ValueError(
            "Missing Reddit API credentials. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env"
        )
    reddit = reddit_client.get_reddit(account)

    existing_ids = {
        row["id"] for row in store.connect().execute("SELECT id FROM posts").fetchall()
    }

    fetched = reddit_client.fetch_posts(
        reddit,
        config.subreddits,
        config.listing,
        config.fetch_limit,
    )

    new_count = 0
    stored_posts: list[dict[str, Any]] = []
    for post in fetched:
        is_new = post["id"] not in existing_ids
        store.upsert_post(**post)
        stored_posts.append(store.get_post(post["id"]) or post)
        if is_new:
            existing_ids.add(post["id"])
            new_count += 1

    apply_scores(store, stored_posts, config.discovery)
    store.add_audit("fetched", detail={"new_count": new_count, "total": len(stored_posts)})
    logger.info("Stored %d new post(s), scored %d", new_count, len(stored_posts))
    return new_count


def _generate_draft_body(config: AppConfig, post: dict[str, Any]) -> str:
    return generate_comment(
        config.llm,
        post["title"],
        post["selftext"],
        post.get("top_comments") or [],
        config.prompt_template,
        **_voice_kwargs(config),
    )


def _eligible_posts_for_drafting(store: Store, config: AppConfig) -> list[dict[str, Any]]:
    posts = store.list_posts(undrafted=True, skipped=False, min_score=config.discovery.min_score)
    return posts


def draft_pending(config: AppConfig, store: Store, account_name: str | None = None) -> int:
    """Create LLM drafts for eligible posts."""
    store.ensure_schema()
    if not config.llm.api_key:
        raise ValueError("Missing LLM_API_KEY in .env (or llm.api_key in config)")
    account = _resolve_account(config, account_name)
    posts = _eligible_posts_for_drafting(store, config)
    created = 0

    for post in posts:
        try:
            body = _generate_draft_body(config, post)
            draft_id = store.create_draft(post["id"], account.name, body, status="pending")
            store.add_audit("drafted", draft_id=draft_id, post_id=post["id"])
            created += 1
            logger.info("Drafted comment for post %s", post["id"])
        except Exception as exc:
            logger.exception("LLM draft failed for post %s: %s", post["id"], exc)
            draft_id = store.create_draft(post["id"], account.name, "", status="error")
            store.update_draft(draft_id, error=str(exc))
            store.add_audit("draft_error", draft_id=draft_id, post_id=post["id"], detail={"error": str(exc)})

    logger.info("Created %d draft(s)", created)
    return created


def draft_one(config: AppConfig, store: Store, post_id: str, account_name: str | None = None) -> int:
    """Draft a single post by id (Discover UI)."""
    store.ensure_schema()
    post = store.get_post(post_id)
    if post is None:
        raise ValueError(f"Post not found: {post_id}")
    if post.get("skipped"):
        raise ValueError(f"Post {post_id} is skipped")
    existing = store.connect().execute(
        "SELECT id FROM drafts WHERE post_id = ?", (post_id,)
    ).fetchone()
    if existing:
        raise ValueError(f"Post {post_id} already has a draft")

    account = _resolve_account(config, account_name)
    if not config.llm.api_key:
        raise ValueError("Missing LLM_API_KEY in .env (or llm.api_key in config)")

    try:
        body = _generate_draft_body(config, post)
        draft_id = store.create_draft(post_id, account.name, body, status="pending")
        store.add_audit("drafted", draft_id=draft_id, post_id=post_id)
        return draft_id
    except Exception as exc:
        draft_id = store.create_draft(post_id, account.name, "", status="error")
        store.update_draft(draft_id, error=str(exc))
        store.add_audit("draft_error", draft_id=draft_id, post_id=post_id, detail={"error": str(exc)})
        raise


def skip_post(store: Store, post_id: str) -> None:
    """Mark a post as skipped."""
    post = store.get_post(post_id)
    if post is None:
        raise ValueError(f"Post not found: {post_id}")
    store.update_post(post_id, skipped=1)
    store.add_audit("skipped", post_id=post_id)


def regenerate_draft(config: AppConfig, store: Store, draft_id: int) -> None:
    """Regenerate an LLM draft body."""
    draft = store.get_draft(draft_id)
    if draft is None:
        raise ValueError(f"Draft not found: {draft_id}")
    if not config.llm.api_key:
        raise ValueError("Missing LLM_API_KEY in .env (or llm.api_key in config)")

    new_body = _generate_draft_body(config, draft)
    store.update_draft(draft_id, body=new_body, status="pending", error=None)
    store.add_audit("regenerated", draft_id=draft_id, post_id=draft["post_id"])


def approve_draft(store: Store, draft_id: int, body: str | None = None) -> None:
    """Mark a draft as approved."""
    draft = store.get_draft(draft_id)
    if draft is None:
        raise ValueError(f"Draft not found: {draft_id}")
    if draft["status"] not in {"pending", "error"}:
        raise ValueError(f"Draft {draft_id} cannot be approved (status={draft['status']})")
    if body is not None:
        store.update_draft(draft_id, body=body)
        draft = store.get_draft(draft_id) or draft
    if not (draft.get("body") or "").strip():
        raise ValueError(f"Draft {draft_id} has an empty body")
    store.update_draft(draft_id, status="approved", error=None)
    store.add_audit("approved", draft_id=draft_id, post_id=draft["post_id"])
    logger.info("Approved draft %d", draft_id)


def reject_draft(store: Store, draft_id: int) -> None:
    """Mark a draft as rejected."""
    draft = store.get_draft(draft_id)
    if draft is None:
        raise ValueError(f"Draft not found: {draft_id}")
    if draft["status"] not in {"pending", "error", "approved", "scheduled"}:
        raise ValueError(f"Draft {draft_id} cannot be rejected (status={draft['status']})")
    store.update_draft(draft_id, status="rejected", run_at=None)
    store.add_audit("rejected", draft_id=draft_id, post_id=draft["post_id"])
    logger.info("Rejected draft %d", draft_id)


def edit_draft(store: Store, draft_id: int, body: str) -> None:
    """Save an edited draft body."""
    draft = store.get_draft(draft_id)
    if draft is None:
        raise ValueError(f"Draft not found: {draft_id}")
    store.update_draft(draft_id, body=body)
    store.add_audit("draft_edited", draft_id=draft_id, post_id=draft["post_id"])


def schedule_draft(store: Store, draft_id: int, run_at: datetime) -> None:
    """Schedule an approved draft for future posting."""
    draft = store.get_draft(draft_id)
    if draft is None:
        raise ValueError(f"Draft not found: {draft_id}")
    if draft["status"] not in {"pending", "approved"}:
        raise ValueError(f"Draft {draft_id} cannot be scheduled (status={draft['status']})")

    if draft["status"] == "pending":
        if not (draft.get("body") or "").strip():
            raise ValueError(f"Draft {draft_id} has an empty body")
        store.update_draft(draft_id, status="approved", error=None)

    run_at_iso = run_at.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    store.update_draft(draft_id, status="scheduled", run_at=run_at_iso)
    store.add_audit("scheduled", draft_id=draft_id, post_id=draft["post_id"], detail={"run_at": run_at_iso})
    logger.info("Scheduled draft %d for %s", draft_id, run_at_iso)


def cancel_schedule(store: Store, draft_id: int) -> None:
    """Cancel a scheduled draft, returning it to approved."""
    draft = store.get_draft(draft_id)
    if draft is None:
        raise ValueError(f"Draft not found: {draft_id}")
    store.cancel_schedule(draft_id)
    store.add_audit("unscheduled", draft_id=draft_id, post_id=draft["post_id"])
    logger.info("Unscheduled draft %d", draft_id)


def _rate_limit_allows(config: AppConfig, store: Store, account_name: str) -> tuple[bool, str | None]:
    posted_today = store.count_posted_today(account_name)
    if posted_today >= config.rate_limits.daily_cap:
        return False, f"Daily cap reached ({posted_today}/{config.rate_limits.daily_cap})"

    last_posted = store.get_last_posted_at(account_name)
    if last_posted is not None:
        elapsed = (datetime.now(timezone.utc) - last_posted).total_seconds()
        remaining = config.rate_limits.min_interval_seconds - elapsed
        if remaining > 0:
            return False, f"Minimum interval not met ({int(remaining)}s remaining)"

    return True, None


def _is_due(draft: dict[str, Any], now: datetime | None = None) -> bool:
    if draft["status"] != "scheduled":
        return False
    run_at = draft.get("run_at")
    if not run_at:
        return False
    now = now or datetime.now(timezone.utc)
    dt = datetime.fromisoformat(run_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt <= now


def _post_draft(config: AppConfig, store: Store, draft: dict[str, Any]) -> dict[str, Any]:
    accounts_by_name = {account.name: account for account in config.accounts}
    account_name = draft["account_name"]
    account = accounts_by_name.get(account_name)
    if account is None:
        message = f"Unknown account: {account_name}"
        store.update_draft(draft["id"], status="error", error=message)
        store.add_audit("post_error", draft_id=draft["id"], post_id=draft["post_id"], detail={"error": message})
        return {"draft_id": draft["id"], "ok": False, "error": message}

    allowed, reason = _rate_limit_allows(config, store, account_name)
    if not allowed:
        logger.info("Skipping draft %d: %s", draft["id"], reason)
        return {"draft_id": draft["id"], "ok": False, "skipped": True, "error": reason}

    reddit = reddit_client.get_reddit(account)
    try:
        permalink = reddit_client.post_comment(reddit, draft["post_id"], draft["body"])
        store.update_draft(draft["id"], status="posted", permalink=permalink, error=None, run_at=None)
        store.add_audit("posted", draft_id=draft["id"], post_id=draft["post_id"], detail={"permalink": permalink})
        logger.info("Posted draft %d -> %s", draft["id"], permalink)
        return {"draft_id": draft["id"], "ok": True, "permalink": permalink}
    except Exception as exc:
        logger.exception("Failed to post draft %d: %s", draft["id"], exc)
        store.update_draft(draft["id"], status="error", error=str(exc))
        store.add_audit("post_error", draft_id=draft["id"], post_id=draft["post_id"], detail={"error": str(exc)})
        return {"draft_id": draft["id"], "ok": False, "error": str(exc)}


def post_approved(
    config: AppConfig,
    store: Store,
    draft_id: int | None = None,
) -> list[dict[str, Any]]:
    """Post approved drafts to Reddit, enforcing rate limits."""
    store.ensure_schema()
    now = datetime.now(timezone.utc)

    if draft_id is not None:
        draft = store.get_draft(draft_id)
        if draft is None:
            raise ValueError(f"Draft not found: {draft_id}")
        if draft["status"] == "approved":
            drafts = [draft]
        elif draft["status"] == "scheduled" and _is_due(draft, now):
            drafts = [draft]
        else:
            logger.warning("Draft %d is not postable (status=%s)", draft_id, draft["status"])
            drafts = []
    else:
        drafts = store.list_drafts(status="approved")

    results: list[dict[str, Any]] = []
    for draft in drafts:
        results.append(_post_draft(config, store, draft))
    return results


def post_due_scheduled(config: AppConfig, store: Store) -> list[dict[str, Any]]:
    """Post scheduled drafts whose run_at has passed."""
    store.ensure_schema()
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    due = store.list_scheduled_due(now_iso)
    results: list[dict[str, Any]] = []

    for draft in due:
        results.append(_post_draft(config, store, draft))

    posted = sum(1 for item in results if item.get("ok"))
    if due:
        store.add_audit("posted_scheduled", detail={"due": len(due), "posted": posted})
    return results


def run_once(config: AppConfig, store: Store) -> dict[str, int]:
    """Run one worker cycle: fetch, draft eligible posts, post due schedules."""
    fetched = fetch_and_store(config, store)
    drafted = draft_pending(config, store)
    scheduled_results = post_due_scheduled(config, store)
    posted = sum(1 for item in scheduled_results if item.get("ok"))
    return {"fetched": fetched, "drafted": drafted, "posted": posted}


def rescore_posts(store: Store, config: AppConfig) -> int:
    """Re-score all posts (useful after config keyword changes)."""
    posts = store.list_posts()
    apply_scores(store, posts, config.discovery)
    return len(posts)
