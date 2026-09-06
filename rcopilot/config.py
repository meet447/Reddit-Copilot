"""Configuration loading and persistence for Reddit Copilot."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values, load_dotenv

DEFAULT_PROMPT_TEMPLATE = """You are drafting a helpful Reddit comment.

Post title: {title}
Post body: {selftext}
Top comments:
{comments}

Product context: {product}
Tone: {tone}
Persona: {persona}
Things to avoid: {avoid}

Write a single Reddit comment reply. Be concise, helpful, and natural. Do not use markdown headers. Do not wrap the reply in quotes."""


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


def _env_account_prefix(name: str) -> str:
    sanitized = re.sub(r"[^A-Z0-9]", "_", name.upper())
    return f"REDDIT_{sanitized}"


def _fill_account_secrets(account: Account, env: dict[str, str | None]) -> None:
    prefix = _env_account_prefix(account.name)
    if account.name == "default":
        account.client_id = account.client_id or env.get("REDDIT_CLIENT_ID") or ""
        account.client_secret = account.client_secret or env.get("REDDIT_CLIENT_SECRET") or ""
        account.username = account.username or env.get("REDDIT_USERNAME") or ""
        account.password = account.password or env.get("REDDIT_PASSWORD") or ""
    else:
        account.client_id = account.client_id or env.get(f"{prefix}_CLIENT_ID") or ""
        account.client_secret = account.client_secret or env.get(f"{prefix}_CLIENT_SECRET") or ""
        account.username = account.username or env.get(f"{prefix}_USERNAME") or ""
        account.password = account.password or env.get(f"{prefix}_PASSWORD") or ""


def _parse_account(raw: dict[str, Any]) -> Account:
    return Account(
        name=str(raw.get("name", "default")),
        user_agent=str(raw.get("user_agent", "reddit-copilot/1.0")),
        client_id=str(raw.get("client_id", "")),
        client_secret=str(raw.get("client_secret", "")),
        username=str(raw.get("username", "")),
        password=str(raw.get("password", "")),
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
        listing=str(raw.get("listing", "hot")),
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
            avoid=str(voice_raw.get("avoid", "")),
        ),
        discovery=DiscoveryConfig(
            keywords=list(discovery_raw.get("keywords") or []),
            min_score=float(discovery_raw.get("min_score", 0.25)),
        ),
        worker=WorkerConfig(interval_seconds=int(worker_raw.get("interval_seconds", 300))),
        prompt_template=str(raw.get("prompt_template") or DEFAULT_PROMPT_TEMPLATE),
        onboarding_complete=bool(raw.get("onboarding_complete", False)),
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
    }

    for account in config.accounts:
        acct: dict[str, Any] = {"name": account.name, "user_agent": account.user_agent}
        if include_secrets:
            acct.update(
                {
                    "client_id": account.client_id,
                    "client_secret": account.client_secret,
                    "username": account.username,
                    "password": account.password,
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
        listing="hot",
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


def sanitize_config(config: AppConfig) -> dict[str, Any]:
    """Return config safe for API responses (no secrets)."""
    data = _config_to_yaml_dict(config, include_secrets=False)
    data["has_credentials"] = any(
        account.client_id and account.client_secret and account.username
        for account in config.accounts
    )
    data["has_api_key"] = bool(config.llm.api_key)
    data["accounts"] = [
        {
            "name": account.name,
            "user_agent": account.user_agent,
            "has_username": bool(account.username),
        }
        for account in config.accounts
    ]
    return data
