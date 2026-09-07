"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getDrafts,
  getStatus,
  type Draft,
  type DraftStatus,
} from "@/lib/api";
import { ApiDownNotice } from "@/components/ui/notice";
import { PageStatus } from "@/components/ui/page-status";
import { DraftCard, FilterChips } from "@/components/queue/draft-card";

export function QueueView() {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [filter, setFilter] = useState<DraftStatus | "all">("pending");
  const [counts, setCounts] = useState<Partial<Record<DraftStatus, number>>>(
    {},
  );
  const [apiDown, setApiDown] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [draftList, status] = await Promise.all([
        getDrafts(filter),
        getStatus(),
      ]);
      setDrafts(draftList);
      setCounts(status.counts);
      setApiDown(false);
    } catch {
      setApiDown(true);
      setDrafts([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex h-full flex-col">
      <header className="shrink-0 border-b border-line px-6 py-4">
        <h1 className="text-[22px] font-semibold text-ink tracking-tight">
          Review queue
        </h1>
        <p className="mt-0.5 text-[13px] text-ink-3">
          Draft a reply, edit it, then post or schedule. Reject anything that
          doesn’t fit.
        </p>
      </header>

      <div className="flex shrink-0 flex-col gap-4 border-b border-line px-6 py-4">
        {apiDown && <ApiDownNotice />}
        <FilterChips active={filter} onChange={setFilter} counts={counts} />
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading ? (
          <PageStatus kind="loading" message="Loading the queue…" />
        ) : drafts.length === 0 ? (
          <PageStatus
            kind="empty"
            message="Nothing to review yet. Add threads from Discover."
          />
        ) : (
          <div className="grid gap-3 motion-safe:animate-fade-in">
            {drafts.map((draft) => (
              <DraftCard key={draft.id} draft={draft} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
