"""FastAPI JSON API for Reddit Copilot."""

from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

from rcopilot import __version__
from rcopilot.config import (
    AppConfig,
    DiscoveryConfig,
    LLMConfig,
    RateLimits,
    VoiceConfig,
    WorkerConfig,
    env_secret_key,
    format_text_list,
    load_config,
    sanitize_config,
    save_config,
    write_env_secrets,
)
from rcopilot import reddit_client
from rcopilot.draft_lint import lint_draft
from rcopilot.interview import (
    attach_user_turn,
    complete_workspace,
    iter_interview_reply,
    opening_message,
    split_ready_marker,
    visible_interview_stream,
)
from rcopilot.pipeline import (
    approve_draft,
    cancel_schedule,
    create_submission_draft,
    draft_one,
    draft_pending,
    edit_draft,
    fetch_and_store,
    finish_draft_stream,
    generate_draft_variants,
    generate_submission_ideas,
    iter_draft_deltas,
    iter_fetch_and_store,
    poll_outcomes,
    post_approved,
    queue_post,
    regenerate_draft,
    reject_draft,
    run_once,
    schedule_draft,
    select_draft_variant,
    skip_post,
)
from rcopilot.store import DEFAULT_PROJECT_ID, PROJECT_PURPOSES, Store
from rcopilot.projects import (
    apply_project_to_config,
    has_finished_project,
    persist_config_to_project,
    resolve_active_project,
    seed_projects_from_config,
    serialize_project,
    serialize_project_summary,
)
from rcopilot.best_times import (
    get_cached_hours,
    set_cached_hours,
    suggest_best_times,
)

logger = logging.getLogger(__name__)

DRAFT_API_FIELDS = (
    "id",
    "post_id",
    "account_name",
    "body",
    "status",
    "error",
    "permalink",
    "created_at",
    "updated_at",
    "run_at",
    "subreddit",
    "title",
    "selftext",
    "url",
    "post_permalink",
    "created_utc",
    "top_comments",
    "relevance_score",
    "score_reasons",
    "comment_id",
    "outcome_score",
    "outcome_replies",
    "outcome_removed",
    "outcomes_polled_at",
    "kind",
    "target_subreddit",
    "submission_id",
    "variants",
)


class DraftEditBody(BaseModel):
    body: str
    title: str | None = None


class ApproveBody(BaseModel):
    body: str | None = None


class SelectVariantBody(BaseModel):
    variant_id: str


class ScheduleBody(BaseModel):
    run_at: str


class SubmissionCreateBody(BaseModel):
    subreddit: str
    title: str
    body: str
    account_name: str | None = None


class GenerateSubmissionsBody(BaseModel):
    count: int = 5
    subreddits: list[str] | None = None
    account_name: str | None = None


class SuggestSubredditsBody(BaseModel):
    product: str | None = None
    tone: str | None = None
    persona: str | None = None
    count: int = 12
    purpose: str | None = None
    goals: list[str] | None = None


class ConfigUpdateBody(BaseModel):
    subreddits: list[str] | None = None
    listing: str | None = None
    fetch_limit: int | None = None
    voice: dict[str, str] | None = None
    discovery: dict[str, Any] | None = None
    rate_limits: dict[str, int] | None = None
    worker: dict[str, int] | None = None
    accounts: list[dict[str, str]] | None = None
    llm: dict[str, str] | None = None
    prompt_template: str | None = None
    onboarding_complete: bool | None = None
    onboarding_step: int | None = None
    active_project_id: str | None = None
    purpose: str | None = None
    goals: list[str] | None = None


class ProjectCreateBody(BaseModel):
    purpose: str
    name: str | None = None


class ProjectUpdateBody(BaseModel):
    name: str | None = None
    briefing: str | None = None
    goals: list[str] | None = None
    tone: str | None = None
    persona: str | None = None
    avoid: str | None = None
    subreddits: list[str] | None = None
    keywords: list[str] | None = None
    complete: bool | None = None
    setup_step: int | None = None


