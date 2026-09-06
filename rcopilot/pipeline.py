"""Orchestration pipeline: fetch, draft, approve, schedule, and post comments."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from rcopilot import reddit_client
from rcopilot.config import AppConfig, Account, save_config
from rcopilot.llm import (
    fallback_search_queries,
    finalize_comment,
    generate_comment,
    generate_search_queries,
    generate_submission,
    iter_comment_deltas,
)
from rcopilot.projects import persist_queries_to_project
from rcopilot.scoring import apply_scores
from rcopilot.store import DEFAULT_PROJECT_ID, Store

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


def _project_id(config: AppConfig) -> str:
    return (config.active_project_id or "").strip() or DEFAULT_PROJECT_ID


def _voice_kwargs(config: AppConfig) -> dict[str, str]:
    return {
        "product": config.voice.product,
        "tone": config.voice.tone,
        "persona": config.voice.persona,
        "avoid": config.voice.avoid,
        "goals": "; ".join(config.goals) if config.goals else "",
    }


def _queries_fingerprint(config: AppConfig) -> str:
    payload = {
        "product": config.voice.product,
        "persona": config.voice.persona,
        "keywords": config.discovery.keywords,
        "subreddits": config.subreddits,
        "purpose": config.purpose,
        "goals": config.goals,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def ensure_search_queries(
    config: AppConfig,
    *,
    config_path: str | Path | None = None,
) -> list[str]:
    """Return cached LLM/fallback search queries, regenerating when voice or keywords change."""
    fingerprint = _queries_fingerprint(config)
    cached = [query.strip() for query in config.discovery.search_queries if query.strip()]
    if cached and config.discovery.queries_fingerprint == fingerprint:
        return cached

    queries: list[str] = []
    if config.llm.api_key:
        try:
            queries = generate_search_queries(
                config.llm,
                product=config.voice.product,
                keywords=config.discovery.keywords,
                subreddits=config.subreddits,
                persona=config.voice.persona,
                purpose=config.purpose,
                goals=config.goals,
            )
        except Exception:
            logger.exception("LLM search-query generation failed; using fallback queries")

    if not queries:
        queries = fallback_search_queries(config.voice.product, config.discovery.keywords)

    config.discovery.search_queries = queries
    config.discovery.queries_fingerprint = fingerprint
    if config_path:
        save_config(config_path, config)
        logger.info("Saved %d discovery search quer(y/ies) to %s", len(queries), config_path)
    return queries


def fetch_and_store(
    config: AppConfig,
    store: Store,
    *,
    config_path: str | Path | None = None,
) -> int:
    """Fetch posts from Reddit, persist, and score them. Returns count of new posts."""
    store.ensure_schema()
    if not config.subreddits:
        raise ValueError("No subreddits configured in config.yaml")
    account = _resolve_account(config, None)
    if not account.client_id:
        raise ValueError(
            "Missing REDDIT_CLIENT_ID. Create a Reddit web app and paste the client id in .env or onboarding."
        )
    if not account.refresh_token and not (account.username and account.password):
        raise ValueError("Reddit is not connected. Use Connect Reddit in onboarding or Settings.")
    reddit = reddit_client.get_reddit(account)
    project_id = _project_id(config)

    existing_ids = store.list_post_ids(project_id=project_id)

    queries = ensure_search_queries(config, config_path=config_path)
    persist_queries_to_project(store, config)
    fetched = reddit_client.fetch_posts(
        reddit,
        config.subreddits,
        config.listing,
        config.fetch_limit,
    )
    search_limit = min(10, max(5, config.fetch_limit))
    searched = reddit_client.search_posts(
        reddit,
        config.subreddits,
        queries,
        limit_per_query=search_limit,
    )

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for post in searched + fetched:
        if post["id"] in seen:
            continue
        seen.add(post["id"])
        merged.append(post)

    new_count = 0
    stored_posts: list[dict[str, Any]] = []
    for post in merged:
        is_new = post["id"] not in existing_ids
        store.upsert_post(**post, project_id=project_id)
        stored_posts.append(store.get_post(post["id"], project_id=project_id) or post)
        if is_new:
            existing_ids.add(post["id"])
            new_count += 1

    apply_scores(
        store,
        stored_posts,
        config.discovery,
        product=config.voice.product,
        project_id=project_id,
    )
    store.add_audit(
        "fetched",
        project_id=project_id,
        detail={
            "new_count": new_count,
            "total": len(stored_posts),
            "search_queries": queries,
        },
    )
    logger.info(
        "Stored %d new post(s), scored %d (search=%d listing=%d queries=%d)",
        new_count,
        len(stored_posts),
        len(searched),
        len(fetched),
        len(queries),
    )
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
    posts = store.list_posts(
        project_id=_project_id(config),
        undrafted=True,
        skipped=False,
        min_score=config.discovery.min_score,
    )
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
            draft_id = store.create_draft(
                post["id"], account.name, body, status="pending", project_id=_project_id(config)
            )
            store.add_audit("drafted", draft_id=draft_id, post_id=post["id"], project_id=_project_id(config))
            created += 1
            logger.info("Drafted comment for post %s", post["id"])
        except Exception as exc:
            logger.exception("LLM draft failed for post %s: %s", post["id"], exc)
            draft_id = store.create_draft(
                post["id"], account.name, "", status="error", project_id=_project_id(config)
            )
            store.update_draft(draft_id, error=str(exc))
            store.add_audit(
                "draft_error",
                draft_id=draft_id,
                post_id=post["id"],
                project_id=_project_id(config),
                detail={"error": str(exc)},
            )

    logger.info("Created %d draft(s)", created)
    return created


def draft_one(config: AppConfig, store: Store, post_id: str, account_name: str | None = None) -> int:
    """Generate an LLM draft for a single post (CLI / legacy). Prefer queue_post + stream in the UI."""
    store.ensure_schema()
    project_id = _project_id(config)
    post = store.get_post(post_id, project_id=project_id)
    if post is None:
        raise ValueError(f"Post not found: {post_id}")
    if post.get("skipped"):
        raise ValueError(f"Post {post_id} is skipped")
    if store.draft_exists_for_post(post_id, project_id=project_id):
        raise ValueError(f"Post {post_id} already has a draft")

    account = _resolve_account(config, account_name)
    if not config.llm.api_key:
        raise ValueError("Missing LLM_API_KEY in .env (or llm.api_key in config)")

    try:
        body = _generate_draft_body(config, post)
        draft_id = store.create_draft(post_id, account.name, body, status="pending", project_id=project_id)
        store.add_audit("drafted", draft_id=draft_id, post_id=post_id, project_id=project_id)
        return draft_id
    except Exception as exc:
        draft_id = store.create_draft(post_id, account.name, "", status="error", project_id=project_id)
        store.update_draft(draft_id, error=str(exc))
        store.add_audit(
            "draft_error",
            draft_id=draft_id,
            post_id=post_id,
            project_id=project_id,
            detail={"error": str(exc)},
        )
        raise


def queue_post(config: AppConfig, store: Store, post_id: str, account_name: str | None = None) -> int:
    """Add a post to the review queue without generating a reply yet."""
    store.ensure_schema()
    project_id = _project_id(config)
    post = store.get_post(post_id, project_id=project_id)
    if post is None:
        raise ValueError(f"Post not found: {post_id}")
    if post.get("skipped"):
        raise ValueError(f"Post {post_id} is skipped")
    if store.draft_exists_for_post(post_id, project_id=project_id):
        raise ValueError(f"Post {post_id} is already in the review queue")

    account = _resolve_account(config, account_name)
    draft_id = store.create_draft(post_id, account.name, "", status="pending", project_id=project_id)
    store.add_audit("queued", draft_id=draft_id, post_id=post_id, project_id=project_id)
    logger.info("Queued post %s as draft %d", post_id, draft_id)
    return draft_id


def iter_draft_deltas(config: AppConfig, store: Store, draft_id: int) -> Iterator[str]:
    """Stream LLM deltas for a queued draft. Caller must finalize and save."""
    draft = store.get_draft(draft_id)
    if draft is None:
        raise ValueError(f"Draft not found: {draft_id}")
    if draft["status"] in {"posted", "rejected"}:
        raise ValueError(f"Draft {draft_id} cannot be generated (status={draft['status']})")
    if not config.llm.api_key:
        raise ValueError("Missing LLM_API_KEY in .env (or llm.api_key in config)")

    yield from iter_comment_deltas(
        config.llm,
        draft["title"],
        draft["selftext"],
        draft.get("top_comments") or [],
        config.prompt_template,
        **_voice_kwargs(config),
    )


def finish_draft_stream(
    config: AppConfig,
    store: Store,
    draft_id: int,
    raw_text: str,
    *,
    regenerated: bool = False,
) -> str:
    """Lint streamed text, save onto the draft, and return the cleaned body."""
    draft = store.get_draft(draft_id)
    if draft is None:
        raise ValueError(f"Draft not found: {draft_id}")
    body = finalize_comment(raw_text, product=config.voice.product)
    store.update_draft(draft_id, body=body, status="pending", error=None)
    store.add_audit(
        "regenerated" if regenerated else "drafted",
        draft_id=draft_id,
        post_id=draft["post_id"],
    )
    return body


def skip_post(store: Store, post_id: str, *, project_id: str = DEFAULT_PROJECT_ID) -> None:
    """Mark a post as skipped."""
    post = store.get_post(post_id, project_id=project_id)
    if post is None:
        raise ValueError(f"Post not found: {post_id}")
    store.update_post(post_id, project_id=project_id, skipped=1)
    store.add_audit("skipped", post_id=post_id, project_id=project_id)


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


def edit_draft(
    store: Store,
    draft_id: int,
    body: str,
    *,
    title: str | None = None,
) -> None:
    """Save an edited draft body (and title for submissions)."""
    draft = store.get_draft(draft_id)
    if draft is None:
        raise ValueError(f"Draft not found: {draft_id}")
    fields: dict[str, Any] = {"body": body}
    if title is not None and (draft.get("kind") or "comment") == "submission":
        fields["title"] = title.strip()
    store.update_draft(draft_id, **fields)
    store.add_audit("draft_edited", draft_id=draft_id, post_id=draft.get("post_id"))


def create_submission_draft(
    config: AppConfig,
    store: Store,
    *,
    subreddit: str,
    title: str,
    body: str,
    account_name: str | None = None,
) -> int:
    """Create a pending original self-post draft."""
    store.ensure_schema()
    account = _resolve_account(config, account_name)
    cleaned_sub = subreddit.strip().lstrip("r/")
    cleaned_title = title.strip()
    cleaned_body = body.strip()
    if not cleaned_sub:
        raise ValueError("Subreddit is required")
    if not cleaned_title:
        raise ValueError("Title is required")
    if not cleaned_body:
        raise ValueError("Post body is required")
    draft_id = store.create_submission_draft(
        account_name=account.name,
        subreddit=cleaned_sub,
        title=cleaned_title,
        body=cleaned_body,
        project_id=_project_id(config),
    )
    store.add_audit(
        "submission_created",
        draft_id=draft_id,
        project_id=_project_id(config),
        detail={"subreddit": cleaned_sub, "title": cleaned_title},
    )
    return draft_id


def generate_submission_ideas(
    config: AppConfig,
    store: Store,
    *,
    count: int = 5,
    subreddits: list[str] | None = None,
    account_name: str | None = None,
) -> list[int]:
    """Ask the LLM for original self-posts across configured subreddits."""
    store.ensure_schema()
    if not config.llm.api_key:
        raise ValueError("Missing LLM_API_KEY in .env (or llm.api_key in config)")
    if count < 1 or count > 20:
        raise ValueError("count must be between 1 and 20")

    account = _resolve_account(config, account_name)
    pool = [s.strip().lstrip("r/") for s in (subreddits or config.subreddits) if s.strip()]
    if not pool:
        raise ValueError("No subreddits configured — add some in Settings")

    created_ids: list[int] = []
    for index in range(count):
        subreddit = pool[index % len(pool)]
        try:
            title, body = generate_submission(
                config.llm,
                subreddit=subreddit,
                **_voice_kwargs(config),
            )
            draft_id = store.create_submission_draft(
                account_name=account.name,
                subreddit=subreddit,
                title=title,
                body=body,
                project_id=_project_id(config),
            )
            store.add_audit(
                "submission_generated",
                draft_id=draft_id,
                project_id=_project_id(config),
                detail={"subreddit": subreddit, "title": title},
            )
            created_ids.append(draft_id)
        except Exception as exc:
            logger.warning("Failed to generate submission for r/%s: %s", subreddit, exc)
            store.add_audit(
                "submission_generate_error",
                detail={"subreddit": subreddit, "error": str(exc)},
            )
    return created_ids


def schedule_draft(store: Store, draft_id: int, run_at: datetime) -> None:
    """Schedule a draft with a reply/post body for future posting."""
    draft = store.get_draft(draft_id)
    if draft is None:
        raise ValueError(f"Draft not found: {draft_id}")
    if draft["status"] not in {"pending", "approved"}:
        raise ValueError(f"Draft {draft_id} cannot be scheduled (status={draft['status']})")
    if not (draft.get("body") or "").strip():
        raise ValueError(f"Draft {draft_id} needs a body before scheduling")
    kind = draft.get("kind") or "comment"
    if kind == "submission":
        if not (draft.get("title") or "").strip():
            raise ValueError(f"Draft {draft_id} needs a title before scheduling")
        if not (draft.get("target_subreddit") or draft.get("subreddit") or "").strip():
            raise ValueError(f"Draft {draft_id} needs a target subreddit before scheduling")

    run_at_iso = run_at.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    store.update_draft(draft_id, status="scheduled", run_at=run_at_iso)
    store.add_audit(
        "scheduled",
        draft_id=draft_id,
        post_id=draft.get("post_id"),
        detail={"run_at": run_at_iso, "kind": kind},
    )
    logger.info("Scheduled draft %d for %s", draft_id, run_at_iso)


def cancel_schedule(store: Store, draft_id: int) -> None:
    """Cancel a scheduled draft, returning it to pending."""
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
    kind = draft.get("kind") or "comment"
    try:
        if kind == "submission":
            subreddit = (draft.get("target_subreddit") or draft.get("subreddit") or "").strip()
            title = (draft.get("title") or "").strip()
            permalink, submission_id = reddit_client.post_submission(
                reddit, subreddit, title, draft["body"]
            )
            store.update_draft(
                draft["id"],
                status="posted",
                permalink=permalink,
                submission_id=submission_id,
                error=None,
                run_at=None,
            )
            store.add_audit(
                "posted",
                draft_id=draft["id"],
                detail={
                    "permalink": permalink,
                    "submission_id": submission_id,
                    "kind": "submission",
                    "subreddit": subreddit,
                },
            )
            logger.info("Posted submission draft %d -> %s", draft["id"], permalink)
            return {
                "draft_id": draft["id"],
                "ok": True,
                "permalink": permalink,
                "submission_id": submission_id,
            }

        permalink, comment_id = reddit_client.post_comment(
            reddit, draft["post_id"], draft["body"]
        )
        store.update_draft(
            draft["id"],
            status="posted",
            permalink=permalink,
            comment_id=comment_id,
            error=None,
            run_at=None,
        )
        store.add_audit(
            "posted",
            draft_id=draft["id"],
            post_id=draft["post_id"],
            detail={"permalink": permalink, "comment_id": comment_id, "kind": "comment"},
        )
        logger.info("Posted draft %d -> %s", draft["id"], permalink)
        return {
            "draft_id": draft["id"],
            "ok": True,
            "permalink": permalink,
            "comment_id": comment_id,
        }
    except Exception as exc:
        logger.exception("Failed to post draft %d: %s", draft["id"], exc)
        store.update_draft(draft["id"], status="error", error=str(exc))
        store.add_audit(
            "post_error",
            draft_id=draft["id"],
            post_id=draft.get("post_id"),
            detail={"error": str(exc), "kind": kind},
        )
        return {"draft_id": draft["id"], "ok": False, "error": str(exc)}


def poll_outcomes(config: AppConfig, store: Store, *, limit: int = 20) -> int:
    """Refresh score / replies / removed for posted comments. Returns polls attempted."""
    store.ensure_schema()
    drafts = store.list_posted_for_outcomes(limit=limit)
    if not drafts:
        return 0

    accounts_by_name = {account.name: account for account in config.accounts}
    polled = 0

    for draft in drafts:
        account = accounts_by_name.get(draft["account_name"])
        if account is None:
            logger.warning(
                "Skipping outcome poll for draft %s: unknown account %s",
                draft["id"],
                draft["account_name"],
            )
            continue

        comment_id = draft.get("comment_id") or reddit_client.comment_id_from_permalink(
            draft.get("permalink")
        )
        if not comment_id:
            logger.debug("Draft %s has no comment_id/permalink for outcome poll", draft["id"])
            continue

        try:
            reddit = reddit_client.get_reddit(account)
            outcome = reddit_client.fetch_comment_outcome(reddit, comment_id)
        except Exception as exc:
            logger.warning("Outcome poll failed for draft %s: %s", draft["id"], exc)
            continue

        new_removed = bool(outcome.get("removed"))
        old_score = draft.get("outcome_score")
        old_replies = draft.get("outcome_replies")
        old_removed = bool(draft.get("outcome_removed"))
        new_score = outcome.get("score")
        new_replies = int(outcome.get("replies") or 0)

        changed = (
            old_score != new_score
            or old_replies != new_replies
            or old_removed != new_removed
        )

        fields: dict[str, Any] = {
            "comment_id": comment_id,
            "outcome_score": new_score,
            "outcome_replies": new_replies,
            "outcome_removed": 1 if new_removed else 0,
            "outcomes_polled_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        if outcome.get("permalink") and not draft.get("permalink"):
            fields["permalink"] = outcome["permalink"]

        store.update_draft(draft["id"], **fields)
        polled += 1

        if changed:
            store.add_audit(
                "outcome_updated",
                draft_id=draft["id"],
                post_id=draft["post_id"],
                detail={
                    "score": new_score,
                    "replies": new_replies,
                    "removed": new_removed,
                },
            )

    return polled


def post_approved(
    config: AppConfig,
    store: Store,
    draft_id: int | None = None,
) -> list[dict[str, Any]]:
    """Post ready drafts to Reddit (pending/approved with a body, or due schedules)."""
    store.ensure_schema()
    now = datetime.now(timezone.utc)

    def _postable(draft: dict[str, Any]) -> bool:
        if draft["status"] == "scheduled":
            return _is_due(draft, now)
        if draft["status"] in {"pending", "approved"}:
            return bool((draft.get("body") or "").strip())
        return False

    if draft_id is not None:
        draft = store.get_draft(draft_id)
        if draft is None:
            raise ValueError(f"Draft not found: {draft_id}")
        if _postable(draft):
            drafts = [draft]
        else:
            logger.warning("Draft %d is not postable (status=%s)", draft_id, draft["status"])
            drafts = []
    else:
        drafts = [
            item
            for item in store.list_drafts(status="pending") + store.list_drafts(status="approved")
            if (item.get("body") or "").strip()
        ]

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


def run_once(
    config: AppConfig,
    store: Store,
    *,
    config_path: str | Path | None = None,
) -> dict[str, int]:
    """Run one worker cycle: fetch, draft eligible posts, post due schedules, poll outcomes."""
    from rcopilot.projects import apply_project_to_config, seed_projects_from_config

    store.ensure_schema()
    seed_projects_from_config(store, config)
    original_id = _project_id(config)
    projects = [item for item in store.list_projects() if item.get("subreddits")]
    fetched = 0
    drafted = 0
    if projects:
        for project in projects:
            apply_project_to_config(config, project)
            try:
                fetched += fetch_and_store(config, store, config_path=config_path)
            except ValueError as exc:
                logger.warning("Fetch skipped for project %s: %s", project.get("id"), exc)
            try:
                drafted += draft_pending(config, store)
            except ValueError as exc:
                logger.warning("Draft skipped for project %s: %s", project.get("id"), exc)
        original = store.get_project(original_id)
        if original:
            apply_project_to_config(config, original)
            if config_path:
                save_config(config_path, config)
    else:
        fetched = fetch_and_store(config, store, config_path=config_path)
        drafted = draft_pending(config, store)
    scheduled_results = post_due_scheduled(config, store)
    posted = sum(1 for item in scheduled_results if item.get("ok"))
    outcomes = poll_outcomes(config, store)
    return {
        "fetched": fetched,
        "drafted": drafted,
        "posted": posted,
        "outcomes": outcomes,
    }


def rescore_posts(store: Store, config: AppConfig) -> int:
    """Re-score all posts (useful after config keyword changes)."""
    project_id = _project_id(config)
    posts = store.list_posts(project_id=project_id)
    apply_scores(
        store,
        posts,
        config.discovery,
        product=config.voice.product,
        project_id=project_id,
    )
    return len(posts)
