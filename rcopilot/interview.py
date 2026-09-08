"""Conversational project briefing (Ollama-safe: no tool calling)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterator

from openai import OpenAI

from rcopilot.config import LLMConfig, format_text_list
from rcopilot.llm import parse_subreddit_list, suggest_subreddits
from rcopilot.projects import _name_from_briefing
from rcopilot.research import extract_urls, research_urls

logger = logging.getLogger(__name__)

OPENING_PROMPTS = {
    "product": (
        "Tell me about your product. What is it, who is it for, and what problem does it solve? "
        "You can also paste links to the site, docs, or a launch post."
    ),
    "personal": (
        "Tell me about yourself — what you do, the communities you care about, "
        "and how you want to show up on Reddit."
    ),
    "custom": (
        "What do you want to do with this copilot? What is your aim — "
        "the more specific, the better I can set up discovery and drafts."
    ),
}

READY_MARKER = "READY_FOR_WORKSPACE"

_READY_RULE = (
    "When you have enough to generate the workspace — a name, a short briefing, "
    "and at least one goal — do not ask another question. Write one short sentence "
    f"that you are setting up the workspace now, then on its own last line write exactly: {READY_MARKER}\n"
    f"If anything important is still missing, ask one question and do not write {READY_MARKER}."
)

_SYSTEM_BY_PURPOSE = {
    "product": f"""You are helping someone set up a Reddit Copilot workspace for a product.

Interview agenda (ask one thing at a time, short messages):
1. Understand the product (what it is, who it is for, what problem it solves).
2. Ask what they want out of Reddit (goals: signups, feedback, being helpful in niche subs, etc.).
3. Invite them to paste links (site, docs, launch post). When page excerpts appear in the thread, use them and ask a follow-up if something important is still missing.
4. Ask remaining follow-ups: tone, what to avoid, audiences, competitors.

Rules:
- Sound like a calm desk companion, not a growth hacker.
- 1–3 short sentences per turn. One question at a time.
- Never pitch posting automation. This tool only drafts; humans publish.
- {_READY_RULE}""",
    "personal": f"""You are helping someone set up a Reddit Copilot workspace for personal use (not a company product).

Interview agenda (ask one thing at a time, short messages):
1. Understand them (work, interests, expertise, how they want to sound).
2. Ask follow-ups until you can picture where they would be a useful commenter.
3. Ask their Reddit goals (learn, share expertise, job search, hobby community, personal brand — whatever they say).
4. More follow-ups for tone, topics to avoid, communities they already like.

Rules:
- Sound like a calm desk companion.
- 1–3 short sentences per turn. One question at a time.
- Do not assume they are selling a product.
- {_READY_RULE}""",
    "custom": f"""You are helping someone set up a Reddit Copilot workspace with no template.

They will tell you exactly what they want this copilot for. Follow their lead.
Ask only the follow-ups you need for: who they are in this context, what success looks like, topics/keywords, and which kinds of Reddit communities fit.

Rules:
- Sound like a calm desk companion.
- 1–3 short sentences per turn. One question at a time.
- Do not force a product or personal-brand frame if they described something else.
- {_READY_RULE}""",
}

EXTRACT_PROMPT = """From this briefing interview, extract a JSON object for a Reddit Copilot workspace.

Purpose: {purpose}

Transcript:
{transcript}

