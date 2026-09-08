"""Project workspaces: seed, hydrate, and mirror into AppConfig."""

from __future__ import annotations

from typing import Any

from rcopilot.config import AppConfig, DiscoveryConfig, VoiceConfig, format_text_list
from rcopilot.store import DEFAULT_PROJECT_ID, Store


def project_is_complete(project: dict[str, Any] | None) -> bool:
    if not project:
        return False
    if project.get("complete"):
        return True
    return bool(project.get("subreddits")) and bool((project.get("briefing") or "").strip())


def has_finished_project(store: Store) -> bool:
    return any(project_is_complete(item) for item in store.list_projects(include_empty=True))


def seed_projects_from_config(store: Store, config: AppConfig) -> dict[str, Any] | None:
    """If yaml still holds the only voice/subreddits, copy them onto the default project."""
    store.ensure_schema()
    visible = store.list_projects()
    if visible:
        return None

    default = store.get_project(DEFAULT_PROJECT_ID)
    has_legacy = bool(
        (config.voice.product or "").strip()
        or config.onboarding_complete
    )
    if not has_legacy or default is None:
        return None

    name = _name_from_briefing(config.voice.product) or "Default"
    return store.update_project(
        DEFAULT_PROJECT_ID,
        name=name,
        purpose="product",
        briefing=config.voice.product,
        tone=config.voice.tone,
        persona=config.voice.persona,
        avoid=config.voice.avoid,
        subreddits=list(config.subreddits),
        keywords=list(config.discovery.keywords),
        search_queries=list(config.discovery.search_queries),
        queries_fingerprint=config.discovery.queries_fingerprint,
        complete=bool(config.onboarding_complete and config.subreddits),
    )


def resolve_active_project(store: Store, config: AppConfig) -> dict[str, Any] | None:
    seed_projects_from_config(store, config)
    wanted = (config.active_project_id or "").strip()
    if wanted:
        project = store.get_project(wanted)
        if project:
            return project
    visible = store.list_projects()
    if visible:
        return visible[0]
    return store.get_project(DEFAULT_PROJECT_ID)


def apply_project_to_config(config: AppConfig, project: dict[str, Any] | None) -> AppConfig:
    """Copy project briefing/subs into the in-memory config used by pipeline + API."""
    if not project:
        return config
    config.active_project_id = project["id"]
    unused = not (
        project.get("complete")
        or (project.get("briefing") or "").strip()
        or project.get("subreddits")
    )
    if unused:
        return config
    config.purpose = project.get("purpose") or "product"
    config.goals = list(project.get("goals") or [])
    config.voice = VoiceConfig(
        product=project.get("briefing") or "",
        tone=project.get("tone") or "",
        persona=project.get("persona") or "",
        avoid=format_text_list(project.get("avoid") or ""),
    )
    config.subreddits = list(project.get("subreddits") or [])
    config.discovery = DiscoveryConfig(
        keywords=list(project.get("keywords") or []),
        min_score=config.discovery.min_score,
        search_queries=list(project.get("search_queries") or []),
        queries_fingerprint=str(project.get("queries_fingerprint") or ""),
    )
    return config


def persist_config_to_project(store: Store, config: AppConfig) -> dict[str, Any] | None:
    """Write voice/subreddits/keywords from config onto the active project."""
    project_id = (config.active_project_id or "").strip() or DEFAULT_PROJECT_ID
    project = store.get_project(project_id)
    if project is None:
        return None
    return store.update_project(
        project_id,
        briefing=config.voice.product,
        tone=config.voice.tone,
        persona=config.voice.persona,
        avoid=config.voice.avoid,
        purpose=config.purpose if config.purpose in ("product", "personal", "custom") else project["purpose"],
        subreddits=list(config.subreddits),
        keywords=list(config.discovery.keywords),
        search_queries=list(config.discovery.search_queries),
        queries_fingerprint=config.discovery.queries_fingerprint,
        goals=list(config.goals or []),
    )


def persist_queries_to_project(store: Store, config: AppConfig) -> None:
    project_id = (config.active_project_id or "").strip() or DEFAULT_PROJECT_ID
    if store.get_project(project_id) is None:
        return
    store.update_project(
        project_id,
        search_queries=list(config.discovery.search_queries),
        queries_fingerprint=config.discovery.queries_fingerprint,
    )


def serialize_project(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": project["id"],
        "name": project.get("name") or "",
        "purpose": project.get("purpose") or "product",
        "briefing": project.get("briefing") or "",
        "goals": list(project.get("goals") or []),
        "links": list(project.get("links") or []),
        "interview_messages": list(project.get("interview_messages") or []),
        "tone": project.get("tone") or "",
        "persona": project.get("persona") or "",
        "avoid": format_text_list(project.get("avoid") or ""),
        "subreddits": list(project.get("subreddits") or []),
        "keywords": list(project.get("keywords") or []),
        "search_queries": list(project.get("search_queries") or []),
        "complete": bool(project.get("complete")),
        "setup_step": int(project.get("setup_step") or 0),
        "created_at": project.get("created_at"),
        "updated_at": project.get("updated_at"),
    }


def serialize_project_summary(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": project["id"],
        "name": project.get("name") or _name_from_briefing(project.get("briefing") or "") or "Untitled",
        "purpose": project.get("purpose") or "product",
        "complete": bool(project.get("complete")),
    }


def _name_from_briefing(briefing: str) -> str:
    text = (briefing or "").strip()
    if not text:
        return ""
    first = text.splitlines()[0].strip()
    first = first.split(".")[0].strip()
    if len(first) > 48:
        first = first[:45].rstrip() + "…"
    return first
