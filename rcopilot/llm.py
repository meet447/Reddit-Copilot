"""OpenAI-compatible LLM client for generating comment drafts and search queries."""

from __future__ import annotations

import json
import logging
import re

from openai import OpenAI

from rcopilot.config import LLMConfig, SafeDict
from rcopilot.draft_lint import apply_lint
from rcopilot.scoring import intent_terms_from_product

logger = logging.getLogger(__name__)

QUERY_LIMIT = 8


def _format_comments(comments: list[dict]) -> str:
    if not comments:
        return "(none)"
    lines: list[str] = []
    for index, comment in enumerate(comments, start=1):
        body = (comment.get("body") or "").strip()
        score = comment.get("score", 0)
        lines.append(f"{index}. [{score} pts] {body}")
    return "\n".join(lines)


def _strip_enclosing_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1].strip()
    return text


def generate_comment(
    llm_config: LLMConfig,
    title: str,
    selftext: str,
    comments: list[dict],
    prompt_template: str,
    *,
    product: str = "",
    tone: str = "",
    persona: str = "",
    avoid: str = "",
) -> str:
    """Generate a Reddit comment using an OpenAI-compatible chat completion API."""
    prompt = prompt_template.format_map(
        SafeDict(
            title=title or "",
            selftext=selftext or "(no body)",
            comments=_format_comments(comments),
            product=product,
            tone=tone,
            persona=persona,
            avoid=avoid,
        )
    )

    client = OpenAI(base_url=llm_config.base_url, api_key=llm_config.api_key)
    logger.debug("Requesting LLM completion with model %s", llm_config.model)

    response = client.chat.completions.create(
        model=llm_config.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.95,
    )

    content = response.choices[0].message.content if response.choices else None
    if not content or not content.strip():
        raise RuntimeError("LLM returned an empty response")

    result = _strip_enclosing_quotes(content)
    if not result:
        raise RuntimeError("LLM returned an empty response after cleanup")

    lint = apply_lint(result, product=product)
    if "empty" in lint.codes:
        raise RuntimeError("LLM draft was empty after anti-slop cleanup")
    remaining = lint.codes - {"em_dash", "bot_phrase"}
    if remaining:
        logger.warning("Draft lint issues after cleanup: %s", sorted(remaining))
    elif lint.codes:
        logger.info("Draft auto-cleaned: %s", sorted(lint.codes))

    logger.debug("Generated comment (%d chars)", len(lint.cleaned))
    return lint.cleaned


def parse_query_list(raw: str, *, limit: int = QUERY_LIMIT) -> list[str]:
    """Parse a JSON array of search queries from an LLM response."""
    text = _strip_enclosing_quotes(raw)
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM did not return a JSON array of queries")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, list):
        raise ValueError("LLM query payload was not a list")

    queries: list[str] = []
    seen: set[str] = set()
    for item in data:
        query = str(item).strip().strip("\"'")
        key = query.lower()
        if len(query) < 3 or len(query) > 80 or key in seen:
            continue
        seen.add(key)
        queries.append(query)
        if len(queries) >= limit:
            break
    if not queries:
        raise ValueError("LLM returned no usable search queries")
    return queries


def fallback_search_queries(product: str, keywords: list[str], *, limit: int = QUERY_LIMIT) -> list[str]:
    """Build search queries without an LLM from keywords and the product blurb."""
    queries: list[str] = []
    seen: set[str] = set()

    def add(query: str) -> None:
        cleaned = query.strip()
        key = cleaned.lower()
        if len(cleaned) < 3 or key in seen:
            return
        seen.add(key)
        queries.append(cleaned)

    for keyword in keywords:
        add(keyword)
        add(f"looking for {keyword}")

    for term in intent_terms_from_product(product, limit=6):
        add(term)
        add(f"looking for {term}")
        add(f"alternative to {term}")

    if not queries:
        add("looking for a tool")
        add("recommend a tool")
        add("alternative to")
    return queries[:limit]


def generate_search_queries(
    llm_config: LLMConfig,
    *,
    product: str,
    keywords: list[str],
    subreddits: list[str],
    persona: str = "",
) -> list[str]:
    """Ask the LLM for varied Reddit search queries, then fall back locally if needed."""
    prompt = f"""Generate Reddit search queries to find threads where someone might need this product.

Product:
{product or "(not described)"}

Persona notes:
{persona or "(none)"}

Keywords they already care about:
{", ".join(keywords) if keywords else "(none)"}

They watch these subreddits (do not put subreddit names in the queries):
{", ".join(subreddits) if subreddits else "(none)"}

Write {QUERY_LIMIT} short queries a real Reddit user might type. Mix:
- looking for / recommend / anyone using
- alternative to
- problem statements
- how do you / what do you use

No site operators, no subreddit names, no quotes around the whole list.
Return ONLY a JSON array of strings."""

    client = OpenAI(base_url=llm_config.base_url, api_key=llm_config.api_key)
    logger.info("Generating discovery search queries with model %s", llm_config.model)
    response = client.chat.completions.create(
        model=llm_config.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
    )
    content = response.choices[0].message.content if response.choices else None
    if not content or not content.strip():
        raise RuntimeError("LLM returned an empty query list")
    return parse_query_list(content)
