import { cn } from "@/lib/cn";

type NoticeTone = "neutral" | "accent" | "honey" | "sage" | "clay";

const toneClasses: Record<NoticeTone, string> = {
  neutral: "bg-well text-ink-2",
  accent: "bg-accent-50 text-ink-2",
  honey: "bg-honey-50 text-ink-2",
  sage: "bg-sage-50 text-ink-2",
  clay: "bg-clay-50 text-ink-2",
};

export function Notice({
  tone = "neutral",
  className,
  children,
}: {
  tone?: NoticeTone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-field px-4 py-3 text-[14px] leading-relaxed squircle",
        toneClasses[tone],
        className,
      )}
      role="status"
    >
      {children}
    </div>
  );
}

export function ApiDownNotice() {
  return (
    <Notice tone="clay">
      Can&apos;t reach the API. Start the server with{" "}
      <code className="font-mono text-[13px] text-ink">rcopilot serve</code>{" "}
      and refresh.
    </Notice>
  );
}
