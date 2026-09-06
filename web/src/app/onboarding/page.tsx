import { Suspense } from "react";
import { OnboardingFlow } from "@/components/onboarding/onboarding-flow";
import { PageStatus } from "@/components/ui/page-status";

export default function OnboardingPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-surface">
          <PageStatus kind="loading" message="Getting things ready…" />
        </div>
      }
    >
      <OnboardingFlow />
    </Suspense>
  );
}
