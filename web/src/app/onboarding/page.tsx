import { Suspense } from "react";
import { OnboardingFlow } from "@/components/onboarding/onboarding-flow";
import { Mascot } from "@/components/ui/mascot";

export default function OnboardingPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-surface">
          <Mascot mood="thinking" />
        </div>
      }
    >
      <OnboardingFlow />
    </Suspense>
  );
}
