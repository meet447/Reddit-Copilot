"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  getConfig,
  putConfig,
  putSecrets,
  startOAuth,
  fetchThreads,
  type AppConfig,
  type ConfigUpdate,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";
import { MeuxeMark, Mascot } from "@/components/ui/mascot";
import { Field, Label, Input, Textarea, Hint } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";

const STEPS = [
  {
    title: "Create a Reddit app",
    subtitle: "A web app at reddit.com/prefs/apps. You’ll only paste the client id and secret.",
    mood: "neutral" as const,
  },
  {
    title: "Connect Reddit",
    subtitle: "Sign in with Reddit in the browser. We store a refresh token locally — not your password.",
    mood: "thinking" as const,
  },
  {
    title: "Describe your voice",
    subtitle: "What you build and how you sound when you help people.",
    mood: "happy" as const,
  },
  {
    title: "Pick subreddits & keywords",
    subtitle: "Where to look and what signals matter.",
    mood: "surprised" as const,
  },
  {
    title: "Connect your LLM",
    subtitle: "OpenAI-compatible API for drafting replies.",
    mood: "sleepy" as const,
  },
];

function splitCsv(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function clampStep(value: number | undefined): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(Math.trunc(value as number), STEPS.length - 1));
}

export function OnboardingFlow() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [step, setStep] = useState(0);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectedName, setConnectedName] = useState("");
  const [hasClientId, setHasClientId] = useState(false);
  const [hasApiKey, setHasApiKey] = useState(false);
  const [redirectUri, setRedirectUri] = useState(
    "http://127.0.0.1:8000/api/oauth/callback",
  );

  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [productDesc, setProductDesc] = useState("");
  const [tone, setTone] = useState("");
  const [persona, setPersona] = useState("");
  const [subreddits, setSubreddits] = useState("");
  const [keywords, setKeywords] = useState("");
  const [llmModel, setLlmModel] = useState("gpt-4o-mini");
  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");

  function applyConfig(config: AppConfig) {
    if (config.oauth_redirect_uri) setRedirectUri(config.oauth_redirect_uri);
    const account = config.accounts?.[0];
    setHasClientId(Boolean(account?.has_client_id));
    setHasApiKey(Boolean(config.has_api_key));
    if (account?.connected_username) {
      setConnectedName(account.connected_username);
    } else if (account?.has_oauth) {
      setConnectedName("your account");
    }
    setProductDesc(config.voice?.product ?? "");
    setTone(config.voice?.tone ?? "");
    setPersona(config.voice?.persona ?? "");
    setSubreddits((config.subreddits ?? []).join(", "));
    setKeywords((config.discovery?.keywords ?? []).join(", "));
    if (config.llm?.model) setLlmModel(config.llm.model);
    setLlmBaseUrl(config.llm?.base_url ?? "");
  }

  async function persist(nextStep: number, extra?: ConfigUpdate) {
    await putConfig({
      onboarding_step: nextStep,
      subreddits: splitCsv(subreddits),
      voice: {
        product: productDesc,
        tone,
        persona,
      },
      discovery: {
        keywords: splitCsv(keywords),
      },
      llm: {
        model: llmModel,
        base_url: llmBaseUrl || undefined,
      },
      ...extra,
    });
  }

  useEffect(() => {
    let cancelled = false;
    getConfig()
      .then((config) => {
        if (cancelled) return;
        applyConfig(config);
        const reddit = searchParams.get("reddit");
        let nextStep = clampStep(config.onboarding_step);
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
  }, [searchParams]);

  useEffect(() => {
    if (!ready) return;
    const timer = window.setTimeout(() => {
      void persist(step);
    }, 500);
    return () => window.clearTimeout(timer);
    // persist reads the latest field state from this render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    ready,
    step,
    productDesc,
    tone,
    persona,
    subreddits,
    keywords,
    llmModel,
    llmBaseUrl,
  ]);

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

  async function finish() {
    setLoading(true);
    setError(null);
    try {
      await saveSecretsIfPresent();
      await persist(STEPS.length - 1, { onboarding_complete: true });
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
      if (!clientId.trim() && !clientSecret.trim() && !hasClientId) {
        setError("Paste your Reddit client ID and secret to continue.");
        return;
      }
      if ((!clientId.trim() || !clientSecret.trim()) && !hasClientId) {
        setError("Paste your Reddit client ID and secret to continue.");
        return;
      }
    }
    if (step === 1 && !connectedName) {
      setError("Connect Reddit before continuing.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await saveSecretsIfPresent();
      if (step < STEPS.length - 1) {
        const nextStep = step + 1;
        await persist(nextStep);
        setStep(nextStep);
        return;
      }
      await finish();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save this step.");
    } finally {
      setLoading(false);
    }
  }

  async function handleBack() {
    if (step === 0) return;
    const nextStep = step - 1;
    setError(null);
    try {
      await persist(nextStep);
      setStep(nextStep);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save this step.");
    }
  }

  async function handleConnect() {
    setConnecting(true);
    setError(null);
    try {
      await saveSecretsIfPresent();
      await persist(1);
      const { authorize_url } = await startOAuth("/onboarding");
      window.location.href = authorize_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start Reddit sign-in.");
      setConnecting(false);
    }
  }

  if (!ready) {
    return (
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-surface">
        <Mascot mood="thinking" />
      </div>
    );
  }

  const current = STEPS[step];

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-surface">
      <header className="flex items-center justify-between px-6 py-4">
        <MeuxeMark size={32} />
        <div className="flex items-center gap-1.5">
          {STEPS.map((_, i) => (
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

      <main className="flex flex-1 flex-col items-center justify-center px-6 pb-24">
        <div className="w-full max-w-[560px] text-center motion-safe:animate-rise-in">
          <Mascot mood={current.mood} className="mx-auto mb-6" size={96} />
          <p className="text-[13px] text-ink-3 mb-2">
            Step {step + 1} of {STEPS.length}
          </p>
          <h1 className="text-[24px] font-semibold text-ink tracking-tight">
            {current.title}
          </h1>
          <p className="mt-2 text-[15px] text-ink-2 leading-relaxed">
            {current.subtitle}
          </p>

          <div className="mt-8 text-left space-y-4">
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
                    placeholder={hasClientId ? "Leave blank to keep current" : undefined}
                  />
                  <Hint>Create a web app. Redirect URI must match exactly:</Hint>
                </Field>
                <p className="rounded-field bg-well px-3 py-2 font-mono text-[12px] text-ink-2 break-all">
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
                <Field>
                  <Label htmlFor="ob-product">What do you make?</Label>
                  <Textarea
                    id="ob-product"
                    value={productDesc}
                    onChange={(e) => setProductDesc(e.target.value)}
                    rows={3}
                  />
                </Field>
                <Field>
                  <Label htmlFor="ob-tone">Tone</Label>
                  <Input
                    id="ob-tone"
                    value={tone}
                    onChange={(e) => setTone(e.target.value)}
                    placeholder="Helpful, direct, no hype"
                  />
                </Field>
                <Field>
                  <Label htmlFor="ob-persona">Persona notes</Label>
                  <Textarea
                    id="ob-persona"
                    value={persona}
                    onChange={(e) => setPersona(e.target.value)}
                    rows={2}
                  />
                </Field>
              </>
            )}

            {step === 3 && (
              <>
                <Field>
                  <Label htmlFor="ob-subs">Subreddits</Label>
                  <Input
                    id="ob-subs"
                    value={subreddits}
                    onChange={(e) => setSubreddits(e.target.value)}
                    placeholder="startups, SaaS, indiehackers"
                  />
                  <Hint>Comma-separated, without r/</Hint>
                </Field>
                <Field>
                  <Label htmlFor="ob-kw">Keywords</Label>
                  <Input
                    id="ob-kw"
                    value={keywords}
                    onChange={(e) => setKeywords(e.target.value)}
                    placeholder="looking for, alternative to, recommend"
                  />
                </Field>
              </>
            )}

            {step === 4 && (
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
                    placeholder={hasApiKey ? "Leave blank to keep current" : undefined}
                  />
                </Field>
                <Notice tone="accent">
                  We&apos;ll run your first thread fetch when you finish.
                </Notice>
              </>
            )}
          </div>
        </div>
      </main>

      <footer className="fixed bottom-0 left-0 right-0 flex items-center justify-between px-6 py-4 bg-surface border-t border-line">
        <Button variant="ghost" disabled={step === 0} onClick={handleBack}>
          Back
        </Button>
        <Button loading={loading} onClick={handleContinue}>
          {step === STEPS.length - 1 ? "Finish" : "Continue"}
        </Button>
      </footer>
    </div>
  );
}
