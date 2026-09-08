const apiTarget = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const accept = request.headers.get("accept") || "application/json";
  const upstream = await fetch(`${apiTarget}/api/actions/fetch`, {
    method: "POST",
    cache: "no-store",
    headers: { Accept: accept },
  });

  if (!upstream.body || !accept.includes("text/event-stream")) {
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("Content-Type") || "application/json",
      },
    });
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
