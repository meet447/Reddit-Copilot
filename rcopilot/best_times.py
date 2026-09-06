"""Suggest schedule slots from local timezone + subreddit activity hours."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any

# In-memory cache: subreddit -> (expires_at, hours_utc)
_HOUR_CACHE: dict[str, tuple[datetime, list[int]]] = {}
_CACHE_TTL = timedelta(hours=6)

# Tue=1 .. Thu=3 in datetime.weekday()
_FALLBACK_WEEKDAYS = (1, 2, 3)
_FALLBACK_LOCAL_HOURS = (15, 19)


def _tz_from_offset_minutes(offset_minutes: int) -> timezone:
    return timezone(timedelta(minutes=offset_minutes))


def get_cached_hours(subreddit: str) -> list[int] | None:
    key = subreddit.strip().lstrip("r/").lower()
    entry = _HOUR_CACHE.get(key)
    if not entry:
        return None
    expires, hours = entry
    if datetime.now(timezone.utc) >= expires:
        _HOUR_CACHE.pop(key, None)
        return None
    return list(hours)


def set_cached_hours(subreddit: str, hours: list[int]) -> None:
    key = subreddit.strip().lstrip("r/").lower()
    _HOUR_CACHE[key] = (datetime.now(timezone.utc) + _CACHE_TTL, list(hours))


def clear_hour_cache() -> None:
    _HOUR_CACHE.clear()


def _top_hours(hours_utc: list[int], *, count: int = 3) -> list[int]:
    if not hours_utc:
        return []
    counts = Counter(h % 24 for h in hours_utc)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [hour for hour, _ in ranked[:count]]


def _next_occurrence(
    *,
    now_local: datetime,
    hour: int,
    prefer_weekdays: bool,
) -> datetime:
    candidate = now_local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    if prefer_weekdays:
        while candidate.weekday() >= 5:  # Sat/Sun
            candidate += timedelta(days=1)
    return candidate


def _fallback_slots(now_local: datetime, count: int) -> list[datetime]:
    slots: list[datetime] = []
    day = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    # Search forward up to two weeks
    for offset in range(0, 14):
        day_candidate = day + timedelta(days=offset)
        if day_candidate.weekday() not in _FALLBACK_WEEKDAYS:
            continue
        for hour in _FALLBACK_LOCAL_HOURS:
            slot = day_candidate.replace(hour=hour)
            if slot <= now_local:
                continue
            slots.append(slot)
            if len(slots) >= count:
                return slots
    # Absolute fallback: next N evenings
    while len(slots) < count:
        slot = (slots[-1] + timedelta(days=1)) if slots else now_local + timedelta(hours=2)
        slot = slot.replace(minute=0, second=0, microsecond=0)
        slots.append(slot)
    return slots[:count]


def suggest_best_times(
    hours_utc: list[int],
    *,
    now: datetime | None = None,
    tz_offset_minutes: int = 0,
    count: int = 3,
) -> list[dict[str, Any]]:
    """Return upcoming local schedule suggestions.

    Each item: {run_at: ISO UTC, label: str, score: int, hour_utc: int}
    """
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    local_tz: tzinfo = _tz_from_offset_minutes(tz_offset_minutes)
    now_local = now_utc.astimezone(local_tz)

    top = _top_hours(hours_utc, count=max(count, 3))
    slots: list[datetime] = []
    scores: list[int] = []

    if top:
        counts = Counter(h % 24 for h in hours_utc)
        for hour_utc in top:
            # Convert UTC hour peak into a local wall-clock hour by taking
            # "today at that UTC hour" then reading local hour.
            probe = now_utc.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
            local_hour = probe.astimezone(local_tz).hour
            slot = _next_occurrence(
                now_local=now_local,
                hour=local_hour,
                prefer_weekdays=True,
            )
            # Avoid duplicate local slots
            if any(abs((existing - slot).total_seconds()) < 60 for existing in slots):
                slot = _next_occurrence(
                    now_local=slot + timedelta(minutes=1),
                    hour=local_hour,
                    prefer_weekdays=True,
                )
            slots.append(slot)
            scores.append(int(counts.get(hour_utc, 1)))
            if len(slots) >= count:
                break
    else:
        slots = _fallback_slots(now_local, count)
        scores = [1] * len(slots)

    results: list[dict[str, Any]] = []
    for slot, score in zip(slots[:count], scores[:count]):
        utc_slot = slot.astimezone(timezone.utc).replace(microsecond=0)
        hour_12 = slot.strftime("%I").lstrip("0") or "12"
        label = f"{slot.strftime('%a')} {hour_12}:{slot.strftime('%M')} {slot.strftime('%p')}"
        results.append(
            {
                "run_at": utc_slot.isoformat(),
                "label": label,
                "score": score,
                "hour_utc": utc_slot.hour,
            }
        )
    return results
