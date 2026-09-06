"""Discovery query generation tests (no network)."""

from __future__ import annotations

from rcopilot.llm import fallback_search_queries, parse_query_list
from rcopilot.pipeline import _queries_fingerprint, ensure_search_queries
from rcopilot.config import (
    Account,
    AppConfig,
    DiscoveryConfig,
    LLMConfig,
    RateLimits,
    VoiceConfig,
    WorkerConfig,
)


def _config(**overrides) -> AppConfig:
    data = dict(
        subreddits=["startups"],
        listing="new",
        fetch_limit=25,
        db_path="unused.db",
        accounts=[Account(name="default", user_agent="test/1.0")],
        llm=LLMConfig(base_url="https://example.com/v1", model="test"),
        rate_limits=RateLimits(),
        voice=VoiceConfig(product="Reddit Copilot, a local Reddit engagement assistant"),
        discovery=DiscoveryConfig(keywords=["looking for", "gummysearch"]),
        worker=WorkerConfig(),
        prompt_template="test {title}",
    )
    data.update(overrides)
    return AppConfig(**data)


def test_parse_query_list_from_fenced_json() -> None:
    raw = """Here you go:
```json
["looking for reddit tool", "alternative to gummysearch", "how do you find intent threads"]
```
"""
    queries = parse_query_list(raw)
    assert queries[0] == "looking for reddit tool"
    assert "alternative to gummysearch" in queries


def test_fallback_queries_include_product_and_keywords() -> None:
    queries = fallback_search_queries(
        "Reddit Copilot local-first engagement assistant",
        ["gummysearch"],
    )
    blob = " ".join(queries).lower()
    assert "gummysearch" in blob
    assert "looking for" in blob
    assert any("engagement" in query or "copilot" in query or "assistant" in query for query in queries)


def test_ensure_search_queries_reuses_cache() -> None:
    config = _config()
    config.discovery.search_queries = ["cached query"]
    config.discovery.queries_fingerprint = _queries_fingerprint(config)
    assert ensure_search_queries(config) == ["cached query"]


def test_ensure_search_queries_falls_back_without_api_key() -> None:
    config = _config()
    queries = ensure_search_queries(config)
    assert queries
    assert config.discovery.queries_fingerprint == _queries_fingerprint(config)
    assert config.discovery.search_queries == queries
