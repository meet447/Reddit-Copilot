import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const api = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";
  try {
    const res = await fetch(`${api}/api/config`, { cache: "no-store" });
    if (res.ok) {
      const config = (await res.json()) as { onboarding_complete?: boolean };
      if (!config.onboarding_complete) {
        redirect("/onboarding");
      }
    }
  } catch {
    // API down — still show queue
  }
  redirect("/queue");
}
