"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AppShell } from "@/components/shell/app-shell";
import { getConfig } from "@/lib/api";
import { PageStatus } from "@/components/ui/page-status";

export function ConditionalShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isOnboarding = pathname.startsWith("/onboarding");
  const [allowed, setAllowed] = useState(isOnboarding);

  useEffect(() => {
    if (isOnboarding) {
      setAllowed(true);
      return;
    }

    let cancelled = false;
    getConfig()
      .then((config) => {
        if (cancelled) return;
        if (!config.onboarding_complete) {
          router.replace("/onboarding");
          return;
        }
        setAllowed(true);
      })
      .catch(() => {
        if (!cancelled) router.replace("/onboarding");
      });

    return () => {
      cancelled = true;
    };
  }, [isOnboarding, router]);

  if (isOnboarding) {
    return <>{children}</>;
  }

  if (!allowed) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas">
        <PageStatus kind="loading" message="Opening Reddit Copilot…" />
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
