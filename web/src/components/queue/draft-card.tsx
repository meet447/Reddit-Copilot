"use client";

import Link from "next/link";
import { cn } from "@/lib/cn";
import type { Draft, DraftStatus } from "@/lib/api";
import { formatRelativeTime, truncate } from "@/lib/format";
import { Pill } from "@/components/ui/pill";
import { Surface } from "@/components/ui/surface";

export function DraftCard({ draft }: { draft: Draft }) {
  return (
    <Link href={`/queue/${draft.id}`} className="block group">
      <Surface
        tone="surface"
        radius="card"
        elevation="soft"
        interactive
        className={cn(
          "p-4 transition-all duration-200 ease-[var(--ease-soft)]",
          "group-focus-visible:ring-2 group-focus-visible:ring-accent-200",
        )}
      >
        <div className="flex items-start justify-between gap-3 mb-2">
          <div className="min-w-0">
            <p className="text-[12px] text-ink-3 font-mono">
              {draft.kind === "submission" ? "Post · " : ""}
              r/{draft.subreddit}
            </p>
            <h3 className="mt-0.5 text-[15px] font-semibold text-ink tracking-tight leading-snug truncate">
              {draft.title}
            </h3>
          </div>
          <Pill status={draft.status} />
        </div>
        <p className="text-[14px] text-ink-2 leading-relaxed line-clamp-2">
          {draft.body.trim()
            ? truncate(draft.body, 180)
            : draft.kind === "submission"
              ? "No body yet — open to edit."
              : "No reply yet — open and click Draft."}
        </p>
        {draft.status === "posted" && draft.outcomes_polled_at && (
          <p className="mt-2 text-[12px] text-ink-3">
            {draft.outcome_removed
              ? "Removed on Reddit"
              : `${draft.outcome_score ?? "—"} pts · ${draft.outcome_replies ?? 0} ${(draft.outcome_replies ?? 0) === 1 ? "reply" : "replies"}`}
          </p>
        )}
        <p className="mt-3 text-[12px] text-ink-3">
          {formatRelativeTime(draft.updated_at)}
        </p>
      </Surface>
    </Link>
  );
}

export const FILTER_STATUSES: DraftStatus[] = [
  "pending",
  "scheduled",
  "posted",
  "error",
];

export const FILTER_LABELS: Record<DraftStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  scheduled: "Scheduled",
  posted: "Posted",
  rejected: "Rejected",
  error: "Error",
};

export function FilterChips({
  active,
  onChange,
  counts,
}: {
  active: DraftStatus | "all";
  onChange: (status: DraftStatus | "all") => void;
  counts?: Partial<Record<DraftStatus, number>>;
}) {
  const chips: { key: DraftStatus | "all"; label: string }[] = [
    { key: "all", label: "All" },
    ...FILTER_STATUSES.map((s) => ({
      key: s,
      label: FILTER_LABELS[s],
    })),
  ];

  return (
    <div className="flex flex-wrap gap-2">
      {chips.map(({ key, label }) => {
        const selected = active === key;
        const count = key === "all" ? undefined : counts?.[key];
        return (
          <button
            key={key}
            type="button"
            onClick={() => onChange(key)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] font-medium transition-colors duration-200 ease-[var(--ease-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-200 squircle",
              selected
                ? "bg-ink text-white"
                : "bg-well text-ink-2 hover:bg-well-2 hover:text-ink",
            )}
          >
            {label}
            {count !== undefined && count > 0 && (
              <span
                className={cn(
                  "text-[11px]",
                  selected ? "text-white/70" : "text-ink-3",
                )}
              >
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
