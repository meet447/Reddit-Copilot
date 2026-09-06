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
    load_config,
    sanitize_config,
    save_config,
    write_env_secrets,
)
from rcopilot import reddit_client
from rcopilot.draft_lint import lint_draft
from rcopilot.pipeline import (
    approve_draft,
    cancel_schedule,
    draft_one,
    draft_pending,
    edit_draft,
    fetch_and_store,
    finish_draft_stream,
    iter_draft_deltas,
    post_approved,
    queue_post,
    regenerate_draft,
    reject_draft,
    run_once,
    schedule_draft,
    skip_post,
)
from rcopilot.store import Store

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
)


class DraftEditBody(BaseModel):
    body: str


class ApproveBody(BaseModel):
    body: str | None = None


class ScheduleBody(BaseModel):
    run_at: str


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
        return load_config(resolved_path)

    def get_store(config: AppConfig) -> Store:
        store = Store(config.db_path)
        store.ensure_schema()
        return store

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
        counts = store.count_drafts_by_status()
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
        drafts = store.list_drafts(status=filter_status)
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
            edit_draft(store, draft_id, body.body)
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
    ) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        posts = store.list_posts(
            undrafted=undrafted if undrafted else None,
            skipped=skipped,
            min_score=config.discovery.min_score if undrafted else None,
        )
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
            skip_post(store, post_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        post = store.get_post(post_id)
        return _serialize_post(post)  # type: ignore[arg-type]

    @app.post("/api/actions/fetch")
    def action_fetch() -> dict[str, int]:
        config = get_config()
        store = get_store(config)
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

    @app.get("/api/schedule")
    def get_schedule() -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        drafts = store.list_scheduled()
        return {"drafts": [_serialize_draft(d, product=config.voice.product) for d in drafts]}

    @app.get("/api/activity")
    def get_activity(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        config = get_config()
        store = get_store(config)
        events = store.list_audit(limit=limit)
        return {"events": events}

    @app.get("/api/config")
    def get_config_route() -> dict[str, Any]:
        config = get_config()
        return sanitize_config(config)

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
                avoid=body.voice.get("avoid", config.voice.avoid),
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
            config.onboarding_step = max(0, min(int(body.onboarding_step), 4))

        save_config(resolved_path, config)
        return sanitize_config(config)

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
