export type DraftStatus =
  | "pending"
  | "approved"
  | "scheduled"
  | "posted"
  | "rejected"
  | "error";

export interface TopComment {
  body: string;
  score: number;
}

export interface Draft {
  id: number;
  post_id: string;
  account_name: string;
  body: string;
  status: DraftStatus;
  error: string | null;
  permalink: string | null;
  created_at: string;
  updated_at: string;
  run_at: string | null;
  subreddit: string;
  title: string;
  selftext: string;
  url: string;
  post_permalink: string;
  created_utc: number;
  top_comments: TopComment[];
  relevance_score: number;
  score_reasons: string[];
}

export interface Post {
  id: string;
  subreddit: string;
  title: string;
  selftext: string;
  url: string;
  permalink: string;
  created_utc: number;
  top_comments: TopComment[];
  relevance_score: number;
  score_reasons: string[];
  keywords_matched: string[];
  skipped: boolean;
}

export interface StatusCounts {
  counts: Record<DraftStatus, number>;
  config_loaded: boolean;
}

export interface ActivityEvent {
  id: number;
  created_at: string;
  action: string;
  draft_id: number | null;
  post_id: string | null;
  detail: Record<string, unknown> | string | null;
}

export interface AccountPublic {
  name: string;
  user_agent: string;
  has_username: boolean;
  has_oauth: boolean;
  connected_username: string;
  has_client_id: boolean;
}

export interface AppConfig {
  subreddits: string[];
  listing: string;
  fetch_limit: number;
  db_path: string;
  accounts: AccountPublic[];
  llm: {
    base_url: string;
    model: string;
  };
  rate_limits: {
    min_interval_seconds: number;
    daily_cap: number;
  };
  voice: {
    product: string;
    tone: string;
    persona: string;
    avoid: string;
  };
  discovery: {
    keywords: string[];
    min_score: number;
    search_queries?: string[];
  };
  worker: {
    interval_seconds: number;
  };
  onboarding_complete: boolean;
  onboarding_step: number;
  has_credentials: boolean;
  has_oauth: boolean;
  has_api_key: boolean;
  oauth_redirect_uri: string;
  frontend_url: string;
  prompt_template?: string;
}

export type ConfigUpdate = {
  subreddits?: string[];
  listing?: string;
  fetch_limit?: number;
  voice?: Partial<AppConfig["voice"]>;
  discovery?: Partial<AppConfig["discovery"]>;
  rate_limits?: Partial<AppConfig["rate_limits"]>;
  worker?: Partial<AppConfig["worker"]>;
  accounts?: { name: string; user_agent: string }[];
  llm?: { base_url?: string; model?: string };
  prompt_template?: string;
  onboarding_complete?: boolean;
  onboarding_step?: number;
};

export type SecretsUpdate = {
  reddit_client_id?: string;
  reddit_client_secret?: string;
  llm_api_key?: string;
  account_name?: string;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    cache: "no-store",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const data = (await res.json()) as { error?: string; detail?: string };
      if (data.error) message = data.error;
      else if (typeof data.detail === "string") message = data.detail;
    } catch {
      // ignore parse errors
    }
    throw new ApiError(message, res.status);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function checkHealth(): Promise<boolean> {
  try {
    await request<{ ok: boolean }>("/api/health");
    return true;
  } catch {
    return false;
  }
}

export function getStatus(): Promise<StatusCounts> {
  return request<StatusCounts>("/api/status");
}

export async function getDrafts(
  status: DraftStatus | "all" = "pending",
): Promise<Draft[]> {
  const data = await request<{ drafts: Draft[] }>(
    `/api/drafts?status=${status}`,
  );
  return data.drafts;
}

export function getDraft(id: number): Promise<Draft> {
  return request<Draft>(`/api/drafts/${id}`);
}

export function patchDraft(id: number, body: string): Promise<Draft> {
  return request<Draft>(`/api/drafts/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ body }),
  });
}

export function approveDraft(id: number, body?: string): Promise<Draft> {
  return request<Draft>(`/api/drafts/${id}/approve`, {
    method: "POST",
    body: JSON.stringify(body !== undefined ? { body } : {}),
  });
}

export function rejectDraft(id: number): Promise<Draft> {
  return request<Draft>(`/api/drafts/${id}/reject`, { method: "POST" });
}

export function regenerateDraft(id: number): Promise<Draft> {
  return request<Draft>(`/api/drafts/${id}/regenerate`, { method: "POST" });
}

export async function postDraft(id: number): Promise<Draft> {
  const data = await request<{ draft: Draft }>(`/api/drafts/${id}/post`, {
    method: "POST",
  });
  return data.draft;
}

export function scheduleDraft(id: number, runAt: string): Promise<Draft> {
  return request<Draft>(`/api/drafts/${id}/schedule`, {
    method: "POST",
    body: JSON.stringify({ run_at: runAt }),
  });
}

export function unscheduleDraft(id: number): Promise<Draft> {
  return request<Draft>(`/api/drafts/${id}/unschedule`, { method: "POST" });
}

export async function getPosts(params?: {
  undrafted?: boolean;
  skipped?: boolean;
}): Promise<Post[]> {
  const search = new URLSearchParams();
  if (params?.undrafted !== undefined)
    search.set("undrafted", String(params.undrafted));
  if (params?.skipped !== undefined)
    search.set("skipped", String(params.skipped));
  const qs = search.toString();
  const data = await request<{ posts: Post[] }>(
    `/api/posts${qs ? `?${qs}` : ""}`,
  );
  return data.posts;
}

export function draftPost(id: string): Promise<Draft> {
  return request<Draft>(`/api/posts/${id}/draft`, { method: "POST" });
}

export function skipPost(id: string): Promise<Post> {
  return request<Post>(`/api/posts/${id}/skip`, { method: "POST" });
}

export function fetchThreads(): Promise<{ fetched: number }> {
  return request<{ fetched: number }>("/api/actions/fetch", { method: "POST" });
}

export function generateDrafts(): Promise<{ drafted: number }> {
  return request<{ drafted: number }>("/api/actions/draft", { method: "POST" });
}

export function runOnce(): Promise<{
  fetched: number;
  drafted: number;
  posted: number;
}> {
  return request("/api/actions/run-once", { method: "POST" });
}

export async function getSchedule(): Promise<Draft[]> {
  const data = await request<{ drafts: Draft[] }>("/api/schedule");
  return data.drafts;
}

export async function getActivity(limit = 50): Promise<ActivityEvent[]> {
  const data = await request<{ events: ActivityEvent[] }>(
    `/api/activity?limit=${limit}`,
  );
  return data.events;
}

export function getConfig(): Promise<AppConfig> {
  return request<AppConfig>("/api/config");
}

export function putConfig(config: ConfigUpdate): Promise<AppConfig> {
  return request<AppConfig>("/api/config", {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

export function putSecrets(secrets: SecretsUpdate): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/secrets", {
    method: "PUT",
    body: JSON.stringify(secrets),
  });
}

export function startOAuth(
  next = "/onboarding",
  accountName = "default",
): Promise<{ authorize_url: string; redirect_uri: string }> {
  return request("/api/oauth/start", {
    method: "POST",
    body: JSON.stringify({ next, account_name: accountName }),
  });
}
