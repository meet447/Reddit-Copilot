"use client";

import Link from "next/link";
import {
  pollOutcomes,
  type Draft,
} from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import {
  IconChevronLeft,
  IconExternal,
  IconRefresh,
} from "@/components/ui/icons";
import { Notice } from "@/components/ui/notice";
import { Pill } from "@/components/ui/pill";
import { Surface } from "@/components/ui/surface";
import { SubredditName } from "@/components/ui/subreddit-name";
import { useState } from "react";

export function PostedDetailView({
  draft,
  onDraftChange,
}: {
  draft: Draft;
  onDraftChange: (draft: Draft) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const polled = Boolean(draft.outcomes_polled_at);
  const score = draft.outcome_score;
  const replies = draft.outcome_replies ?? 0;
  const removed = Boolean(draft.outcome_removed);

  async function handleRefresh() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await pollOutcomes();
      const { getDraft } = await import("@/lib/api");
      const updated = await getDraft(draft.id);
      onDraftChange(updated);
      setMessage(
        result.outcomes > 0
          ? "Outcome updated from Reddit."
          : "Nothing new to poll yet.",
      );
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not refresh outcomes. Is the API running?",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-line px-6 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <Link href="/queue?status=posted">
            <IconButton label="Back to posted">
              <IconChevronLeft size={18} />
            </IconButton>
          </Link>
          <div className="min-w-0">
            <SubredditName name={draft.subreddit} />
            <h1 className="truncate text-[18px] font-semibold tracking-tight text-ink">
              {draft.title}
            </h1>
          </div>
          <Pill status="posted" />
          {removed && <Pill tone="clay">Removed</Pill>}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            leading={<IconRefresh size={14} />}
            loading={busy}
            onClick={() => void handleRefresh()}
          >
            Refresh
          </Button>
          {draft.permalink && (
            <Button
              variant="secondary"
              size="sm"
              leading={<IconExternal size={14} />}
              onClick={() =>
                window.open(draft.permalink!, "_blank", "noopener,noreferrer")
              }
            >
              Open on Reddit
            </Button>
          )}
        </div>
      </header>

      <div className="flex min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-8">
          {message && <Notice tone="sage">{message}</Notice>}
          {error && <Notice tone="clay">{error}</Notice>}

          <section>
            <p className="mb-3 text-[12px] font-medium text-ink-3">How it did</p>
            <div className="grid grid-cols-3 gap-3">
              <Surface tone="surface" radius="card" elevation="soft" className="p-4">
                <p className="text-[11px] font-medium uppercase tracking-wide text-ink-3">
                  Score
                </p>
                <p className="mt-1 font-mono text-[28px] font-semibold leading-none tracking-tight text-ink">
                  {polled ? (score ?? "—") : "—"}
                </p>
              </Surface>
              <Surface tone="surface" radius="card" elevation="soft" className="p-4">
                <p className="text-[11px] font-medium uppercase tracking-wide text-ink-3">
                  Replies
                </p>
                <p className="mt-1 font-mono text-[28px] font-semibold leading-none tracking-tight text-ink">
                  {polled ? replies : "—"}
                </p>
              </Surface>
              <Surface tone="surface" radius="card" elevation="soft" className="p-4">
                <p className="text-[11px] font-medium uppercase tracking-wide text-ink-3">
                  Status
                </p>
                <p className="mt-2 text-[15px] font-semibold text-ink">
                  {!polled
                    ? "Not polled"
                    : removed
                      ? "Removed"
                      : "Live"}
                </p>
              </Surface>
            </div>
            <p className="mt-3 text-[12px] text-ink-3">
              {polled && draft.outcomes_polled_at
                ? `Last checked ${formatRelativeTime(draft.outcomes_polled_at)}`
                : "Hit Refresh to pull score and replies from Reddit."}
            </p>
          </section>

          <section>
            <p className="mb-2 text-[12px] font-medium text-ink-3">
              What you posted
            </p>
            <Surface tone="surface" radius="card" elevation="soft" className="p-5">
              <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-ink-2">
                {draft.body.trim() || "—"}
              </p>
            </Surface>
          </section>

          <section>
            <div className="mb-2 flex items-center justify-between gap-2">
              <p className="text-[12px] font-medium text-ink-3">Thread</p>
              {(draft.post_permalink || draft.url) && (
                <a
                  href={draft.post_permalink || draft.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-[12px] text-ink-3 hover:text-ink"
                >
                  Open thread
                  <IconExternal size={12} />
                </a>
              )}
            </div>
            <Surface tone="raised" radius="card" className="p-5">
              <p className="text-[15px] font-semibold tracking-tight text-ink">
                {draft.title}
              </p>
              {draft.selftext && (
                <p className="mt-3 max-h-48 overflow-y-auto whitespace-pre-wrap text-[14px] leading-relaxed text-ink-2">
                  {draft.selftext}
                </p>
              )}
            </Surface>
          </section>
        </div>
      </div>
    </div>
  );
}
