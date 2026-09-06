"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  completeProject,
  createProject,
  fetchThreads,
  getConfig,
  getProject,
  patchProject,
  putConfig,
  putSecrets,
  setActiveProject,
  startOAuth,
  streamInterview,
  type InterviewMessage,
  type ProjectLink,
  type ProjectPurpose,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";
import { MeuxeMark, Mascot } from "@/components/ui/mascot";
import { Field, Label, Input, Textarea, Hint } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { TagInput } from "@/components/ui/tag-input";
import { ChoiceCard } from "@/components/ui/choice-card";
import { InterviewChat } from "@/components/onboarding/interview-chat";

const ACCOUNT_STEPS = 3;

const STEPS = [
  {
    title: "Create a Reddit app",
    subtitle:
      "A web app at reddit.com/prefs/apps. You’ll only paste the client id and secret.",
    mood: "neutral" as const,
  },
  {
    title: "Connect Reddit",
    subtitle:
      "Sign in with Reddit in the browser. We store a refresh token locally — not your password.",
    mood: "thinking" as const,
  },
  {
    title: "Connect your LLM",
    subtitle:
      "OpenAI-compatible API — used for drafts, briefing, and subreddit suggestions.",
    mood: "sleepy" as const,
  },
  {
    title: "What is this for?",
    subtitle: "Each workspace can be a product, personal, or something you define.",
    mood: "happy" as const,
  },
  {
    title: "Tell us more",
    subtitle:
      "A short conversation so Copilot can pick communities and write in your voice.",
    mood: "thinking" as const,
  },
  {
    title: "Review your workspace",
    subtitle: "Edit the goals and communities, then we’ll fetch the first threads.",
    mood: "surprised" as const,
  },
];

const PURPOSES: { id: ProjectPurpose; title: string; description: string }[] = [
  {
    id: "product",
    title: "A product",
    description:
      "Find threads where people need what you make, then draft helpful replies.",
  },
  {
    id: "personal",
    title: "Personal",
    description:
      "Show up as yourself — expertise, job search, hobby communities.",
  },
  {
    id: "custom",
    title: "Custom",
    description: "Describe exactly what you want this copilot to do.",
  },
];

const OPENINGS: Record<ProjectPurpose, string> = {
  product:
    "Tell me about your product. What is it, who is it for, and what problem does it solve? You can also paste links to the site, docs, or a launch post.",
  personal:
    "Tell me about yourself — what you do, the communities you care about, and how you want to show up on Reddit.",
  custom:
    "What do you want to do with this copilot? What is your aim — the more specific, the better I can set up discovery and drafts.",
};

function messagesWithOpening(
  purpose: ProjectPurpose,
  messages: InterviewMessage[],
): InterviewMessage[] {
  if (messages.some((item) => item.role === "assistant")) return messages;
  return [{ role: "assistant", content: OPENINGS[purpose] }, ...messages];
}

function clampStep(value: number | undefined, max: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(Math.trunc(value as number), max));
}

