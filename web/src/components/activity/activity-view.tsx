"use client";

import { useCallback, useEffect, useState } from "react";
import { getActivity, type ActivityEvent } from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";
import { ApiDownNotice } from "@/components/ui/notice";
import { Surface } from "@/components/ui/surface";
import { PageStatus } from "@/components/ui/page-status";

export function ActivityView() {
  const [items, setItems] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [apiDown, setApiDown] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getActivity(100);
      setItems(data);
      setApiDown(false);
    } catch {
      setApiDown(true);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex h-full flex-col">
      <header className="shrink-0 border-b border-line px-6 py-4">
        <h1 className="text-[22px] font-semibold text-ink tracking-tight">
          Activity
        </h1>
        <p className="mt-0.5 text-[13px] text-ink-3">
          Audit log of drafts, edits, and posts.
        </p>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {apiDown && (
          <div className="mb-4">
            <ApiDownNotice />
          </div>
        )}

        {loading ? (
          <PageStatus kind="loading" message="Loading activity…" />
        ) : items.length === 0 ? (
          <PageStatus
            kind="empty"
            message="No activity yet. Actions will show up here as you review and post."
          />
        ) : (
          <ul className="space-y-2">
            {items.map((item) => (
              <li key={item.id}>
                <Surface
                  tone="surface"
                  radius="card"
                  elevation="soft"
                  className="flex items-start justify-between gap-4 p-4 squircle"
                >
                  <div>
                    <p className="text-[14px] font-medium text-ink">
                      {item.action.replaceAll("_", " ")}
                    </p>
                    <p className="mt-0.5 font-mono text-[12px] text-ink-3">
                      {[
                        item.draft_id != null ? `draft ${item.draft_id}` : null,
                        item.post_id ? `post ${item.post_id}` : null,
                      ]
                        .filter(Boolean)
                        .join(" · ") || "—"}
                    </p>
                    {item.detail && (
                      <p className="mt-1 text-[13px] text-ink-2">
                        {typeof item.detail === "string"
                          ? item.detail
                          : Object.entries(item.detail)
                              .map(([key, value]) => `${key}: ${String(value)}`)
                              .join(" · ")}
                      </p>
                    )}
                  </div>
                  <time className="shrink-0 text-[12px] text-ink-3">
                    {formatRelativeTime(item.created_at)}
                  </time>
                </Surface>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
