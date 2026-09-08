"""Configuration loading and persistence for Reddit Copilot."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values, load_dotenv


def format_text_list(value: Any) -> str:
    """Turn a string or list into readable newline-separated text.

    Interview extraction often returns `avoid` as a JSON array; storing
    `str(list)` made Settings show Python repr like ``['Hard selling', ...]``.
    """
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return "\n".join(items)
    text = str(value or "").strip()
    if len(text) >= 2 and text.startswith("[") and text.endswith("]"):
        parsed: Any = None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                parsed = None
        if isinstance(parsed, list):
            return "\n".join(str(item).strip() for item in parsed if str(item).strip())
    return text


DEFAULT_PROMPT_TEMPLATE = """Write a Reddit comment reply as a real person in this thread — not as an assistant, marketer, or chatbot.

Post title: {title}
Post body: {selftext}
Top comments (for context; do not copy them):
{comments}

Your background (use only if it genuinely helps answer OP):
Product/context: {product}
Goals: {goals}
Tone: {tone}
Persona: {persona}
Things to avoid: {avoid}

Hard rules:
1. Open by answering OP's specific question or situation. Reference one concrete detail from the title or body.
2. Keep it short: about 2–6 sentences. Prefer one useful tip or lived detail over a tidy list of tips.
3. Sound like Reddit: first person, contractions, uneven sentence length. Fragments are fine.
4. No markdown: no headings, no bullet/numbered lists, no bold labels.
5. Never use em dashes (—) or en dashes (–). Use commas, periods, or parentheses.
6. Never use bot closers or AI tells: "hope this helps", "great question", "it's worth noting", "as an AI", "let me know if you have any questions", "feel free to ask", "happy to help".
7. Avoid buzzwords: delve, leverage, seamless, robust, tapestry, navigate the, unlock the, pivotal, testament.
8. Do not structure the reply as "not X, but Y" antithesis or a balanced "X, Y, and Z" triad.
9. Do not pitch the product. Mention it only if directly relevant to OP's ask, in one clause max, never as the point of the comment.
10. Do not wrap the reply in quotes. Output only the comment body — nothing else.
"""


class SafeDict(dict):
    """Dict for str.format_map that leaves unknown placeholders intact."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


@dataclass
class Account:
    name: str
    user_agent: str
    client_id: str = ""
    client_secret: str = ""
    username: str = ""
    password: str = ""
    refresh_token: str = ""
    connected_username: str = ""


@dataclass
class LLMConfig:
    base_url: str
    model: str
    api_key: str = ""


@dataclass
class RateLimits:
    min_interval_seconds: int = 120
    daily_cap: int = 10


@dataclass
class VoiceConfig:
    product: str = ""
    tone: str = ""
    persona: str = ""
    avoid: str = ""


@dataclass
class DiscoveryConfig:
    keywords: list[str] = field(default_factory=list)
    min_score: float = 0.25
    search_queries: list[str] = field(default_factory=list)
    queries_fingerprint: str = ""


@dataclass
class WorkerConfig:
    interval_seconds: int = 300


@dataclass
class AppConfig:
    subreddits: list[str]
    listing: str
    fetch_limit: int
    db_path: str
    accounts: list[Account]
    llm: LLMConfig
    rate_limits: RateLimits
    voice: VoiceConfig
    discovery: DiscoveryConfig
    worker: WorkerConfig
    prompt_template: str
    onboarding_complete: bool = False
    onboarding_step: int = 0
    oauth_redirect_uri: str = "http://127.0.0.1:8000/api/oauth/callback"
    frontend_url: str = "http://localhost:3000"
    active_project_id: str = ""
    purpose: str = "product"
    goals: list[str] = field(default_factory=list)


def _env_account_prefix(name: str) -> str:
    sanitized = re.sub(r"[^A-Z0-9]", "_", name.upper())
    return f"REDDIT_{sanitized}"


def env_secret_key(account_name: str, suffix: str) -> str:
    """Return .env key for a Reddit secret, e.g. CLIENT_ID or REFRESH_TOKEN."""
    if account_name == "default":
        return f"REDDIT_{suffix}"
    return f"{_env_account_prefix(account_name)}_{suffix}"


