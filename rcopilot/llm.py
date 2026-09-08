"""OpenAI-compatible LLM client for generating comment drafts and search queries."""

from __future__ import annotations

import json
import logging
import re
from typing import Iterator

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


def _build_comment_prompt(
    title: str,
    selftext: str,
    comments: list[dict],
    prompt_template: str,
    *,
    product: str = "",
    tone: str = "",
    persona: str = "",
    avoid: str = "",
    goals: str = "",
) -> str:
    return prompt_template.format_map(
        SafeDict(
            title=title or "",
            selftext=selftext or "(no body)",
            comments=_format_comments(comments),
            product=product,
            tone=tone,
            persona=persona,
            avoid=avoid,
            goals=goals,
        )
    )


def iter_comment_deltas(
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
    goals: str = "",
) -> Iterator[str]:
    """Stream raw comment text deltas from an OpenAI-compatible chat completion API."""
    prompt = _build_comment_prompt(
        title,
        selftext,
        comments,
        prompt_template,
        product=product,
        tone=tone,
        persona=persona,
        avoid=avoid,
        goals=goals,
    )

    client = OpenAI(base_url=llm_config.base_url, api_key=llm_config.api_key)
    logger.debug("Requesting streaming LLM completion with model %s", llm_config.model)

    stream = client.chat.completions.create(
        model=llm_config.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.95,
        stream=True,
    )

    for chunk in stream:
        content = chunk.choices[0].delta.content if chunk.choices else None
        if content:
            yield content