class ActiveProjectBody(BaseModel):
    id: str


class InterviewBody(BaseModel):
    message: str


class SecretsBody(BaseModel):
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    llm_api_key: str | None = None
    account_name: str | None = None


class OAuthStartBody(BaseModel):
    account_name: str | None = None
    next: str | None = None


def _serialize_draft(draft: dict[str, Any], *, product: str = "") -> dict[str, Any]:
    data = {key: draft.get(key) for key in DRAFT_API_FIELDS}
    lint = lint_draft(str(draft.get("body") or ""), product=product)
    data["lint_warnings"] = [
        {"code": issue.code, "message": issue.message} for issue in lint.issues
    ]
    return data


def _serialize_post(post: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": post["id"],
        "subreddit": post["subreddit"],
        "title": post["title"],
        "selftext": post["selftext"],
        "url": post["url"],
        "permalink": post["permalink"],
        "created_utc": post["created_utc"],
        "top_comments": post.get("top_comments") or [],
        "relevance_score": post.get("relevance_score", 0),
        "score_reasons": post.get("score_reasons") or [],
        "keywords_matched": post.get("keywords_matched") or [],
        "intent_labels": post.get("intent_labels") or [],
        "skipped": post.get("skipped", False),
    }


def create_app(config_path: str | None = None) -> FastAPI:
    resolved_path = Path(config_path or "config.yaml")
    app = FastAPI(title="Reddit Copilot API", version=__version__)

    allow_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    extra_origins = os.environ.get("FRONTEND_ORIGINS", "")
    allow_origins.extend(origin.strip() for origin in extra_origins.split(",") if origin.strip())

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.oauth_pending = {}

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    @app.exception_handler(Exception)
    async def generic_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error: %s", exc)
        return JSONResponse(status_code=500, content={"error": str(exc)})

    def get_config() -> AppConfig:
        if not resolved_path.exists():
            raise HTTPException(status_code=400, detail=f"Config not found: {resolved_path}")
        config = load_config(resolved_path)
        store = Store(config.db_path)
        store.ensure_schema()
        seed_projects_from_config(store, config)
        project = resolve_active_project(store, config)
        if project:
            apply_project_to_config(config, project)
        return config

    def get_store(config: AppConfig) -> Store:
        store = Store(config.db_path)
        store.ensure_schema()
        seed_projects_from_config(store, config)
        return store

    def _pid(config: AppConfig) -> str:
        return (config.active_project_id or "").strip() or DEFAULT_PROJECT_ID

    def _public_config(config: AppConfig) -> dict[str, Any]:
        store = get_store(config)
        data = sanitize_config(config)
        data["projects"] = [serialize_project_summary(item) for item in store.list_projects()]
        data["onboarding_complete"] = bool(
            config.onboarding_complete and has_finished_project(store)
        )
        setup = store.find_setup_project()
        data["setup_project"] = serialize_project(setup) if setup else None
        return data

    @app.on_event("startup")
    def on_startup() -> None:
        if resolved_path.exists():
            config = load_config(resolved_path)
            store = Store(config.db_path)
            store.ensure_schema()

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        counts = store.count_drafts_by_status(project_id=_pid(config))
        return {
            "counts": {
                "pending": counts.get("pending", 0),
                "approved": counts.get("approved", 0),
                "scheduled": counts.get("scheduled", 0),
                "posted": counts.get("posted", 0),
                "rejected": counts.get("rejected", 0),
                "error": counts.get("error", 0),
            },
            "config_loaded": True,
        }

    @app.get("/api/drafts")
    def list_drafts(
        status: str = Query(default="pending"),
    ) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        filter_status = None if status == "all" else status
        drafts = store.list_drafts(status=filter_status, project_id=_pid(config))
        return {"drafts": [_serialize_draft(d, product=config.voice.product) for d in drafts]}

    @app.get("/api/drafts/{draft_id}")
    def get_draft(draft_id: int) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        draft = store.get_draft(draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail=f"Draft not found: {draft_id}")
        return _serialize_draft(draft, product=config.voice.product)

    @app.patch("/api/drafts/{draft_id}")
    def patch_draft(draft_id: int, body: DraftEditBody) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        try:
            edit_draft(store, draft_id, body.body, title=body.title)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        draft = store.get_draft(draft_id)
        return _serialize_draft(draft, product=config.voice.product)  # type: ignore[arg-type]

    @app.post("/api/drafts/{draft_id}/approve")
    def approve(draft_id: int, body: ApproveBody | None = None) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        draft = store.get_draft(draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail=f"Draft not found: {draft_id}")
        try:
            approve_draft(store, draft_id, body=body.body if body else None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        draft = store.get_draft(draft_id)
        return _serialize_draft(draft, product=config.voice.product)  # type: ignore[arg-type]

    @app.post("/api/drafts/{draft_id}/reject")
    def reject(draft_id: int) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        try:
            reject_draft(store, draft_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        draft = store.get_draft(draft_id)
        return _serialize_draft(draft, product=config.voice.product)  # type: ignore[arg-type]

    @app.post("/api/drafts/{draft_id}/regenerate")
    def regenerate(draft_id: int) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        try:
            regenerate_draft(config, store, draft_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        draft = store.get_draft(draft_id)
        return _serialize_draft(draft, product=config.voice.product)  # type: ignore[arg-type]

    @app.post("/api/drafts/{draft_id}/variants")
    def generate_variants(draft_id: int) -> dict[str, Any]:
        """Generate 2–3 reply angles for a queued comment. Nothing is selected until pick."""
        config = get_config()
        store = get_store(config)
        try:
            generate_draft_variants(config, store, draft_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        draft = store.get_draft(draft_id)
        return _serialize_draft(draft, product=config.voice.product)  # type: ignore[arg-type]

    @app.post("/api/drafts/{draft_id}/select-variant")
    def select_variant(draft_id: int, body: SelectVariantBody) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        try:
            select_draft_variant(store, draft_id, body.variant_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        draft = store.get_draft(draft_id)
        return _serialize_draft(draft, product=config.voice.product)  # type: ignore[arg-type]

    @app.post("/api/drafts/{draft_id}/generate")
    def generate_stream(draft_id: int) -> StreamingResponse:
        """Stream an LLM reply into a queued draft (SSE)."""
        config = get_config()
        store = get_store(config)
        draft = store.get_draft(draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail=f"Draft not found: {draft_id}")
        regenerated = bool((draft.get("body") or "").strip())

        def event_stream() -> Iterator[str]:
            parts: list[str] = []
            try:
                for delta in iter_draft_deltas(config, store, draft_id):
                    parts.append(delta)
                    yield f"data: {json.dumps({'delta': delta})}\n\n"
                body = finish_draft_stream(
                    config,
                    store,
                    draft_id,
                    "".join(parts),
                    regenerated=regenerated,
                )
                payload = _serialize_draft(
                    store.get_draft(draft_id) or {"body": body},
                    product=config.voice.product,
                )
                payload["body"] = body
                yield f"data: {json.dumps({'done': True, 'draft': payload})}\n\n"
            except Exception as exc:
                logger.exception("Streaming draft failed for %s: %s", draft_id, exc)
                try:
                    store.update_draft(draft_id, status="error", error=str(exc))
                except Exception:
                    pass
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/drafts/{draft_id}/post")
    def post_draft(draft_id: int) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        try:
            results = post_approved(config, store, draft_id=draft_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if not results:
            raise HTTPException(
                status_code=400,
                detail="Draft needs a reply body before posting, or it is not due yet",
            )
        result = results[0]
        if not result.get("ok"):
            if result.get("skipped"):
                raise HTTPException(status_code=400, detail=result.get("error", "Rate limited"))
            raise HTTPException(status_code=400, detail=result.get("error", "Post failed"))
        draft = store.get_draft(draft_id)
        return {"result": result, "draft": _serialize_draft(draft, product=config.voice.product)}  # type: ignore[arg-type]

    @app.post("/api/drafts/{draft_id}/schedule")
    def schedule(draft_id: int, body: ScheduleBody) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        try:
            run_at = datetime.fromisoformat(body.run_at)
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=timezone.utc)
            schedule_draft(store, draft_id, run_at)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        draft = store.get_draft(draft_id)
        return _serialize_draft(draft, product=config.voice.product)  # type: ignore[arg-type]

    @app.post("/api/drafts/{draft_id}/unschedule")
    def unschedule(draft_id: int) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        try:
            cancel_schedule(store, draft_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        draft = store.get_draft(draft_id)
        return _serialize_draft(draft, product=config.voice.product)  # type: ignore[arg-type]

    @app.get("/api/posts")
    def list_posts(
        undrafted: bool = Query(default=False),
        skipped: bool | None = Query(default=None),
        label: str | None = Query(default=None),
    ) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        posts = store.list_posts(
            project_id=_pid(config),
            undrafted=undrafted if undrafted else None,
            skipped=skipped,
            min_score=config.discovery.min_score if undrafted else None,
        )
        if label:
            wanted = {item.strip() for item in label.split(",") if item.strip()}
            if wanted:
                posts = [
                    post
                    for post in posts
                    if wanted.intersection(post.get("intent_labels") or [])
                ]
        return {"posts": [_serialize_post(p) for p in posts]}

    @app.post("/api/posts/{post_id}/queue")
    def queue_post_route(post_id: str) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        try:
            draft_id = queue_post(config, store, post_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        draft = store.get_draft(draft_id)
        return _serialize_draft(draft, product=config.voice.product)  # type: ignore[arg-type]

    @app.post("/api/posts/{post_id}/draft")
    def draft_post(post_id: str) -> dict[str, Any]:
        """Legacy: generate a full draft immediately. Prefer /queue + /generate."""
        config = get_config()
        store = get_store(config)
        try:
            draft_id = draft_one(config, store, post_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        draft = store.get_draft(draft_id)
        return _serialize_draft(draft, product=config.voice.product)  # type: ignore[arg-type]

    @app.post("/api/posts/{post_id}/skip")
    def skip(post_id: str) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        try:
            skip_post(store, post_id, project_id=_pid(config))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        post = store.get_post(post_id, project_id=_pid(config))
        return _serialize_post(post)  # type: ignore[arg-type]

    @app.post("/api/actions/fetch")
    def action_fetch(request: Request) -> Any:
        config = get_config()
        store = get_store(config)
        accept = (request.headers.get("accept") or "").lower()
        if "text/event-stream" in accept:

            def event_stream() -> Iterator[str]:
                # SSE comment + started event so proxies flush before Reddit I/O.
                yield ": " + (" " * 2048) + "\n\n"
                yield f"data: {json.dumps({'type': 'started'})}\n\n"
                try:
                    for event in iter_fetch_and_store(
                        config, store, config_path=resolved_path
                    ):
                        payload = dict(event)
                        if payload.get("type") == "post" and payload.get("post"):
                            payload["post"] = _serialize_post(payload["post"])
                        yield f"data: {json.dumps(payload)}\n\n"
                except ValueError as exc:
                    yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
                except Exception as exc:
                    logger.exception("Streaming fetch failed: %s", exc)
                    yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"

            return StreamingResponse(
                event_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        try:
            fetched = fetch_and_store(config, store, config_path=resolved_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"fetched": fetched}

    @app.post("/api/actions/draft")
    def action_draft() -> dict[str, int]:
        config = get_config()
        store = get_store(config)
        try:
            drafted = draft_pending(config, store)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"drafted": drafted}

    @app.post("/api/actions/run-once")
    def action_run_once() -> dict[str, int]:
        config = get_config()
        store = get_store(config)
        try:
            return run_once(config, store, config_path=resolved_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/actions/poll-outcomes")
    def action_poll_outcomes() -> dict[str, int]:
        config = get_config()
        store = get_store(config)
        try:
            outcomes = poll_outcomes(config, store)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"outcomes": outcomes}

    @app.post("/api/submissions")
    def create_submission(body: SubmissionCreateBody) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        try:
            draft_id = create_submission_draft(
                config,
                store,
                subreddit=body.subreddit,
                title=body.title,
                body=body.body,
                account_name=body.account_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        draft = store.get_draft(draft_id)
        return _serialize_draft(draft, product=config.voice.product)  # type: ignore[arg-type]

    @app.post("/api/submissions/generate")
    def generate_submissions(body: GenerateSubmissionsBody) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        try:
            ids = generate_submission_ideas(
                config,
                store,
                count=body.count,
                subreddits=body.subreddits,
                account_name=body.account_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        drafts = [
            _serialize_draft(d, product=config.voice.product)
            for d in (store.get_draft(i) for i in ids)
            if d is not None
        ]
        return {"created": len(drafts), "drafts": drafts}

    @app.post("/api/subreddits/suggest")
    def suggest_subreddits_route(body: SuggestSubredditsBody) -> dict[str, Any]:
        from rcopilot.llm import suggest_subreddits

        config = get_config()
        if not config.llm.api_key:
            raise HTTPException(
                status_code=400,
                detail="Add an LLM API key first so we can suggest subreddits.",
            )
        product = (body.product if body.product is not None else config.voice.product) or ""
        tone = body.tone if body.tone is not None else config.voice.tone
        persona = body.persona if body.persona is not None else config.voice.persona
        try:
            names = suggest_subreddits(
                config.llm,
                product=product,
                tone=tone or "",
                persona=persona or "",
                count=body.count,
                purpose=body.purpose or config.purpose,
                goals=body.goals if body.goals is not None else config.goals,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("subreddit suggest failed: %s", exc)
            raise HTTPException(
                status_code=502,
                detail=f"Could not suggest subreddits: {exc}",
            ) from exc
        return {"subreddits": names}

    @app.get("/api/subreddits/icons")
    def subreddit_icons(
        names: str = Query(..., description="Comma-separated subreddit names"),
    ) -> dict[str, Any]:
        config = get_config()
        cleaned = [
            part.strip().lstrip("r/")
            for part in names.split(",")
            if part.strip()
        ]
        if not cleaned:
            return {"icons": {}}
        icons: dict[str, str | None] = {name: None for name in cleaned[:40]}
        try:
            account = config.accounts[0] if config.accounts else None
            if account is not None:
                reddit = reddit_client.get_reddit(account)
                fetched = reddit_client.fetch_subreddit_icons(reddit, cleaned)
                icons.update(fetched)
        except Exception as exc:
            logger.warning("subreddit icons fetch failed: %s", exc)
        return {"icons": icons}

    @app.get("/api/best-times")
    def best_times(
        subreddit: str = Query(...),
        tz_offset_minutes: int = Query(default=0),
        count: int = Query(default=3, ge=1, le=6),
    ) -> dict[str, Any]:
        config = get_config()
        cleaned = subreddit.strip().lstrip("r/")
        if not cleaned:
            raise HTTPException(status_code=400, detail="subreddit is required")

        hours = get_cached_hours(cleaned)
        if hours is None:
            hours = []
            try:
                account = config.accounts[0] if config.accounts else None
                if account is not None:
                    reddit = reddit_client.get_reddit(account)
                    hours = reddit_client.sample_subreddit_post_hours(
                        reddit, cleaned, limit=100
                    )
                    set_cached_hours(cleaned, hours)
            except Exception as exc:
                logger.warning("best-times sample failed for r/%s: %s", cleaned, exc)
                hours = []

        suggestions = suggest_best_times(
            hours,
            tz_offset_minutes=tz_offset_minutes,
            count=count,
        )
        return {
            "subreddit": cleaned,
            "sample_size": len(hours),
            "suggestions": suggestions,
        }

    @app.get("/api/schedule")
    def get_schedule() -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        drafts = store.list_scheduled(project_id=_pid(config))
        return {"drafts": [_serialize_draft(d, product=config.voice.product) for d in drafts]}

    @app.get("/api/activity")
    def get_activity(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        events = store.list_audit(limit=limit, project_id=_pid(config))
        return {"events": events}

    @app.get("/api/config")
    def get_config_route() -> dict[str, Any]:
        config = get_config()
        return _public_config(config)

    @app.put("/api/config")
    def put_config(body: ConfigUpdateBody) -> dict[str, Any]:
        config = get_config()

        if body.subreddits is not None:
            config.subreddits = body.subreddits
        if body.listing is not None:
            config.listing = body.listing
        if body.fetch_limit is not None:
            config.fetch_limit = body.fetch_limit
        if body.voice is not None:
            config.voice = VoiceConfig(
                product=body.voice.get("product", config.voice.product),
                tone=body.voice.get("tone", config.voice.tone),
                persona=body.voice.get("persona", config.voice.persona),
                avoid=format_text_list(body.voice.get("avoid", config.voice.avoid)),
            )
        if body.discovery is not None:
            config.discovery = DiscoveryConfig(
                keywords=body.discovery.get("keywords", config.discovery.keywords),
                min_score=float(body.discovery.get("min_score", config.discovery.min_score)),
                search_queries=list(
                    body.discovery.get("search_queries", config.discovery.search_queries)
                ),
                queries_fingerprint=str(
                    body.discovery.get("queries_fingerprint", config.discovery.queries_fingerprint)
                    or ""
                ),
            )
        if body.rate_limits is not None:
            config.rate_limits = RateLimits(
                min_interval_seconds=int(
                    body.rate_limits.get("min_interval_seconds", config.rate_limits.min_interval_seconds)
                ),
                daily_cap=int(body.rate_limits.get("daily_cap", config.rate_limits.daily_cap)),
            )
        if body.worker is not None:
            config.worker = WorkerConfig(
                interval_seconds=int(
                    body.worker.get("interval_seconds", config.worker.interval_seconds)
                ),
            )
        if body.accounts is not None:
            for update in body.accounts:
                name = update.get("name")
                if not name:
                    continue
                for account in config.accounts:
                    if account.name == name and "user_agent" in update:
                        account.user_agent = update["user_agent"]
        if body.llm is not None:
            config.llm = LLMConfig(
                base_url=body.llm.get("base_url", config.llm.base_url),
                model=body.llm.get("model", config.llm.model),
                api_key=config.llm.api_key,
            )
        if body.prompt_template is not None:
            config.prompt_template = body.prompt_template
        if body.onboarding_complete is not None:
            config.onboarding_complete = body.onboarding_complete
        if body.onboarding_step is not None:
            config.onboarding_step = max(0, min(int(body.onboarding_step), 5))
        if body.active_project_id is not None:
            config.active_project_id = body.active_project_id
        if body.purpose is not None:
            config.purpose = body.purpose
        if body.goals is not None:
            config.goals = [str(item) for item in body.goals if str(item).strip()]

        save_config(resolved_path, config)
        if any(
            value is not None
            for value in (body.subreddits, body.voice, body.discovery, body.goals, body.purpose)
        ):
            persist_config_to_project(get_store(config), config)
        return _public_config(config)

    @app.get("/api/projects")
    def list_projects() -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        return {
            "projects": [serialize_project_summary(item) for item in store.list_projects()],
            "active_project_id": _pid(config),
        }

    @app.post("/api/projects")
    def create_project_route(body: ProjectCreateBody) -> dict[str, Any]:
        purpose = (body.purpose or "").strip().lower()
        if purpose not in PROJECT_PURPOSES:
            raise HTTPException(status_code=400, detail="Purpose must be product, personal, or custom.")
        config = get_config()
        store = get_store(config)
        opening = opening_message(purpose)
        project = store.create_project(
            purpose=purpose,
            name=(body.name or "").strip(),
            interview_messages=[opening],
        )
        for item in store.list_projects(include_empty=True):
            if item["id"] != project["id"] and int(item.get("setup_step") or 0) in {3, 4, 5}:
                store.update_project(item["id"], setup_step=0)
        updated = store.update_project(project["id"], setup_step=4)
        return serialize_project(updated or project)

    @app.put("/api/projects/active")
    def set_active_project(body: ActiveProjectBody) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        project = store.get_project(body.id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        config.active_project_id = project["id"]
        apply_project_to_config(config, project)
        save_config(resolved_path, config)
        return _public_config(config)

    @app.get("/api/projects/{project_id}")
    def get_project_route(project_id: str) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        project = store.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return serialize_project(project)

    @app.patch("/api/projects/{project_id}")
    def patch_project_route(project_id: str, body: ProjectUpdateBody) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        project = store.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        fields: dict[str, Any] = {}
        for key in ("name", "briefing", "goals", "tone", "persona", "avoid", "subreddits", "keywords"):
            value = getattr(body, key)
            if value is not None:
                fields[key] = value
        if body.complete is not None:
            fields["complete"] = body.complete
            if body.complete:
                fields["setup_step"] = 0
        if body.setup_step is not None:
            fields["setup_step"] = body.setup_step
        updated = store.update_project(project_id, **fields) if fields else project
        if updated is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if body.complete or config.active_project_id == project_id:
            config.active_project_id = project_id
            apply_project_to_config(config, updated)
            save_config(resolved_path, config)
        return serialize_project(updated)

    @app.post("/api/projects/{project_id}/interview")
    def interview_project(project_id: str, body: InterviewBody) -> StreamingResponse:
        config = get_config()
        store = get_store(config)
        project = store.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if not config.llm.api_key:
            raise HTTPException(status_code=400, detail="Add an LLM API key first.")
        text = (body.message or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="Write a message first.")

        messages, researched = attach_user_turn(list(project.get("interview_messages") or []), text)
        store.update_project(project_id, interview_messages=messages, links=_merge_links(project, researched))

        def event_stream() -> Iterator[str]:
            held = ""
            emitted = 0
            try:
                if researched:
                    yield f"data: {json.dumps({'research': researched})}\n\n"
                for delta in iter_interview_reply(
                    config.llm,
                    purpose=project.get("purpose") or "custom",
                    messages=messages,
                ):
                    held += delta
                    visible = visible_interview_stream(held)
                    if len(visible) > emitted:
                        yield f"data: {json.dumps({'delta': visible[emitted:]})}\n\n"
                        emitted = len(visible)
                reply, ready = split_ready_marker(held)
                history = list(messages)
                history.append({"role": "assistant", "content": reply})
                store.update_project(project_id, interview_messages=history)
                yield f"data: {json.dumps({'done': True, 'ready': ready, 'message': {'role': 'assistant', 'content': reply}})}\n\n"
            except Exception as exc:
                logger.exception("Interview failed for %s: %s", project_id, exc)
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/projects/{project_id}/complete")
    def complete_project_route(project_id: str) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        project = store.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if not config.llm.api_key:
            raise HTTPException(status_code=400, detail="Add an LLM API key first.")
        try:
            briefing = complete_workspace(
                config.llm,
                purpose=project.get("purpose") or "custom",
                messages=list(project.get("interview_messages") or []),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Project complete failed: %s", exc)
            raise HTTPException(status_code=502, detail=f"Could not generate workspace: {exc}") from exc

        updated = store.update_project(
            project_id,
            name=briefing["name"],
            briefing=briefing["briefing"],
            goals=briefing["goals"],
            keywords=briefing["keywords"],
            tone=briefing.get("tone") or "",
            persona=briefing.get("persona") or "",
            avoid=briefing.get("avoid") or "",
            subreddits=briefing.get("subreddits") or [],
            setup_step=5,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Project not found")
        config.active_project_id = project_id
        apply_project_to_config(config, updated)
        save_config(resolved_path, config)
        return serialize_project(updated)

    def _merge_links(project: dict[str, Any], researched: list[dict[str, Any]]) -> list[dict[str, Any]]:
        existing = list(project.get("links") or [])
        seen = {str(item.get("url") or "") for item in existing}
        for item in researched:
            url = str(item.get("url") or "")
            if not url or url in seen:
                continue
            seen.add(url)
            existing.append(
                {
                    "url": url,
                    "title": item.get("title") or "",
                    "excerpt": item.get("excerpt") or "",
                    "ok": bool(item.get("ok")),
                    "error": item.get("error"),
                }
            )
        return existing

    @app.put("/api/secrets")
    def put_secrets(body: SecretsBody) -> dict[str, bool]:
        env_path = resolved_path.parent / ".env"
        mapping: dict[str, str] = {}
        account_name = body.account_name or "default"

        if body.reddit_client_id is not None:
            mapping[env_secret_key(account_name, "CLIENT_ID")] = body.reddit_client_id
        if body.reddit_client_secret is not None:
            mapping[env_secret_key(account_name, "CLIENT_SECRET")] = body.reddit_client_secret
        if body.llm_api_key is not None:
            mapping["LLM_API_KEY"] = body.llm_api_key

        if mapping:
            write_env_secrets(env_path, mapping)
        return {"ok": True}

    def _safe_next(path: str | None) -> str:
        if path in {"/onboarding", "/queue"}:
            return path
        return "/onboarding"

    @app.post("/api/oauth/start")
    def oauth_start(body: OAuthStartBody | None = None) -> dict[str, str]:
        config = get_config()
        account_name = (body.account_name if body else None) or "default"
        account = next((item for item in config.accounts if item.name == account_name), None)
        if account is None:
            raise HTTPException(status_code=400, detail=f"Unknown account: {account_name}")
        if not account.client_id:
            raise HTTPException(
                status_code=400,
                detail="Save your Reddit client ID first, then connect.",
            )
        state = secrets.token_urlsafe(24)
        app.state.oauth_pending[state] = {
            "account_name": account_name,
            "next": _safe_next(body.next if body else None),
        }
        try:
            url = reddit_client.oauth_authorize_url(
                account, config.oauth_redirect_uri, state
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"authorize_url": url, "redirect_uri": config.oauth_redirect_uri}

    @app.get("/api/oauth/callback")
    def oauth_callback(
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> RedirectResponse:
        config = get_config()
        frontend = config.frontend_url.rstrip("/")
        pending: dict[str, dict[str, str]] = app.state.oauth_pending

        def bounce(reason: str) -> RedirectResponse:
            return RedirectResponse(
                f"{frontend}/onboarding?reddit=error&reason={quote(reason)}",
                status_code=302,
            )

        if error:
            pending.pop(state, None)
            return bounce(error)
        if not code or not state or state not in pending:
            pending.pop(state, None)
            return bounce("missing_code")

        meta = pending.pop(state)
        account_name = meta["account_name"]
        account = next((item for item in config.accounts if item.name == account_name), None)
        if account is None:
            return bounce("unknown_account")
        try:
            refresh_token, username = reddit_client.oauth_exchange_code(
                account, config.oauth_redirect_uri, code
            )
        except Exception as exc:
            return bounce(str(exc))

        write_env_secrets(
            resolved_path.parent / ".env",
            {
                env_secret_key(account_name, "REFRESH_TOKEN"): refresh_token,
                env_secret_key(account_name, "USERNAME"): username,
            },
        )
        account.connected_username = username
        save_config(resolved_path, config)
        dest = meta.get("next") or "/onboarding"
        return RedirectResponse(f"{frontend}{dest}?reddit=connected", status_code=302)

    return app