def _clamp_onboarding_step(value: Any) -> int:
    try:
        step = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, min(step, 5))


def _fill_account_secrets(account: Account, env: dict[str, str | None]) -> None:
    account.client_id = account.client_id or env.get(env_secret_key(account.name, "CLIENT_ID")) or ""
    account.client_secret = (
        account.client_secret or env.get(env_secret_key(account.name, "CLIENT_SECRET")) or ""
    )
    account.username = account.username or env.get(env_secret_key(account.name, "USERNAME")) or ""
    account.password = account.password or env.get(env_secret_key(account.name, "PASSWORD")) or ""
    account.refresh_token = (
        account.refresh_token or env.get(env_secret_key(account.name, "REFRESH_TOKEN")) or ""
    )
    if not account.connected_username and account.username:
        account.connected_username = account.username


def _parse_account(raw: dict[str, Any]) -> Account:
    return Account(
        name=str(raw.get("name", "default")),
        user_agent=str(raw.get("user_agent", "reddit-copilot/1.0")),
        client_id=str(raw.get("client_id", "")),
        client_secret=str(raw.get("client_secret", "")),
        username=str(raw.get("username", "")),
        password=str(raw.get("password", "")),
        connected_username=str(raw.get("connected_username", "")),
    )


def load_config(path: str | Path) -> AppConfig:
    """Load configuration from YAML and fill secrets from .env."""
    config_path = Path(path)
    load_dotenv(config_path.parent / ".env")
    env = dotenv_values(config_path.parent / ".env")

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    accounts = [_parse_account(item) for item in raw.get("accounts") or [{"name": "default"}]]
    for account in accounts:
        _fill_account_secrets(account, env)

    llm_raw = raw.get("llm") or {}
    llm = LLMConfig(
        base_url=str(llm_raw.get("base_url", "https://api.openai.com/v1")),
        model=str(llm_raw.get("model", "gpt-4o-mini")),
        api_key=str(llm_raw.get("api_key") or env.get("LLM_API_KEY") or ""),
    )

    rate_raw = raw.get("rate_limits") or {}
    voice_raw = raw.get("voice") or {}
    discovery_raw = raw.get("discovery") or {}
    worker_raw = raw.get("worker") or {}

    return AppConfig(
        subreddits=list(raw.get("subreddits") or []),
        listing=str(raw.get("listing", "new")),
        fetch_limit=int(raw.get("fetch_limit", 25)),
        db_path=str(raw.get("db_path", "rcopilot.db")),
        accounts=accounts,
        llm=llm,
        rate_limits=RateLimits(
            min_interval_seconds=int(rate_raw.get("min_interval_seconds", 120)),
            daily_cap=int(rate_raw.get("daily_cap", 10)),
        ),
        voice=VoiceConfig(
            product=str(voice_raw.get("product", "")),
            tone=str(voice_raw.get("tone", "")),
            persona=str(voice_raw.get("persona", "")),
            avoid=format_text_list(voice_raw.get("avoid", "")),
        ),
        discovery=DiscoveryConfig(
            keywords=list(discovery_raw.get("keywords") or []),
            min_score=float(discovery_raw.get("min_score", 0.25)),
            search_queries=[str(item) for item in (discovery_raw.get("search_queries") or []) if str(item).strip()],
            queries_fingerprint=str(discovery_raw.get("queries_fingerprint") or ""),
        ),
        worker=WorkerConfig(interval_seconds=int(worker_raw.get("interval_seconds", 300))),
        prompt_template=str(raw.get("prompt_template") or DEFAULT_PROMPT_TEMPLATE),
        onboarding_complete=bool(raw.get("onboarding_complete", False)),
        onboarding_step=_clamp_onboarding_step(raw.get("onboarding_step", 0)),
        oauth_redirect_uri=str(
            raw.get("oauth_redirect_uri") or "http://127.0.0.1:8000/api/oauth/callback"
        ),
        frontend_url=str(raw.get("frontend_url") or "http://localhost:3000"),
        active_project_id=str(raw.get("active_project_id") or ""),
        purpose=str(raw.get("purpose") or "product"),
        goals=[str(item) for item in (raw.get("goals") or []) if str(item).strip()],
    )