def finalize_comment(text: str, *, product: str = "") -> str:
    """Strip enclosing quotes, lint, and return the cleaned comment draft."""
    result = _strip_enclosing_quotes(text)
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
    goals: str = "",
) -> str:
    """Generate a Reddit comment using an OpenAI-compatible chat completion API."""
    prompt = _build_comment_prompt(
        title,
        selftext,
        comments,
        prompt_template,
        product=product,
        tone=tone,
        persona=persona,
        avoid=avoid,
        goals=goals,
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

    return finalize_comment(content, product=product)


VARIANT_PROMPT = """Write 2 or 3 distinct Reddit comment replies as a real person in this thread — not as an assistant, marketer, or chatbot.

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

Hard rules for every body:
1. Open by answering OP's specific question or situation. Reference one concrete detail from the title or body.
2. Keep it short: about 2–6 sentences. Prefer one useful tip or lived detail over a tidy list of tips.
3. Sound like Reddit: first person, contractions, uneven sentence length. Fragments are fine.
4. No markdown: no headings, no bullet/numbered lists, no bold labels.
5. Never use em dashes (—) or en dashes (–). Use commas, periods, or parentheses.
6. Never use bot closers or AI tells: "hope this helps", "great question", "it's worth noting", "as an AI", "let me know if you have any questions", "feel free to ask", "happy to help".
7. Avoid buzzwords: delve, leverage, seamless, robust, tapestry, navigate the, unlock the, pivotal, testament.
8. Do not structure the reply as "not X, but Y" antithesis or a balanced "X, Y, and Z" triad.
9. Do not pitch the product. Mention it only if directly relevant to OP's ask, in one clause max, never as the point of the comment.
10. Each body must take a different angle (for example: direct answer, lived experience, concise take).

Return ONLY a JSON array of 2 or 3 objects. Each object must have "label" (2–4 words) and "body" (the comment). No markdown fence. Do not wrap bodies in quotes beyond JSON strings.
"""


def parse_comment_variants(raw: str, *, product: str = "") -> list[dict[str, str]]:
    """Parse 2–3 labeled comment variants from an LLM JSON array."""
    text = _strip_enclosing_quotes(raw)
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        body = finalize_comment(raw, product=product)
        return [{"id": "v1", "label": "Reply", "body": body}]

    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        body = finalize_comment(raw, product=product)
        return [{"id": "v1", "label": "Reply", "body": body}]
    if not isinstance(data, list):
        raise ValueError("LLM variant payload was not a list")

    variants: list[dict[str, str]] = []
    for index, item in enumerate(data, start=1):
        if len(variants) >= 3:
            break
        if isinstance(item, str):
            label = f"Angle {index}"
            body_raw = item
        elif isinstance(item, dict):
            label = str(item.get("label") or f"Angle {index}").strip() or f"Angle {index}"
            body_raw = str(item.get("body") or "")
        else:
            continue
        try:
            body = finalize_comment(body_raw, product=product)
        except RuntimeError:
            continue
        variants.append({"id": f"v{index}", "label": label[:40], "body": body})

    if not variants:
        raise ValueError("LLM returned no usable comment variants")
    return variants


def generate_comment_variants(
    llm_config: LLMConfig,
    title: str,
    selftext: str,
    comments: list[dict],
    *,
    product: str = "",
    tone: str = "",
    persona: str = "",
    avoid: str = "",
    goals: str = "",
) -> list[dict[str, str]]:
    """Generate 2–3 distinct comment angles for a thread."""
    prompt = VARIANT_PROMPT.format_map(
        SafeDict(
            title=title or "",
            selftext=selftext or "(no body)",
            comments=_format_comments(comments),
            product=product,
            tone=tone,
            persona=persona,
            avoid=avoid,
            goals=goals,
        )
    )

    client = OpenAI(base_url=llm_config.base_url, api_key=llm_config.api_key)
    logger.debug("Requesting LLM variants with model %s", llm_config.model)

    response = client.chat.completions.create(
        model=llm_config.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.95,
    )

    content = response.choices[0].message.content if response.choices else None
    if not content or not content.strip():
        raise RuntimeError("LLM returned an empty response")

    return parse_comment_variants(content, product=product)


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


SUBMISSION_PROMPT = """Write an original Reddit self-post for r/{subreddit}.

Your background (use lightly — this is not a pitch post):
Product/context: {product}
Goals: {goals}
Tone: {tone}
Persona: {persona}
Things to avoid: {avoid}

Hard rules:
1. Invent a genuine discussion-style self-post that fits r/{subreddit}. Prefer questions, lessons learned, or concrete experiences.
2. Title: under 120 characters, natural Reddit tone, no clickbait ALL CAPS.
3. Body: about 2–6 short paragraphs. First person, contractions OK. Fragments OK.
4. No markdown headings, no bullet lists, no bold labels.
5. Never use em dashes (—) or en dashes (–).
6. Do not pitch the product. Mention it only if it fits naturally in one short clause, never as the point of the post.
7. Do not wrap the whole post in quotes.
8. Vary the angle — do not recycle the same opener every time.

Return ONLY a JSON object with keys "title" and "body". No markdown fence."""


def parse_submission_payload(raw: str, *, product: str = "") -> tuple[str, str]:
    """Parse title/body JSON from an LLM submission response."""
    text = _strip_enclosing_quotes(raw)
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM did not return a JSON object for the submission")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM submission payload was not an object")
    title = _strip_enclosing_quotes(str(data.get("title") or ""))
    body = _strip_enclosing_quotes(str(data.get("body") or ""))
    if not title:
        raise ValueError("LLM submission missing title")
    if not body:
        raise ValueError("LLM submission missing body")
    body = finalize_comment(body, product=product)
    return title[:300], body


def generate_submission(
    llm_config: LLMConfig,
    *,
    subreddit: str,
    product: str = "",
    tone: str = "",
    persona: str = "",
    avoid: str = "",
    goals: str = "",
) -> tuple[str, str]:
    """Generate an original self-post title and body for a subreddit."""
    cleaned = subreddit.strip().lstrip("r/")
    prompt = SUBMISSION_PROMPT.format_map(
        SafeDict(
            subreddit=cleaned,
            product=product or "(not described)",
            tone=tone or "(none)",
            persona=persona or "(none)",
            avoid=avoid or "(none)",
            goals=goals or "(none)",
        )
    )
    client = OpenAI(base_url=llm_config.base_url, api_key=llm_config.api_key)
    logger.info("Generating submission idea for r/%s with model %s", cleaned, llm_config.model)
    response = client.chat.completions.create(
        model=llm_config.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=1.0,
    )
    content = response.choices[0].message.content if response.choices else None
    if not content or not content.strip():
        raise RuntimeError("LLM returned an empty submission")
    return parse_submission_payload(content, product=product)


