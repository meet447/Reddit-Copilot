"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Mascot } from "@/components/ui/mascot";
import { AsciiAccent } from "@/components/ui/ascii-accent";
import { Dots } from "@/components/ui/dots";

export function PageStatus({
  kind,
  message,
  size = 96,
  className,
  children,
}: {
  kind: "loading" | "empty";
  message: string;
  size?: number;
  className?: string;
  children?: ReactNode;
}) {
  const loading = kind === "loading";

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center py-16 text-center motion-safe:animate-rise-in",
        className,
      )}
      role="status"
      aria-live="polite"
      aria-busy={loading}
    >
      {!loading && <AsciiAccent className="mb-4" />}
      <Mascot
        mood={loading ? "thinking" : "sleepy"}
        searching={loading}
        size={size}
        className="mb-4"
      />
      <p className="max-w-sm text-[15px] leading-relaxed text-ink-2">
        {message}
      </p>
      {loading ? <Dots className="mt-4" /> : null}
      {children}
    </div>
  );
}