def _config_to_yaml_dict(config: AppConfig, *, include_secrets: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "subreddits": config.subreddits,
        "listing": config.listing,
        "fetch_limit": config.fetch_limit,
        "db_path": config.db_path,
        "accounts": [],
        "llm": {
            "base_url": config.llm.base_url,
            "model": config.llm.model,
        },
        "rate_limits": asdict(config.rate_limits),
        "voice": asdict(config.voice),
        "discovery": asdict(config.discovery),
        "worker": asdict(config.worker),
        "onboarding_complete": config.onboarding_complete,
        "onboarding_step": config.onboarding_step,
        "oauth_redirect_uri": config.oauth_redirect_uri,
        "frontend_url": config.frontend_url,
        "active_project_id": config.active_project_id,
    }

    for account in config.accounts:
        acct: dict[str, Any] = {
            "name": account.name,
            "user_agent": account.user_agent,
        }
        if account.connected_username:
            acct["connected_username"] = account.connected_username
        if include_secrets:
            acct.update(
                {
                    "client_id": account.client_id,
                    "client_secret": account.client_secret,
                    "username": account.username,
                    "password": account.password,
                    "refresh_token": account.refresh_token,
                }
            )
        data["accounts"].append(acct)

    if include_secrets and config.llm.api_key:
        data["llm"]["api_key"] = config.llm.api_key

    if config.prompt_template != DEFAULT_PROMPT_TEMPLATE:
        data["prompt_template"] = config.prompt_template

    return data


def save_config(path: str | Path, config: AppConfig) -> None:
    """Write configuration to YAML without secrets."""
    config_path = Path(path)
    data = _config_to_yaml_dict(config, include_secrets=False)
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False)


def write_example_config(path: str | Path) -> None:
    """Write an example config.yaml."""
    example = AppConfig(
        subreddits=["python", "learnpython"],
        listing="new",
        fetch_limit=25,
        db_path="rcopilot.db",
        accounts=[
            Account(
                name="default",
                user_agent="reddit-copilot/1.0 by u/YOUR_USERNAME",
            )
        ],
        llm=LLMConfig(base_url="https://api.openai.com/v1", model="gpt-4o-mini"),
        rate_limits=RateLimits(),
        voice=VoiceConfig(),
        discovery=DiscoveryConfig(keywords=[], min_score=0.25),
        worker=WorkerConfig(),
        prompt_template=DEFAULT_PROMPT_TEMPLATE,
        onboarding_complete=False,
    )
    save_config(path, example)


def write_env_secrets(env_path: str | Path, mapping: dict[str, str]) -> None:
    """Update or create .env keys from *mapping* (only provided keys)."""
    env_file = Path(env_path)
    existing: dict[str, str] = {}
    if env_file.exists():
        for key, value in dotenv_values(env_file).items():
            if key and value is not None:
                existing[key] = value

    existing.update({key: value for key, value in mapping.items() if value is not None})

    lines = [f"{key}={existing[key]}" for key in sorted(existing)]
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def account_is_connected(account: Account) -> bool:
    """True when OAuth refresh token or password-grant credentials exist."""
    if account.refresh_token:
        return True
    return bool(account.username and account.password)


def sanitize_config(config: AppConfig) -> dict[str, Any]:
    """Return config safe for API responses (no secrets)."""
    data = _config_to_yaml_dict(config, include_secrets=False)
    data["has_credentials"] = any(
        account.client_id and account_is_connected(account) for account in config.accounts
    )
    data["has_oauth"] = any(bool(account.refresh_token) for account in config.accounts)
    data["has_api_key"] = bool(config.llm.api_key)
    data["active_project_id"] = config.active_project_id
    data["purpose"] = config.purpose or "product"
    data["goals"] = list(config.goals or [])
    data["accounts"] = [
        {
            "name": account.name,
            "user_agent": account.user_agent,
            "has_username": bool(account.username or account.connected_username),
            "has_oauth": bool(account.refresh_token),
            "connected_username": account.connected_username or account.username,
            "has_client_id": bool(account.client_id),
        }
        for account in config.accounts
    ]
    return data
