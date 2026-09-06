"use client";

import { usePathname } from "next/navigation";
import { AppShell } from "@/components/shell/app-shell";

export function ConditionalShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname.startsWith("/onboarding")) {
    return <>{children}</>;
  }
  return <AppShell>{children}</AppShell>;
}
