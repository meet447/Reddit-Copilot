import { cn } from "@/lib/cn";

export function Kbd({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <kbd
      className={cn(
        "inline-flex min-w-[1.5rem] items-center justify-center rounded-control bg-well px-1.5 py-0.5 font-mono text-[11px] text-ink-2 shadow-soft squircle",
        className,
      )}
    >
      {children}
    </kbd>
  );
}

export function KeyCombo({
  keys,
  className,
}: {
  keys: string[];
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      {keys.map((key, i) => (
        <span key={key} className="inline-flex items-center gap-1">
          {i > 0 && <span className="text-[11px] text-ink-4">+</span>}
          <Kbd>{key}</Kbd>
        </span>
      ))}
    </span>
  );
}
