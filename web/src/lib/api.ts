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

export type DraftKind = "comment" | "submission";

export interface DraftVariant {
  id: string;
  label: string;
  body: string;
}

export interface Draft {
  id: number;
  post_id: string | null;
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
  post_permalink: string | null;
  created_utc: number | null;
  top_comments: TopComment[];
  relevance_score: number;
  score_reasons: string[];
  comment_id?: string | null;
  outcome_score?: number | null;
  outcome_replies?: number | null;
  outcome_removed?: boolean;
  outcomes_polled_at?: string | null;
  kind?: DraftKind;
  target_subreddit?: string | null;
  submission_id?: string | null;
  lint_warnings?: { code: string; message: string }[];
  variants?: DraftVariant[];
}

export interface BestTimeSuggestion {
  run_at: string;
  label: string;
  score: number;
  hour_utc: number;
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
  intent_labels: string[];
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
  active_project_id?: string;
  purpose?: ProjectPurpose;
  goals?: string[];
  projects?: ProjectSummary[];
  setup_project?: Project | null;
}

export type ProjectPurpose = "product" | "personal" | "custom";

export interface ProjectSummary {
  id: string;
  name: string;
  purpose: ProjectPurpose;
  complete: boolean;
}

export interface ProjectLink {
  url: string;
  title?: string;
  excerpt?: string;
  ok?: boolean;
  error?: string | null;
}

export interface InterviewMessage {
  role: "assistant" | "user" | "system";
  content: string;
  ready?: boolean;
}

