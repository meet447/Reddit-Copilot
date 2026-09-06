"""Fetch user-pasted URLs for project briefing (not Reddit scraping)."""

from __future__ import annotations

import re
import html as html_lib
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
_TAG_RE = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

MAX_CHARS = 4000
FETCH_TIMEOUT = 8
USER_AGENT = "RedditCopilot/1.0 (workspace briefing; user-pasted URL)"


def extract_urls(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in _URL_RE.findall(text or ""):
        cleaned = match.rstrip(".,;:!?")
        key = cleaned.lower()
        if key in seen:
            continue
        if _is_reddit_url(cleaned):
            continue
        seen.add(key)
        found.append(cleaned)
    return found


def _is_reddit_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "reddit.com" or host.endswith(".reddit.com") or host == "redd.it"


def fetch_url_excerpt(url: str, *, max_chars: int = MAX_CHARS) -> dict[str, Any]:
    """Download a user-pasted page and return title + plain-text excerpt."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return {"url": url, "ok": False, "error": "Only http(s) links can be read."}
    if _is_reddit_url(url):
        return {"url": url, "ok": False, "error": "Reddit links are read via the Reddit API, not fetched."}

    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain"})
    try:
        with urlopen(request, timeout=FETCH_TIMEOUT) as response:
            raw = response.read(200_000)
            charset = response.headers.get_content_charset() or "utf-8"
    except HTTPError as exc:
        return {"url": url, "ok": False, "error": f"Could not read that page ({exc.code})."}
    except URLError as exc:
        return {"url": url, "ok": False, "error": f"Could not reach that page ({exc.reason})."}
    except TimeoutError:
        return {"url": url, "ok": False, "error": "That page took too long to respond."}
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "ok": False, "error": str(exc)}

    try:
        html = raw.decode(charset, errors="replace")
    except LookupError:
        html = raw.decode("utf-8", errors="replace")

    title_match = _TITLE_RE.search(html)
    title = html_lib.unescape(_WHITESPACE_RE.sub(" ", title_match.group(1))).strip() if title_match else ""
    text = _TAG_RE.sub(" ", html)
    text = html_lib.unescape(text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return {
        "url": url,
        "ok": True,
        "title": title or parsed.netloc,
        "excerpt": text,
        "error": None,
    }


def research_urls(urls: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for url in urls[:5]:
        results.append(fetch_url_excerpt(url))
    return results
