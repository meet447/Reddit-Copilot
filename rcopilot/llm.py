"""OpenAI-compatible LLM client for generating comment drafts."""

from __future__ import annotations

import logging

from openai import OpenAI

from rcopilot.config import LLMConfig, SafeDict

logger = logging.getLogger(__name__)


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
        temperature=0.7,
    )

    content = response.choices[0].message.content if response.choices else None
    if not content or not content.strip():
        raise RuntimeError("LLM returned an empty response")

    result = _strip_enclosing_quotes(content)
    if not result:
        raise RuntimeError("LLM returned an empty response after cleanup")

    logger.debug("Generated comment (%d chars)", len(result))
    return result
