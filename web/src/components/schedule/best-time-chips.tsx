"use client";

import { useEffect, useState } from "react";
import {
  getBestTimes,
  type BestTimeSuggestion,
} from "@/lib/api";
import { toDatetimeLocalValue } from "@/lib/format";

export function BestTimeChips({
  subreddit,
  onPick,
}: {
  subreddit: string;
  onPick: (datetimeLocal: string) => void;
}) {
  const [suggestions, setSuggestions] = useState<BestTimeSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const cleaned = subreddit.trim().replace(/^r\//i, "");
    if (!cleaned) {
      setSuggestions([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getBestTimes(cleaned)
      .then((data) => {
        if (!cancelled) setSuggestions(data.suggestions ?? []);
      })
      .catch(() => {
        if (!cancelled) {
          setSuggestions([]);
          setError("Could not load suggestions.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [subreddit]);

  if (!subreddit.trim()) return null;

  return (
    <div className="mt-3 space-y-2">
      <p className="text-[12px] font-medium text-ink-3">Suggested times</p>
      {loading && (
        <p className="text-[12px] text-ink-3">Checking r/{subreddit}…</p>
      )}
      {error && <p className="text-[12px] text-ink-3">{error}</p>}
      {!loading && suggestions.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {suggestions.map((item) => (
            <button
              key={item.run_at}
              type="button"
              onClick={() => onPick(toDatetimeLocalValue(item.run_at))}
              className="rounded-control bg-accent-50 px-2.5 py-1 text-[12px] text-ink-2 transition-colors hover:text-ink"
            >
              {item.label}
              {item.score > 1 ? (
                <span className="ml-1 text-ink-3">· busy</span>
              ) : null}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