export interface Project {
  id: string;
  name: string;
  purpose: ProjectPurpose;
  briefing: string;
  goals: string[];
  links: ProjectLink[];
  interview_messages: InterviewMessage[];
  tone: string;
  persona: string;
  avoid: string;
  subreddits: string[];
  keywords: string[];
  search_queries: string[];
  complete: boolean;
  setup_step?: number;
  created_at?: string;
  updated_at?: string;
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
  active_project_id?: string;
  purpose?: ProjectPurpose;
  goals?: string[];
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

export function patchDraft(
  id: number,
  body: string,
  title?: string,
): Promise<Draft> {
  return request<Draft>(`/api/drafts/${id}`, {
    method: "PATCH",
    body: JSON.stringify(
      title !== undefined ? { body, title } : { body },
    ),
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

export function generateDraftVariants(id: number): Promise<Draft> {
  return request<Draft>(`/api/drafts/${id}/variants`, { method: "POST" });
}

export function selectDraftVariant(
  id: number,
  variantId: string,
): Promise<Draft> {
  return request<Draft>(`/api/drafts/${id}/select-variant`, {
    method: "POST",
    body: JSON.stringify({ variant_id: variantId }),
  });
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

export function createSubmission(input: {
  subreddit: string;
  title: string;
  body: string;
}): Promise<Draft> {
  return request<Draft>("/api/submissions", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function generateSubmissions(input?: {
  count?: number;
  subreddits?: string[];
}): Promise<{ created: number; drafts: Draft[] }> {
  return request("/api/submissions/generate", {
    method: "POST",
    body: JSON.stringify({ count: input?.count ?? 5, subreddits: input?.subreddits }),
  });
}

export async function streamGenerateSubmissions(
  onDraft: (draft: Draft) => void,
  input?: { count?: number; subreddits?: string[] },
): Promise<{ created: number }> {
  const res = await fetch("/api/submissions/generate", {
    method: "POST",
    cache: "no-store",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      count: input?.count ?? 5,
      subreddits: input?.subreddits,
    }),
  });
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const data = (await res.json()) as { error?: string; detail?: string };
      if (data.error) message = data.error;
      else if (typeof data.detail === "string") message = data.detail;
    } catch {
      // ignore
    }
    throw new ApiError(message, res.status);
  }
  if (!res.body) {
    throw new ApiError("No stream from API", res.status || 500);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let created = 0;
  let received = 0;
  let sawDone = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk
        .split("\n")
        .find((entry) => entry.startsWith("data: "));
      if (!line) continue;
      const payload = JSON.parse(line.slice(6)) as {
        type?: string;
        draft?: Draft;
        created?: number;
        error?: string;
      };
      if (payload.type === "error" || payload.error) {
        throw new ApiError(payload.error || "Generate failed", 400);
      }
      if (payload.type === "draft" && payload.draft) {
        received += 1;
        onDraft(payload.draft);
      }
      if (payload.type === "done") {
        created = payload.created ?? received;
        sawDone = true;
      }
    }
  }

  if (!sawDone) {
    throw new ApiError("Generate ended before ideas finished", 500);
  }
  return { created };
}

export function suggestSubreddits(input?: {
  product?: string;
  tone?: string;
  persona?: string;
  count?: number;
  purpose?: ProjectPurpose;
  goals?: string[];
}): Promise<{ subreddits: string[] }> {
  return request("/api/subreddits/suggest", {
    method: "POST",
    body: JSON.stringify({
      product: input?.product,
      tone: input?.tone,
      persona: input?.persona,
      count: input?.count ?? 12,
      purpose: input?.purpose,
      goals: input?.goals,
    }),
  });
}

export function getSubredditIcons(
  names: string[],
): Promise<{ icons: Record<string, string | null> }> {
  const cleaned = names
    .map((n) => n.trim().replace(/^r\//i, ""))
    .filter(Boolean);
  if (!cleaned.length) return Promise.resolve({ icons: {} });
  const search = new URLSearchParams();
  search.set("names", cleaned.join(","));
  return request(`/api/subreddits/icons?${search.toString()}`);
}

export async function getBestTimes(
  subreddit: string,
  opts?: { count?: number },
): Promise<{
  subreddit: string;
  sample_size: number;
  suggestions: BestTimeSuggestion[];
}> {
  const search = new URLSearchParams();
  search.set("subreddit", subreddit);
  search.set("tz_offset_minutes", String(-new Date().getTimezoneOffset()));
  if (opts?.count) search.set("count", String(opts.count));
  return request(`/api/best-times?${search.toString()}`);
}

export async function getPosts(params?: {
  undrafted?: boolean;
  skipped?: boolean;
  label?: string;
}): Promise<Post[]> {
  const search = new URLSearchParams();
  if (params?.undrafted !== undefined)
    search.set("undrafted", String(params.undrafted));
  if (params?.skipped !== undefined)
    search.set("skipped", String(params.skipped));
  if (params?.label) search.set("label", params.label);
  const qs = search.toString();
  const data = await request<{ posts: Post[] }>(
    `/api/posts${qs ? `?${qs}` : ""}`,
  );
  return data.posts;
}

export function draftPost(id: string): Promise<Draft> {
  return request<Draft>(`/api/posts/${id}/draft`, { method: "POST" });
}

export function queuePost(id: string): Promise<Draft> {
  return request<Draft>(`/api/posts/${id}/queue`, { method: "POST" });
}

export async function streamDraftGenerate(
  id: number,
  onDelta: (delta: string) => void,
): Promise<Draft> {
  const res = await fetch(`/api/drafts/${id}/generate`, {
    method: "POST",
    cache: "no-store",
    headers: { Accept: "text/event-stream" },
  });
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const data = (await res.json()) as { error?: string; detail?: string };
      if (data.error) message = data.error;
      else if (typeof data.detail === "string") message = data.detail;
    } catch {
      // ignore
    }
    throw new ApiError(message, res.status);
  }
  if (!res.body) {
    throw new ApiError("No stream from API", res.status || 500);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let draft: Draft | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk
        .split("\n")
        .find((entry) => entry.startsWith("data: "));
      if (!line) continue;
      const payload = JSON.parse(line.slice(6)) as {
        delta?: string;
        done?: boolean;
        draft?: Draft;
        error?: string;
      };
      if (payload.error) throw new ApiError(payload.error, 400);
      if (payload.delta) onDelta(payload.delta);
      if (payload.done && payload.draft) draft = payload.draft;
    }
  }

  if (!draft) {
    throw new ApiError("Stream ended without a draft", 500);
  }
  return draft;
}

export function skipPost(id: string): Promise<Post> {
  return request<Post>(`/api/posts/${id}/skip`, { method: "POST" });
}

export function fetchThreads(): Promise<{ fetched: number }> {
  return request<{ fetched: number }>("/api/actions/fetch", { method: "POST" });
}

export async function streamFetchThreads(
  onPost: (post: Post) => void,
): Promise<{ fetched: number; shown: number }> {
  const res = await fetch("/api/actions/fetch", {
    method: "POST",
    cache: "no-store",
    headers: { Accept: "text/event-stream" },
  });
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const data = (await res.json()) as { error?: string; detail?: string };
      if (data.error) message = data.error;
      else if (typeof data.detail === "string") message = data.detail;
    } catch {
      // ignore
    }
    throw new ApiError(message, res.status);
  }
  if (!res.body) {
    throw new ApiError("No stream from API", res.status || 500);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let fetched = 0;
  let shown = 0;
  let sawDone = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk
        .split("\n")
        .find((entry) => entry.startsWith("data: "));
      if (!line) continue;
      const payload = JSON.parse(line.slice(6)) as {
        type?: string;
        post?: Post;
        fetched?: number;
        shown?: number;
        error?: string;
      };
      if (payload.type === "error" || payload.error) {
        throw new ApiError(payload.error || "Fetch failed", 400);
      }
      if (payload.type === "post" && payload.post) {
        shown += 1;
        onPost(payload.post);
      }
      if (payload.type === "done") {
        fetched = payload.fetched ?? 0;
        shown = payload.shown ?? shown;
        sawDone = true;
      }
    }
  }

  if (!sawDone) {
    throw new ApiError("Fetch ended before Reddit finished", 500);
  }
  return { fetched, shown };
}