def parse_subreddit_list(raw: str, *, limit: int = 16) -> list[str]:
    """Parse a JSON array of subreddit names from an LLM response."""
    text = _strip_enclosing_quotes(raw)
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM did not return a JSON array of subreddits")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, list):
        raise ValueError("LLM subreddit payload was not a list")

    names: list[str] = []
    seen: set[str] = set()
    for item in data:
        name = str(item).strip().lstrip("r/").lstrip("/")
        name = re.sub(r"[^A-Za-z0-9_]", "", name)
        key = name.lower()
        if len(name) < 2 or len(name) > 50 or key in seen:
            continue
        seen.add(key)
        names.append(name)
        if len(names) >= limit:
            break
    if not names:
        raise ValueError("LLM returned no usable subreddit names")
    return names


def suggest_subreddits(
    llm_config: LLMConfig,
    *,
    product: str,
    tone: str = "",
    persona: str = "",
    count: int = 12,
    purpose: str = "product",
    goals: list[str] | None = None,
) -> list[str]:
    """Suggest relevant subreddits from workspace briefing context."""
    if not (product or "").strip():
        raise ValueError("Add a briefing before suggesting subreddits")
    n = max(4, min(int(count), 20))
    goals_text = ", ".join(goals or []) or "(not specified)"
    if purpose == "personal":
        frame = "a person participating as themselves"
        mix = "hobby, career, local, and interest communities where a helpful human comment belongs"
    elif purpose == "custom":
        frame = "this custom aim"
        mix = "communities where that aim is a natural fit — not spammy promo subs"
    else:
        frame = "someone with this product"
        mix = "discussion communities, founder/product audiences, problem-space niches"
    prompt = f"""Suggest Reddit communities where {frame} should participate.

Purpose: {purpose}

Background / briefing:
{product.strip()}

Goals:
{goals_text}

Tone:
{tone.strip() or "(not specified)"}

Persona:
{persona.strip() or "(not specified)"}

Return {n} real, active subreddit names that fit ({mix}). Mix broad and niche. Prefer communities where helpful comments or organic self-posts make sense — not spammy promo subs.

Rules:
- Names only, no r/ prefix
- No invented subreddits if you know better alternatives
- No duplicates
- Return ONLY a JSON array of strings"""

    client = OpenAI(base_url=llm_config.base_url, api_key=llm_config.api_key)
    logger.info("Suggesting subreddits with model %s", llm_config.model)
    response = client.chat.completions.create(
        model=llm_config.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    content = response.choices[0].message.content if response.choices else None
    if not content or not content.strip():
        raise RuntimeError("LLM returned an empty subreddit list")
    return parse_subreddit_list(content, limit=n)


def build_search_query_prompt(
    *,
    product: str,
    keywords: list[str],
    subreddits: list[str],
    persona: str = "",
    purpose: str = "product",
    goals: list[str] | None = None,
) -> str:
    goals_text = ", ".join(goals or []) or "(none)"
    if purpose == "product":
        intent = (
            "find threads where someone might need this product or be asking about the problem it solves.\n"
            "Mix: looking for / recommend / anyone using, alternative to, problem statements, how do you / what do you use."
        )
    elif purpose == "personal":
        intent = (
            "find threads where this person can be useful, given their goals — not buying-intent product hunt queries unless that is the goal.\n"
            "Mix: questions in their domain, advice requests, experiences, how do you / what do you use."
        )
    else:
        intent = (
            "find threads that match this custom aim and stated goals.\n"
            "Mix: the language real Reddit users would type for that aim."
        )
    return f"""Generate Reddit search queries to {intent}

Purpose: {purpose}

Background:
{product or "(not described)"}

Goals:
{goals_text}

Persona notes:
{persona or "(none)"}

Keywords they already care about:
{", ".join(keywords) if keywords else "(none)"}

They watch these subreddits (do not put subreddit names in the queries):
{", ".join(subreddits) if subreddits else "(none)"}

Write {QUERY_LIMIT} short queries a real Reddit user might type.
No site operators, no subreddit names, no quotes around the whole list.
Return ONLY a JSON array of strings."""


def generate_search_queries(
    llm_config: LLMConfig,
    *,
    product: str,
    keywords: list[str],
    subreddits: list[str],
    persona: str = "",
    purpose: str = "product",
    goals: list[str] | None = None,
) -> list[str]:
    """Ask the LLM for varied Reddit search queries, then fall back locally if needed."""
    prompt = build_search_query_prompt(
        product=product,
        keywords=keywords,
        subreddits=subreddits,
        persona=persona,
        purpose=purpose,
        goals=goals,
    )

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
