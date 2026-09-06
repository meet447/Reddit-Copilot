"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getPosts,
  draftPost,
  skipPost,
  fetchThreads,
  ApiError,
  type Post,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ApiDownNotice, Notice } from "@/components/ui/notice";
import { Mascot } from "@/components/ui/mascot";
import { AsciiAccent } from "@/components/ui/ascii-accent";
import { Surface } from "@/components/ui/surface";
import { IconDraft, IconSkip, IconRefresh } from "@/components/ui/icons";
import { Input, Field, Label } from "@/components/ui/field";

export function DiscoverView() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [apiDown, setApiDown] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [fetching, setFetching] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    try {
      const data = await getPosts({ undrafted: true, skipped: false });
      setPosts(data);
      setApiDown(false);
    } catch {
      setApiDown(true);
      setPosts([]);
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = posts.filter((p) => {
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      p.title.toLowerCase().includes(q) ||
      p.subreddit.toLowerCase().includes(q) ||
      p.score_reasons?.some((r) => r.toLowerCase().includes(q))
    );
  });

  async function handleFetch() {
    setFetching(true);
    setActionError(null);
    setMessage(null);
    try {
      const result = await fetchThreads();
      await load({ silent: true });
      setApiDown(false);
      const count = result.fetched ?? 0;
      setMessage(
        count === 0
          ? "No new threads this round."
          : `Found ${count} new thread${count === 1 ? "" : "s"}.`,
      );
    } catch (error) {
      if (error instanceof ApiError && error.status < 500) {
        setActionError(error.message);
        setApiDown(false);
      } else {
        setApiDown(true);
      }
    } finally {
      setFetching(false);
    }
  }

  async function handleDraft(postId: string) {
    setBusyId(postId);
    try {
      await draftPost(postId);
      setPosts((prev) => prev.filter((p) => p.id !== postId));
    } catch {
      setApiDown(true);
    } finally {
      setBusyId(null);
    }
  }

  async function handleSkip(postId: string) {
    setBusyId(postId);
    try {
      await skipPost(postId);
      setPosts((prev) => prev.filter((p) => p.id !== postId));
    } catch {
      setApiDown(true);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-4 border-b border-line px-6 py-4">
        <div>
          <h1 className="text-[22px] font-semibold text-ink tracking-tight">
            Discover
          </h1>
          <p className="mt-0.5 text-[13px] text-ink-3">
            Intent-matched threads waiting for a draft.
          </p>
        </div>
        <Button
          variant="secondary"
          leading={<IconRefresh size={16} />}
          loading={fetching}
          onClick={handleFetch}
        >
          Fetch threads
        </Button>
      </header>

      <div className="shrink-0 border-b border-line px-6 py-4 space-y-3">
        {apiDown && <ApiDownNotice />}
        {actionError && <Notice tone="clay">{actionError}</Notice>}
        {message && <Notice tone="sage">{message}</Notice>}
        <Field>
          <Label htmlFor="discover-search" className="sr-only">
            Search results
          </Label>
          <Input
            id="discover-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by title, subreddit, or signal…"
          />
        </Field>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Mascot mood="thinking" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <AsciiAccent className="mb-4" />
            <Mascot mood="sleepy" className="mb-4" />
            <p className="max-w-sm text-[15px] text-ink-2">
              No intent-matched threads right now. Fetch threads, or check
              subreddits and what you make in Settings.
            </p>
          </div>
        ) : (
          <div className="grid gap-3">
            {filtered.map((post) => (
              <Surface
                key={post.id}
                tone="surface"
                radius="card"
                elevation="soft"
                className="p-4 squircle"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <p className="text-[12px] font-mono text-ink-3">
                      r/{post.subreddit}
                    </p>
                    <a
                      href={post.permalink}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-0.5 block text-[15px] font-semibold text-ink hover:text-ink-2 tracking-tight"
                    >
                      {post.title}
                    </a>
                    {post.selftext && (
                      <p className="mt-2 text-[14px] text-ink-2 line-clamp-2 leading-relaxed">
                        {post.selftext}
                      </p>
                    )}
                    {post.score_reasons?.length > 0 && (
                      <ul className="mt-3 flex flex-wrap gap-1.5">
                        {post.score_reasons.map((r) => (
                          <li
                            key={r}
                            className="rounded-control bg-accent-50 px-2 py-0.5 text-[11px] text-ink-2"
                          >
                            {r}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-col gap-2">
                    <Button
                      size="sm"
                      leading={<IconDraft size={14} />}
                      loading={busyId === post.id}
                      onClick={() => handleDraft(post.id)}
                    >
                      Draft
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      leading={<IconSkip size={14} />}
                      disabled={busyId === post.id}
                      onClick={() => handleSkip(post.id)}
                    >
                      Skip
                    </Button>
                  </div>
                </div>
              </Surface>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
