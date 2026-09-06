import { cn } from "@/lib/cn";

export function AsciiAccent({
  className,
  width = "full",
}: {
  className?: string;
  width?: "full" | "short";
}) {
  const pattern =
    width === "short"
      ? "·  ·  ·  ·  ·  ·  ·  ·"
      : "·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·";

  return (
    <div
      aria-hidden="true"
      className={cn(
        "font-mono text-[10px] tracking-[0.3em] text-ink-4 select-none overflow-hidden whitespace-nowrap",
        className,
      )}
    >
      {pattern}
    </div>
  );
}