export function OnboardingFlow() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isNewProject = searchParams.get("new") === "1";
  const isRerun = searchParams.get("briefing") === "1";
  const [step, setStep] = useState(0);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [connectedName, setConnectedName] = useState("");
  const [hasClientId, setHasClientId] = useState(false);
  const [hasApiKey, setHasApiKey] = useState(false);
  const [accountReady, setAccountReady] = useState(false);
  const [redirectUri, setRedirectUri] = useState(
    "http://127.0.0.1:8000/api/oauth/callback",
  );

  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [llmModel, setLlmModel] = useState("gpt-4o-mini");
  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");

  const [purpose, setPurpose] = useState<ProjectPurpose | null>(null);
  const [projectId, setProjectId] = useState("");
  const [messages, setMessages] = useState<InterviewMessage[]>([]);
  const [streaming, setStreaming] = useState("");
  const [replying, setReplying] = useState(false);
  const [researched, setResearched] = useState<ProjectLink[]>([]);
  const [workspaceName, setWorkspaceName] = useState("");
  const [briefing, setBriefing] = useState("");
  const [goals, setGoals] = useState<string[]>([]);
  const [subreddits, setSubreddits] = useState<string[]>([]);
  const [keywords, setKeywords] = useState<string[]>([]);

  const skipAccount = accountReady || isNewProject || isRerun;
  const firstVisible = isRerun ? 4 : skipAccount ? ACCOUNT_STEPS : 0;
  const visibleSteps = STEPS.map((_, i) => i).filter((i) => i >= firstVisible);
  const current = STEPS[step];

  useEffect(() => {
    let cancelled = false;
    getConfig()
      .then((config) => {
        if (cancelled) return;
        if (config.oauth_redirect_uri) setRedirectUri(config.oauth_redirect_uri);
        const account = config.accounts?.[0];
        setHasClientId(Boolean(account?.has_client_id));
        setHasApiKey(Boolean(config.has_api_key));
        if (account?.connected_username) {
          setConnectedName(account.connected_username);
        } else if (account?.has_oauth) {
          setConnectedName("your account");
        }
        if (config.llm?.model) setLlmModel(config.llm.model);
        setLlmBaseUrl(config.llm?.base_url ?? "");
        const redditOk = Boolean(account?.has_oauth || account?.connected_username);
        const llmOk = Boolean(config.has_api_key);
        const readyAccount = redditOk && llmOk && Boolean(account?.has_client_id);
        setAccountReady(readyAccount);

        const reddit = searchParams.get("reddit");
        let nextStep = clampStep(config.onboarding_step, STEPS.length - 1);
        if (isRerun && readyAccount && config.active_project_id) {
          nextStep = 4;
          void getProject(config.active_project_id)
            .then((project) => {
              if (cancelled) return;
              setProjectId(project.id);
              setPurpose(project.purpose);
              setMessages(
                messagesWithOpening(
                  project.purpose,
                  project.interview_messages ?? [],
                ),
              );
              setResearched(project.links ?? []);
            })
            .catch(() => {
              if (!cancelled) setError("Could not load this workspace.");
            });
        } else if (isNewProject && readyAccount) {
          nextStep = ACCOUNT_STEPS;
        } else if (readyAccount && nextStep < ACCOUNT_STEPS) {
          nextStep = ACCOUNT_STEPS;
        }
        if (reddit === "connected" || reddit === "error") {
          nextStep = Math.max(nextStep, 1);
        }
        setStep(nextStep);
        if (reddit === "error") {
          setError(
            searchParams.get("reason") ||
              "Reddit connection didn’t finish. Check the redirect URI and try again.",
          );
        }
        setReady(true);
      })
      .catch(() => {
        if (cancelled) return;
        setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [searchParams, isNewProject, isRerun]);

  async function persistAccount(nextStep: number) {
    if (isNewProject || isRerun) return;
    await putConfig({
      onboarding_step: nextStep,
      llm: {
        model: llmModel,
        base_url: llmBaseUrl || undefined,
      },
    });
  }

  async function saveSecretsIfPresent() {
    const secrets: {
      reddit_client_id?: string;
      reddit_client_secret?: string;
      llm_api_key?: string;
    } = {};
    if (clientId.trim()) secrets.reddit_client_id = clientId.trim();
    if (clientSecret.trim()) secrets.reddit_client_secret = clientSecret.trim();
    if (apiKey.trim()) secrets.llm_api_key = apiKey.trim();
    if (Object.keys(secrets).length === 0) return;
    await putSecrets(secrets);
    if (secrets.reddit_client_id || secrets.reddit_client_secret) {
      setHasClientId(true);
    }
    if (secrets.llm_api_key) {
      setHasApiKey(true);
      setApiKey("");
    }
  }

  async function handleConnect() {
    setConnecting(true);
    setError(null);
    try {
      await saveSecretsIfPresent();
      await persistAccount(1);
      const { authorize_url } = await startOAuth("/onboarding");
      window.location.href = authorize_url;
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not start Reddit sign-in.",
      );
      setConnecting(false);
    }
  }

  async function startInterview(nextPurpose: ProjectPurpose) {
    if (projectId && purpose === nextPurpose) return;
    const project = await createProject(nextPurpose);
    setProjectId(project.id);
    setPurpose(nextPurpose);
    setMessages(
      messagesWithOpening(nextPurpose, project.interview_messages ?? []),
    );
    setResearched([]);
  }

  async function sendInterview(text: string) {
    if (!projectId) return;
    setError(null);
    setReplying(true);
    setMessages((current) => [...current, { role: "user", content: text }]);
    setStreaming("");
    try {
      const reply = await streamInterview(
        projectId,
        text,
        (delta) => setStreaming((value) => value + delta),
        (items) => setResearched((current) => [...current, ...items]),
      );
      setStreaming("");
      setMessages((current) => [...current, reply]);
    } catch (e) {
      setStreaming("");
      setError(
        e instanceof Error ? e.message : "Could not continue the briefing.",
      );
    } finally {
      setReplying(false);
    }
  }

  async function generateWorkspace() {
    if (!projectId) {
      setError("Pick a purpose first.");
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      const project = await completeProject(projectId);
      setWorkspaceName(project.name);
      setBriefing(project.briefing);
      setGoals(project.goals ?? []);
      setSubreddits(project.subreddits ?? []);
      setKeywords(project.keywords ?? []);
      setStep(5);
      await persistAccount(5);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not generate the workspace.",
      );
    } finally {
      setGenerating(false);
    }
  }

  async function finish() {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      await patchProject(projectId, {
        name: workspaceName,
        briefing,
        goals,
        subreddits,
        keywords,
        complete: true,
      });
      await setActiveProject(projectId);
      if (!isNewProject) {
        await persistAccount(STEPS.length - 1);
        await putConfig({ onboarding_complete: true });
      }
      try {
        await fetchThreads();
      } catch {
        // Queue will show why fetch failed
      }
      router.push("/queue");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Setup failed. Try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleContinue() {
    if (step === 0) {
      if ((!clientId.trim() || !clientSecret.trim()) && !hasClientId) {
        setError("Paste your Reddit client ID and secret to continue.");
        return;
      }
    }
    if (step === 1 && !connectedName) {
      setError("Connect Reddit before continuing.");
      return;
    }
    if (step === 2 && !hasApiKey && !apiKey.trim()) {
      setError("Add an LLM API key so we can draft and run the briefing.");
      return;
    }
    if (step === 3 && !purpose) {
      setError("Choose what this workspace is for.");
      return;
    }
    if (step === 4) {
      await generateWorkspace();
      return;
    }
    if (step === 5) {
      if (subreddits.length === 0) {
        setError("Add at least one subreddit to continue.");
        return;
      }
      await finish();
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await saveSecretsIfPresent();
      if (step === 3 && purpose) {
        await startInterview(purpose);
      }
      const nextStep = step + 1;
      await persistAccount(nextStep);
      setStep(nextStep);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save this step.");
    } finally {
      setLoading(false);
    }
  }

  async function handleBack() {
    if (step <= firstVisible) {
      if (isNewProject || isRerun) router.push("/queue");
      return;
    }
    const nextStep = step - 1;
    setError(null);
    try {
      await persistAccount(nextStep);
      setStep(nextStep);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save this step.");
    }
  }

  if (!ready) {
    return (
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-surface">
        <Mascot mood="thinking" />
      </div>
    );
  }

  const continueLabel =
    step === 4
      ? "Generate workspace"
      : step === STEPS.length - 1
        ? "Finish"
        : "Continue";
  const isInterview = step === 4;

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-surface">
      <header className="flex shrink-0 items-center justify-between px-6 py-4">
        <MeuxeMark size={32} />
        <div className="flex items-center gap-1.5">
          {visibleSteps.map((i) => (
            <span
              key={i}
              className={cn(
                "h-1.5 w-1.5 rounded-full transition-colors",
                i <= step ? "bg-accent-400" : "bg-well-2",
              )}
            />
          ))}
        </div>
        <div className="w-8" />
      </header>

      <main
        className={cn(
          "flex min-h-0 flex-1 flex-col items-center px-6 pb-24",
          isInterview ? "justify-stretch pt-1" : "justify-center",
        )}
      >
        <div
          className={cn(
            "w-full motion-safe:animate-rise-in",
            isInterview
              ? "flex min-h-0 max-w-[640px] flex-1 flex-col"
              : "max-w-[560px] text-center",
          )}
        >
          {!isInterview && (
            <Mascot mood={current.mood} className="mx-auto mb-6" size={96} />
          )}
          <p
            className={cn(
              "mb-2 text-[13px] text-ink-3",
              isInterview && "text-center",
            )}
          >
            Step {visibleSteps.indexOf(step) + 1} of {visibleSteps.length}
          </p>
          <h1
            className={cn(
              "text-[24px] font-semibold tracking-tight text-ink",
              isInterview && "text-center text-[20px]",
            )}
          >
            {current.title}
          </h1>
          <p
            className={cn(
              "mt-2 text-[15px] leading-relaxed text-ink-2",
              isInterview && "text-center text-[14px]",
            )}
          >
            {current.subtitle}
          </p>

          <div
            className={cn(
              "text-left",
              isInterview
                ? "mt-5 flex min-h-0 flex-1 flex-col"
                : "mt-8 space-y-4",
            )}
          >
            {error && <Notice tone="clay">{error}</Notice>}

            {step === 0 && (
              <>
                {hasClientId && (
                  <Notice tone="sage">
                    App credentials are already saved. Leave the fields blank to
                    keep them.
                  </Notice>
                )}
                <Field>
                  <Label htmlFor="ob-client-id">Reddit client ID</Label>
                  <Input
                    id="ob-client-id"
                    value={clientId}
                    onChange={(e) => setClientId(e.target.value)}
                    placeholder={
                      hasClientId
                        ? "Leave blank to keep current"
                        : "From reddit.com/prefs/apps"
                    }
                  />
                </Field>
                <Field>
                  <Label htmlFor="ob-secret">Client secret</Label>
                  <Input
                    id="ob-secret"
                    type="password"
                    value={clientSecret}
                    onChange={(e) => setClientSecret(e.target.value)}
                    placeholder={
                      hasClientId ? "Leave blank to keep current" : undefined
                    }
                  />
                  <Hint>Create a web app. Redirect URI must match exactly:</Hint>
                </Field>
                <p className="break-all rounded-field bg-well px-3 py-2 font-mono text-[12px] text-ink-2">
                  {redirectUri}
                </p>
              </>
            )}

            {step === 1 && (
              <>
                {connectedName ? (
                  <Notice tone="sage">Connected as u/{connectedName}.</Notice>
                ) : (
                  <Notice tone="accent">
                    Nothing posts until you approve it. This only lets Copilot
                    fetch threads and submit comments you approve.
                  </Notice>
                )}
                <Button
                  loading={connecting}
                  onClick={handleConnect}
                  className="w-full"
                >
                  {connectedName ? "Reconnect Reddit" : "Connect Reddit"}
                </Button>
              </>
            )}

            {step === 2 && (
              <>
                {hasApiKey && (
                  <Notice tone="sage">
                    An LLM key is already saved. Leave the key blank to keep it.
                  </Notice>
                )}
                <Field>
                  <Label htmlFor="ob-model">Model</Label>
                  <Input
                    id="ob-model"
                    value={llmModel}
                    onChange={(e) => setLlmModel(e.target.value)}
                  />
                </Field>
                <Field>
                  <Label htmlFor="ob-base">Base URL (optional)</Label>
                  <Input
                    id="ob-base"
                    value={llmBaseUrl}
                    onChange={(e) => setLlmBaseUrl(e.target.value)}
                    placeholder="For Ollama or OpenRouter"
                  />
                </Field>
                <Field>
                  <Label htmlFor="ob-key">API key</Label>
                  <Input
                    id="ob-key"
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={
                      hasApiKey ? "Leave blank to keep current" : undefined
                    }
                  />
                </Field>
              </>
            )}

            {step === 3 && (
              <div className="space-y-2">
                {PURPOSES.map((item) => (
                  <ChoiceCard
                    key={item.id}
                    title={item.title}
                    description={item.description}
                    selected={purpose === item.id}
                    onSelect={() => setPurpose(item.id)}
                  />
                ))}
              </div>
            )}

            {step === 4 && (
              <InterviewChat
                messages={messages}
                streaming={streaming}
                researched={researched}
                busy={replying}
                disabled={replying || generating}
                onSend={(text) => void sendInterview(text)}
              />
            )}

            {step === 5 && (
              <>
                <Field>
                  <Label htmlFor="ob-name">Workspace name</Label>
                  <Input
                    id="ob-name"
                    value={workspaceName}
                    onChange={(e) => setWorkspaceName(e.target.value)}
                  />
                </Field>
                <Field>
                  <Label htmlFor="ob-briefing">
                    {purpose === "personal"
                      ? "About you"
                      : purpose === "custom"
                        ? "Aim"
                        : "Product"}
                  </Label>
                  <Textarea
                    id="ob-briefing"
                    value={briefing}
                    onChange={(e) => setBriefing(e.target.value)}
                    rows={4}
                  />
                </Field>
                <Field>
                  <Label htmlFor="ob-goals">Goals</Label>
                  <TagInput
                    id="ob-goals"
                    values={goals}
                    onChange={setGoals}
                    placeholder="Add a goal and press Enter"
                  />
                </Field>
                <Field>
                  <Label htmlFor="ob-subs">Subreddits</Label>
                  <TagInput
                    id="ob-subs"
                    values={subreddits}
                    onChange={setSubreddits}
                    stripSubPrefix
                    placeholder="Add r/name and press Enter"
                  />
                  <Hint>
                    Suggested from the briefing. Add or remove until it feels
                    right.
                  </Hint>
                </Field>
                <Field>
                  <Label htmlFor="ob-kw">Keywords</Label>
                  <TagInput
                    id="ob-kw"
                    values={keywords}
                    onChange={setKeywords}
                    placeholder="Add a keyword and press Enter"
                  />
                </Field>
                <Notice tone="accent">
                  We’ll run your first thread fetch when you finish.
                </Notice>
              </>
            )}
          </div>
        </div>
      </main>

      <footer className="fixed bottom-0 left-0 right-0 flex items-center justify-between border-t border-line bg-surface px-6 py-4">
        <Button
          variant="ghost"
          disabled={step <= firstVisible && !isNewProject && !isRerun}
          onClick={() => void handleBack()}
        >
          {step <= firstVisible && (isNewProject || isRerun) ? "Cancel" : "Back"}
        </Button>
        <Button
          loading={loading || generating}
          onClick={() => void handleContinue()}
        >
          {continueLabel}
        </Button>
      </footer>
    </div>
  );
}
