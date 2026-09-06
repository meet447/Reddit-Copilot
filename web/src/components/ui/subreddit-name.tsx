"use client";

import { useEffect, useMemo, useState } from "react";
import { getSubredditIcons } from "@/lib/api";
import { cn } from "@/lib/cn";

/** Module-level cache so tabs share resolved icons. */
const iconCache = new Map<string, string | null>();
const pending = new Set<string>();
let flushTimer: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();

function normalizeName(name: string): string {
  return name.trim().replace(/^r\//i, "");
}

function notify() {
  for (const listener of listeners) listener();
}

function scheduleFetch(names: string[]) {
  for (const raw of names) {
    const cleaned = normalizeName(raw);
    if (!cleaned) continue;
    const key = cleaned.toLowerCase();
    if (iconCache.has(key) || pending.has(key)) continue;
    pending.add(key);
  }
  if (!pending.size || flushTimer) return;
  flushTimer = setTimeout(() => {
    flushTimer = null;
    const batch = Array.from(pending);
    pending.clear();
    void getSubredditIcons(batch)
      .then((data) => {
        for (const [name, url] of Object.entries(data.icons ?? {})) {
          iconCache.set(name.toLowerCase(), url);
        }
        for (const name of batch) {
          if (!iconCache.has(name)) iconCache.set(name, null);
        }
        notify();
      })
      .catch(() => {
        for (const name of batch) {
          if (!iconCache.has(name)) iconCache.set(name, null);
        }
        notify();
      });
  }, 40);
}

export function useSubredditIcons(names: string[]): Record<string, string | null> {
  const cleaned = useMemo(
    () => Array.from(new Set(names.map(normalizeName).filter(Boolean))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [names.join("|")],
  );
  const depsKey = cleaned.map((n) => n.toLowerCase()).sort().join(",");
  const [, setTick] = useState(0);

  useEffect(() => {
    const onUpdate = () => setTick((t) => t + 1);
    listeners.add(onUpdate);
    scheduleFetch(cleaned);
    return () => {
      listeners.delete(onUpdate);
    };
  }, [depsKey, cleaned]);

  const map: Record<string, string | null> = {};
  for (const name of cleaned) {
    map[name] = iconCache.get(name.toLowerCase()) ?? null;
  }
  return map;
}

export function SubredditName({
  name,
  className,
  prefix,
  size = "sm",
  mono = true,
}: {
  name: string;
  className?: string;
  /** Optional text before the name, e.g. "Post · " */
  prefix?: string;
  size?: "sm" | "md";
  mono?: boolean;
}) {
  const cleaned = normalizeName(name);
  const icons = useSubredditIcons(cleaned ? [cleaned] : []);
  const iconUrl = cleaned ? icons[cleaned] : null;
  const px = size === "md" ? 20 : 16;
  const letter = (cleaned[0] || "?").toUpperCase();

  return (
    <span
      className={cn(
        "inline-flex min-w-0 items-center gap-1.5",
        mono && "font-mono",
        size === "sm" ? "text-[12px] text-ink-3" : "text-[14px] text-ink-2",
        className,
      )}
    >
      <span
        className="relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-well text-[10px] font-medium text-ink-3"
        style={{ width: px, height: px }}
        aria-hidden
      >
        {iconUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={iconUrl}
            alt=""
            width={px}
            height={px}
            className="h-full w-full object-cover"
            loading="lazy"
            referrerPolicy="no-referrer"
          />
        ) : (
          letter
        )}
      </span>
      <span className="truncate">
        {prefix}
        r/{cleaned}
      </span>
    </span>
  );
}
