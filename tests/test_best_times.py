"""Unit tests for best-time suggestion heuristics."""

from __future__ import annotations

from datetime import datetime, timezone

from rcopilot.best_times import (
    clear_hour_cache,
    get_cached_hours,
    set_cached_hours,
    suggest_best_times,
)


def test_suggest_best_times_from_histogram() -> None:
    # Peak at 18:00 UTC; local offset 0 so local hour is 18
    hours = [18] * 20 + [10] * 5 + [22] * 3
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)  # Tuesday
    suggestions = suggest_best_times(hours, now=now, tz_offset_minutes=0, count=3)

    assert len(suggestions) == 3
    assert suggestions[0]["label"]
    assert "run_at" in suggestions[0]
    assert suggestions[0]["score"] >= suggestions[1]["score"]
    # First slot should land on the peak hour locally
    first = datetime.fromisoformat(suggestions[0]["run_at"])
    assert first.hour == 18
    assert first > now


def test_suggest_best_times_fallback_when_empty() -> None:
    now = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)  # Sunday
    suggestions = suggest_best_times([], now=now, tz_offset_minutes=0, count=3)

    assert len(suggestions) == 3
    for item in suggestions:
        slot = datetime.fromisoformat(item["run_at"]).astimezone(timezone.utc)
        local = slot  # offset 0
        assert local.weekday() in (1, 2, 3)  # Tue–Thu
        assert local.hour in (15, 19)
        assert slot > now


def test_hour_cache_roundtrip() -> None:
    clear_hour_cache()
    assert get_cached_hours("Python") is None
    set_cached_hours("r/Python", [12, 18, 18])
    assert get_cached_hours("python") == [12, 18, 18]
    clear_hour_cache()
    assert get_cached_hours("python") is None
