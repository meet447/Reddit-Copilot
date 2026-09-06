import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const api = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";
  let onboardingComplete = false;

  try {
    const res = await fetch(`${api}/api/config`, { cache: "no-store" });
    if (res.ok) {
      const config = (await res.json()) as {
        onboarding_complete?: boolean;
        projects?: { id: string }[];
      };
      onboardingComplete =
        Boolean(config.onboarding_complete) &&
        Boolean(config.projects && config.projects.length > 0);
    }
  } catch {
    // API down — send first-run users to onboarding
  }

  redirect(onboardingComplete ? "/queue" : "/onboarding");
}
