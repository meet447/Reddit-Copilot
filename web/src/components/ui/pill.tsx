import { cn } from "@/lib/cn";
import type { DraftStatus } from "@/lib/api";

type PillTone = "honey" | "sage" | "accent" | "clay" | "muted";

const toneClasses: Record<PillTone, string> = {
  honey: "bg-honey-100 text-ink-2",
  sage: "bg-sage-100 text-ink-2",
  accent: "bg-accent-100 text-ink-2",
  clay: "bg-clay-100 text-ink-2",
  muted: "bg-well text-ink-3",
};

const statusTone: Record<DraftStatus, PillTone> = {
  pending: "honey",
  approved: "sage",
  scheduled: "accent",
  posted: "sage",
  rejected: "muted",
  error: "clay",
};

const statusLabel: Record<DraftStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  scheduled: "Scheduled",
  posted: "Posted",
  rejected: "Rejected",
  error: "Error",
};

export interface PillProps {
  status?: DraftStatus;
  tone?: PillTone;
  dot?: boolean;
  pulse?: boolean;
  children?: React.ReactNode;
  className?: string;
}

export function Pill({
  status,
  tone,
  dot,
  pulse,
  children,
  className,
}: PillProps) {
  const resolvedTone = tone ?? (status ? statusTone[status] : "muted");
  const label = children ?? (status ? statusLabel[status] : null);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] font-medium rounded-control squircle",
        toneClasses[resolvedTone],
        className,
      )}
    >
      {dot && (
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full bg-current",
            pulse && "motion-safe:animate-dot",
          )}
        />
      )}
      {label}
    </span>
  );
}
