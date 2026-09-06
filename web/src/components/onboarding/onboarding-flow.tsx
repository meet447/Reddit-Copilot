"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  getConfig,
  putConfig,
  putSecrets,
  startOAuth,
  fetchThreads,
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

export function OnboardingFlow() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectedName, setConnectedName] = useState("");
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

  useEffect(() => {
    getConfig()
      .then((config) => {
        if (config.oauth_redirect_uri) setRedirectUri(config.oauth_redirect_uri);
        const account = config.accounts?.[0];
        if (account?.has_oauth && account.connected_username) {
          setConnectedName(account.connected_username);
        }
      })
      .catch(() => {
        // API down — keep defaults
      });
  }, []);

  useEffect(() => {
    const status = searchParams.get("reddit");
    if (status === "connected") {
      setStep(1);
      getConfig()
        .then((config) => {
          const account = config.accounts?.[0];
          setConnectedName(account?.connected_username ?? "your account");
        })
        .catch(() => setConnectedName("your account"));
    }
    if (status === "error") {
      setStep(1);
      setError(
        searchParams.get("reason") ||
          "Reddit connection didn’t finish. Check the redirect URI and try again.",
      );
    }
  }, [searchParams]);

  async function finish() {
    setLoading(true);
    setError(null);
    try {
      await putConfig({
        onboarding_complete: true,
        subreddits: subreddits
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        voice: {
          product: productDesc,
          tone,
          persona,
        },
        discovery: {
          keywords: keywords
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        },
        llm: {
          model: llmModel,
          base_url: llmBaseUrl || undefined,
        },
      });

      if (apiKey) {
        await putSecrets({ llm_api_key: apiKey });
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
      if (!clientId.trim() || !clientSecret.trim()) {
        setError("Paste your Reddit client ID and secret to continue.");
        return;
      }
      setLoading(true);
      setError(null);
      try {
        await putSecrets({
          reddit_client_id: clientId.trim(),
          reddit_client_secret: clientSecret.trim(),
        });
        setStep(1);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not save app credentials.");
      } finally {
        setLoading(false);
      }
      return;
    }
    if (step === 1 && !connectedName) {
      setError("Connect Reddit before continuing.");
      return;
    }
    if (step < STEPS.length - 1) {
      setStep(step + 1);
      return;
    }
    await finish();
  }

  async function handleConnect() {
    setConnecting(true);
    setError(null);
    try {
      await putSecrets({
        reddit_client_id: clientId.trim(),
        reddit_client_secret: clientSecret.trim(),
      });
      const { authorize_url } = await startOAuth("/onboarding");
      window.location.href = authorize_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start Reddit sign-in.");
      setConnecting(false);
    }
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
                <Field>
                  <Label htmlFor="ob-client-id">Reddit client ID</Label>
                  <Input
                    id="ob-client-id"
                    value={clientId}
                    onChange={(e) => setClientId(e.target.value)}
                    placeholder="From reddit.com/prefs/apps"
                  />
                </Field>
                <Field>
                  <Label htmlFor="ob-secret">Client secret</Label>
                  <Input
                    id="ob-secret"
                    type="password"
                    value={clientSecret}
                    onChange={(e) => setClientSecret(e.target.value)}
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
        <Button
          variant="ghost"
          disabled={step === 0}
          onClick={() => setStep(step - 1)}
        >
          Back
        </Button>
        <Button loading={loading} onClick={handleContinue}>
          {step === STEPS.length - 1 ? "Finish" : "Continue"}
        </Button>
      </footer>
    </div>
  );
}