export function generateDrafts(): Promise<{ drafted: number }> {
  return request<{ drafted: number }>("/api/actions/draft", { method: "POST" });
}

export function runOnce(): Promise<{
  fetched: number;
  drafted: number;
  posted: number;
  outcomes?: number;
}> {
  return request("/api/actions/run-once", { method: "POST" });
}

export function pollOutcomes(): Promise<{ outcomes: number }> {
  return request<{ outcomes: number }>("/api/actions/poll-outcomes", {
    method: "POST",
  });
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

export function listProjects(): Promise<{
  projects: ProjectSummary[];
  active_project_id: string;
}> {
  return request("/api/projects");
}

export function createProject(purpose: ProjectPurpose, name?: string): Promise<Project> {
  return request("/api/projects", {
    method: "POST",
    body: JSON.stringify({ purpose, name }),
  });
}

export function getProject(id: string): Promise<Project> {
  return request(`/api/projects/${id}`);
}

export function patchProject(
  id: string,
  body: Partial<{
    name: string;
    briefing: string;
    goals: string[];
    tone: string;
    persona: string;
    avoid: string;
    subreddits: string[];
    keywords: string[];
    complete: boolean;
    setup_step: number;
  }>,
): Promise<Project> {
  return request(`/api/projects/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function setActiveProject(id: string): Promise<AppConfig> {
  return request("/api/projects/active", {
    method: "PUT",
    body: JSON.stringify({ id }),
  });
}

export function completeProject(id: string): Promise<Project> {
  return request(`/api/projects/${id}/complete`, { method: "POST" });
}

export async function streamInterview(
  projectId: string,
  message: string,
  onDelta: (delta: string) => void,
  onResearch?: (items: ProjectLink[]) => void,
): Promise<InterviewMessage> {
  const res = await fetch(`/api/projects/${projectId}/interview`, {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) {
    let messageText = `Request failed (${res.status})`;
    try {
      const data = (await res.json()) as { error?: string; detail?: string };
      if (data.error) messageText = data.error;
      else if (typeof data.detail === "string") messageText = data.detail;
    } catch {
      // ignore
    }
    throw new ApiError(messageText, res.status);
  }
  if (!res.body) {
    throw new ApiError("No stream from API", res.status || 500);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let reply: InterviewMessage | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((entry) => entry.startsWith("data: "));
      if (!line) continue;
      const payload = JSON.parse(line.slice(6)) as {
        delta?: string;
        done?: boolean;
        ready?: boolean;
        message?: InterviewMessage;
        research?: ProjectLink[];
        error?: string;
      };
      if (payload.error) throw new ApiError(payload.error, 400);
      if (payload.research?.length) onResearch?.(payload.research);
      if (payload.delta) onDelta(payload.delta);
      if (payload.done && payload.message) {
        reply = { ...payload.message, ready: Boolean(payload.ready) };
      }
    }
  }

  if (!reply) {
    throw new ApiError("Stream ended without a reply", 500);
  }
  return reply;
}