Return ONLY JSON with keys:
- name: short workspace name (2–6 words)
- briefing: 1–3 paragraph summary of who/what this is for (the background used in drafts)
- goals: array of short goal strings
- keywords: array of 4–12 short discovery phrases (1–3 words) that Reddit users actually type. Good: "self promotion", "getting banned", "which subreddit", "lead generation". Bad: long product slogans like "reddit engagement assistant" or "promote product on reddit".
- tone: short tone line
- persona: short persona notes
- avoid: string or list of things not to say or do in comments
"""


def split_ready_marker(text: str) -> tuple[str, bool]:
    """Strip the end-of-interview marker. Returns (visible text, ready)."""
    if not (text or "").strip():
        return (text or "").rstrip(), False
    stripped = text.rstrip()
    lines = stripped.splitlines()
    if lines and lines[-1].strip() == READY_MARKER:
        body = "\n".join(lines[:-1]).rstrip()
        return body, True
    if READY_MARKER in stripped:
        return stripped.replace(READY_MARKER, "").rstrip(), True
    return stripped, False


def visible_interview_stream(buffer: str) -> str:
    """Hide a trailing READY_FOR_WORKSPACE (including a partial last line) while streaming."""
    visible, ready = split_ready_marker(buffer)
    if ready:
        return visible
    if "\n" in buffer:
        head, last = buffer.rsplit("\n", 1)
        if last and READY_MARKER.startswith(last):
            return head
        return buffer
    if buffer and READY_MARKER.startswith(buffer) and len(buffer) >= 4:
        return ""
    return buffer


def opening_message(purpose: str) -> dict[str, str]:
    text = OPENING_PROMPTS.get(purpose) or OPENING_PROMPTS["custom"]
    return {"role": "assistant", "content": text}


def _transcript(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in messages:
        role = item.get("role") or "user"
        content = (item.get("content") or "").strip()
        if not content:
            continue
        if role == "system":
            lines.append(f"[context]\n{content}")
        else:
            lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def iter_interview_reply(
    llm_config: LLMConfig,
    *,
    purpose: str,
    messages: list[dict[str, Any]],
) -> Iterator[str]:
    system = _SYSTEM_BY_PURPOSE.get(purpose) or _SYSTEM_BY_PURPOSE["custom"]
    chat: list[dict[str, str]] = [{"role": "system", "content": system}]
    for item in messages:
        role = item.get("role") or "user"
        content = (item.get("content") or "").strip()
        if not content:
            continue
        if role == "system":
            chat.append({"role": "system", "content": content})
        elif role == "assistant":
            chat.append({"role": "assistant", "content": content})
        else:
            chat.append({"role": "user", "content": content})

    client = OpenAI(base_url=llm_config.base_url, api_key=llm_config.api_key)
    stream = client.chat.completions.create(
        model=llm_config.model,
        messages=chat,
        temperature=0.7,
        stream=True,
    )
    for chunk in stream:
        content = chunk.choices[0].delta.content if chunk.choices else None
        if content:
            yield content


def attach_user_turn(messages: list[dict[str, Any]], text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Append the user message and any URL research notes. Returns (messages, research results)."""
    updated = list(messages)
    updated.append({"role": "user", "content": text.strip()})
    urls = extract_urls(text)
    researched = research_urls(urls) if urls else []
    if researched:
        bits: list[str] = []
        for item in researched:
            if item.get("ok"):
                bits.append(
                    f"Fetched {item['url']}\nTitle: {item.get('title') or '(none)'}\n"
                    f"Excerpt:\n{item.get('excerpt') or ''}"
                )
            else:
                bits.append(f"Could not fetch {item['url']}: {item.get('error')}")
        updated.append(
            {
                "role": "system",
                "content": "Page research from links the user pasted:\n\n" + "\n\n".join(bits),
            }
        )
    return updated, researched


def extract_briefing(
    llm_config: LLMConfig,
    *,
    purpose: str,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    prompt = EXTRACT_PROMPT.format(purpose=purpose, transcript=_transcript(messages))
    client = OpenAI(base_url=llm_config.base_url, api_key=llm_config.api_key)
    response = client.chat.completions.create(
        model=llm_config.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    raw = response.choices[0].message.content if response.choices else None
    if not raw or not raw.strip():
        raise RuntimeError("LLM returned an empty briefing")
    data = _parse_briefing_json(raw)
    briefing = str(data.get("briefing") or "").strip()
    if not briefing:
        briefing = _fallback_briefing(messages)
    name = str(data.get("name") or "").strip() or _name_from_briefing(briefing) or "Workspace"
    goals = _string_list(data.get("goals"))
    keywords = _string_list(data.get("keywords"))
    return {
        "name": name,
        "briefing": briefing,
        "goals": goals,
        "keywords": keywords,
        "tone": str(data.get("tone") or "").strip(),
        "persona": str(data.get("persona") or "").strip(),
        "avoid": format_text_list(data.get("avoid") or ""),
    }


def complete_workspace(
    llm_config: LLMConfig,
    *,
    purpose: str,
    messages: list[dict[str, Any]],
    count: int = 12,
) -> dict[str, Any]:
    briefing = extract_briefing(llm_config, purpose=purpose, messages=messages)
    goals_text = "; ".join(briefing["goals"])
    try:
        subreddits = suggest_subreddits(
            llm_config,
            product=briefing["briefing"],
            tone=briefing.get("tone") or "",
            persona=briefing.get("persona") or "",
            count=count,
            purpose=purpose,
            goals=briefing.get("goals") or [],
        )
    except Exception:
        logger.exception("subreddit suggestion during interview complete failed")
        subreddits = []
    briefing["subreddits"] = subreddits
    briefing["goals_text"] = goals_text
    return briefing


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [part.strip() for part in re.split(r"[\n,]", value) if part.strip()]
        return items
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _parse_briefing_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM did not return a briefing object")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM briefing payload was not an object")
    return data


def _fallback_briefing(messages: list[dict[str, Any]]) -> str:
    user_bits = [
        str(item.get("content") or "").strip()
        for item in messages
        if item.get("role") == "user" and str(item.get("content") or "").strip()
    ]
    return "\n\n".join(user_bits)[:2000]
