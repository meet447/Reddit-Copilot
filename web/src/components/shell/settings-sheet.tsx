"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import {
  getConfig,
  putConfig,
  putSecrets,
  startOAuth,
  type AppConfig,
  type SecretsUpdate,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { IconX } from "@/components/ui/icons";
import { Field, Label, Input, Textarea, Hint } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { MeuxeMark } from "@/components/ui/mascot";

const sections = [
  { id: "accounts", label: "Accounts" },
  { id: "voice", label: "Voice" },
  { id: "discovery", label: "Subreddits & discovery" },
  { id: "rate_limits", label: "Rate limits" },
  { id: "llm", label: "LLM" },
  { id: "about", label: "About" },
] as const;

type SectionId = (typeof sections)[number]["id"];

export function SettingsSheet({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [section, setSection] = useState<SectionId>("accounts");
  const [, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const [redditClientId, setRedditClientId] = useState("");
  const [redditSecret, setRedditSecret] = useState("");
  const [llmKey, setLlmKey] = useState("");
  const [userAgent, setUserAgent] = useState("");
  const [accountName, setAccountName] = useState("default");
  const [connectedUsername, setConnectedUsername] = useState("");
  const [hasOAuth, setHasOAuth] = useState(false);
  const [hasClientId, setHasClientId] = useState(false);
  const [redirectUri, setRedirectUri] = useState(
    "http://127.0.0.1:8000/api/oauth/callback",
  );
  const [connecting, setConnecting] = useState(false);
  const [productDesc, setProductDesc] = useState("");
  const [tone, setTone] = useState("");
  const [persona, setPersona] = useState("");
  const [avoid, setAvoid] = useState("");
  const [subreddits, setSubreddits] = useState("");
  const [keywords, setKeywords] = useState("");
  const [dailyCap, setDailyCap] = useState("");
  const [minInterval, setMinInterval] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const [hasCredentials, setHasCredentials] = useState(false);
  const [hasApiKey, setHasApiKey] = useState(false);

  useEffect(() => {
    if (!open) return;
    getConfig()
      .then((c) => {
        setConfig(c);
        const account = c.accounts?.[0];
        setAccountName(account?.name ?? "default");
        setUserAgent(account?.user_agent ?? "");
        setProductDesc(c.voice?.product ?? "");
        setTone(c.voice?.tone ?? "");
        setPersona(c.voice?.persona ?? "");
        setAvoid(c.voice?.avoid ?? "");
        setSubreddits((c.subreddits ?? []).join(", "));
        setKeywords((c.discovery?.keywords ?? []).join(", "));
        setDailyCap(String(c.rate_limits?.daily_cap ?? ""));
        setMinInterval(String(c.rate_limits?.min_interval_seconds ?? ""));
        setLlmModel(c.llm?.model ?? "");
        setLlmBaseUrl(c.llm?.base_url ?? "");
        setHasCredentials(c.has_credentials);
        setHasOAuth(Boolean(c.has_oauth || account?.has_oauth));
        setHasClientId(Boolean(account?.has_client_id));
        setConnectedUsername(account?.connected_username ?? "");
        if (c.oauth_redirect_uri) setRedirectUri(c.oauth_redirect_uri);
        setHasApiKey(c.has_api_key);
      })
      .catch(() => setError("Could not load settings."));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await putConfig({
        subreddits: subreddits
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        voice: {
          product: productDesc,
          tone,
          persona,
          avoid,
        },
        discovery: {
          keywords: keywords
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        },
        rate_limits: {
          daily_cap: dailyCap ? Number(dailyCap) : undefined,
          min_interval_seconds: minInterval ? Number(minInterval) : undefined,
        },
        llm: {
          model: llmModel,
          base_url: llmBaseUrl,
        },
        accounts: [{ name: accountName, user_agent: userAgent }],
      });

      const secrets: SecretsUpdate = { account_name: accountName };
      if (redditClientId) secrets.reddit_client_id = redditClientId;
      if (redditSecret) secrets.reddit_client_secret = redditSecret;
      if (llmKey) secrets.llm_api_key = llmKey;
      const hasSecrets = Boolean(
        secrets.reddit_client_id || secrets.reddit_client_secret || secrets.llm_api_key,
      );
      if (hasSecrets) await putSecrets(secrets);

      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function handleConnectReddit() {
    setConnecting(true);
    setError(null);
    try {
      if (redditClientId || redditSecret) {
        await putSecrets({
          account_name: accountName,
          reddit_client_id: redditClientId || undefined,
          reddit_client_secret: redditSecret || undefined,
        });
      }
      const { authorize_url } = await startOAuth("/queue", accountName);
      window.location.href = authorize_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start Reddit sign-in.");
      setConnecting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
      <button
        type="button"
        className="absolute inset-0 bg-ink/20"
        aria-label="Close settings"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        className="relative flex h-[min(640px,90vh)] w-[min(880px,100%)] overflow-hidden rounded-sheet bg-surface shadow-pop squircle motion-safe:animate-pop-in"
      >
        <aside className="w-52 shrink-0 border-r border-line bg-well p-4">
          <div className="mb-6 flex items-center gap-2">
            <MeuxeMark size={28} />
            <span
              id="settings-title"
              className="text-[14px] font-semibold text-ink"
            >
              Settings
            </span>
          </div>
          <nav className="space-y-0.5">
            {sections.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => setSection(id)}
                className={cn(
                  "w-full rounded-control px-3 py-2 text-left text-[13px] transition-colors",
                  section === id
                    ? "bg-surface-2 text-ink font-medium shadow-soft"
                    : "text-ink-2 hover:bg-well-2 hover:text-ink",
                )}
              >
                {label}
              </button>
            ))}
          </nav>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-line px-6 py-4">
            <h2 className="text-[16px] font-semibold text-ink tracking-tight">
              {sections.find((s) => s.id === section)?.label}
            </h2>
            <IconButton label="Close settings" onClick={onClose}>
              <IconX size={18} />
            </IconButton>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
            {error && <Notice tone="clay">{error}</Notice>}
            {saved && (
              <Notice tone="sage">Settings saved.</Notice>
            )}

            {section === "accounts" && (
              <>
                {hasOAuth && connectedUsername ? (
                  <Notice tone="sage">Connected as u/{connectedUsername}.</Notice>
                ) : hasCredentials ? (
                  <Notice tone="sage">Reddit is connected on this machine.</Notice>
                ) : hasClientId ? (
                  <Notice tone="accent">
                    App credentials are saved. Connect Reddit to finish.
                  </Notice>
                ) : null}
                <Field>
                  <Label htmlFor="user-agent">User agent</Label>
                  <Input
                    id="user-agent"
                    value={userAgent}
                    onChange={(e) => setUserAgent(e.target.value)}
                  />
                  <Hint>Identify this app in Reddit’s User-Agent header.</Hint>
                </Field>
                <Field>
                  <Label htmlFor="reddit-client-id">Reddit client ID</Label>
                  <Input
                    id="reddit-client-id"
                    value={redditClientId}
                    onChange={(e) => setRedditClientId(e.target.value)}
                    placeholder={hasClientId ? "Leave blank to keep current" : "From reddit.com/prefs/apps"}
                  />
                </Field>
                <Field>
                  <Label htmlFor="reddit-secret">Client secret</Label>
                  <Input
                    id="reddit-secret"
                    type="password"
                    value={redditSecret}
                    onChange={(e) => setRedditSecret(e.target.value)}
                    placeholder="Leave blank to keep current"
                  />
                  <Hint>Create a web app. Redirect URI must match exactly:</Hint>
                </Field>
                <p className="rounded-field bg-well px-3 py-2 font-mono text-[12px] text-ink-2 break-all">
                  {redirectUri}
                </p>
                <Button
                  loading={connecting}
                  onClick={handleConnectReddit}
                  className="w-full"
                >
                  {hasOAuth ? "Reconnect Reddit" : "Connect Reddit"}
                </Button>
              </>
            )}

            {section === "voice" && (
              <>
                <Field>
                  <Label htmlFor="product-desc">Product description</Label>
                  <Textarea
                    id="product-desc"
                    value={productDesc}
                    onChange={(e) => setProductDesc(e.target.value)}
                    rows={4}
                  />
                </Field>
                <Field>
                  <Label htmlFor="tone">Tone</Label>
                  <Input
                    id="tone"
                    value={tone}
                    onChange={(e) => setTone(e.target.value)}
                    placeholder="Helpful, direct, no hype"
                  />
                </Field>
                <Field>
                  <Label htmlFor="persona">Persona</Label>
                  <Textarea
                    id="persona"
                    value={persona}
                    onChange={(e) => setPersona(e.target.value)}
                    rows={3}
                  />
                </Field>
                <Field>
                  <Label htmlFor="avoid">Things to avoid</Label>
                  <Input
                    id="avoid"
                    value={avoid}
                    onChange={(e) => setAvoid(e.target.value)}
                    placeholder="Hard sells, hype, asking for upvotes"
                  />
                </Field>
              </>
            )}

            {section === "discovery" && (
              <>
                <Field>
                  <Label htmlFor="subreddits">Subreddits</Label>
                  <Input
                    id="subreddits"
                    value={subreddits}
                    onChange={(e) => setSubreddits(e.target.value)}
                    placeholder="startups, SaaS, indiehackers"
                  />
                  <Hint>Comma-separated, without r/</Hint>
                </Field>
                <Field>
                  <Label htmlFor="keywords">Keywords</Label>
                  <Input
                    id="keywords"
                    value={keywords}
                    onChange={(e) => setKeywords(e.target.value)}
                    placeholder="looking for tool, alternative to"
                  />
                </Field>
              </>
            )}

            {section === "rate_limits" && (
              <>
                <Field>
                  <Label htmlFor="max-posts">Daily cap</Label>
                  <Input
                    id="max-posts"
                    type="number"
                    value={dailyCap}
                    onChange={(e) => setDailyCap(e.target.value)}
                  />
                </Field>
                <Field>
                  <Label htmlFor="cooldown">Minimum interval (seconds)</Label>
                  <Input
                    id="cooldown"
                    type="number"
                    value={minInterval}
                    onChange={(e) => setMinInterval(e.target.value)}
                  />
                </Field>
                <Notice tone="accent">
                  Nothing posts until you approve it.
                </Notice>
              </>
            )}

            {section === "llm" && (
              <>
                {hasApiKey && (
                  <Notice tone="sage">An LLM key is already saved in .env.</Notice>
                )}
                <Field>
                  <Label htmlFor="llm-model">Model</Label>
                  <Input
                    id="llm-model"
                    value={llmModel}
                    onChange={(e) => setLlmModel(e.target.value)}
                    placeholder="gpt-4o-mini"
                  />
                </Field>
                <Field>
                  <Label htmlFor="llm-base">Base URL</Label>
                  <Input
                    id="llm-base"
                    value={llmBaseUrl}
                    onChange={(e) => setLlmBaseUrl(e.target.value)}
                    placeholder="https://api.openai.com/v1"
                  />
                  <Hint>For Ollama or OpenRouter, set a custom base URL.</Hint>
                </Field>
                <Field>
                  <Label htmlFor="openai-key">API key</Label>
                  <Input
                    id="openai-key"
                    type="password"
                    value={llmKey}
                    onChange={(e) => setLlmKey(e.target.value)}
                    placeholder="Leave blank to keep current"
                  />
                </Field>
              </>
            )}

            {section === "about" && (
              <div className="space-y-3 text-[14px] text-ink-2 leading-relaxed">
                <p className="text-[18px] font-semibold text-ink tracking-tight">
                  Reddit Copilot
                </p>
                <p>
                  A local-first engagement assistant. Discovery and drafting run
                  in the background — you approve every reply before it ships.
                </p>
                <p className="font-mono text-[13px] text-ink-3">
                  rcopilot serve · npm run dev
                </p>
              </div>
            )}
          </div>

          {section !== "about" && (
            <div className="flex justify-end gap-2 border-t border-line px-6 py-4">
              <Button variant="ghost" onClick={onClose}>
                Cancel
              </Button>
              <Button loading={saving} onClick={handleSave}>
                Save changes
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
