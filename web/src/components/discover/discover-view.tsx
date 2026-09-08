"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getPosts,
  queuePost,
  skipPost,
  streamFetchThreads,
  ApiError,
  type Post,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ApiDownNotice, Notice } from "@/components/ui/notice";
import { PageStatus } from "@/components/ui/page-status";
import { Surface } from "@/components/ui/surface";
import { SubredditName } from "@/components/ui/subreddit-name";
import { IconPlus, IconSkip, IconRefresh } from "@/components/ui/icons";
import { Input, Field, Label } from "@/components/ui/field";
import { Dots } from "@/components/ui/dots";
import {
  STREAM_SLOT_COUNT,
  StreamCardSkeletons,
} from "@/components/ui/stream-card-skeleton";

const INTENT_LABELS: { slug: string; label: string }[] = [
  { slug: "question", label: "Question" },
  { slug: "looking-for-tool", label: "Looking for tool" },
  { slug: "complaint", label: "Complaint" },
  { slug: "unanswered", label: "Unanswered" },
];

const FILTERS: { id: string | null; label: string }[] = [
  { id: null, label: "All" },
  { id: "question", label: "Question" },
  { id: "looking-for-tool", label: "Looking for tool" },
  { id: "unanswered", label: "Unanswered" },
  { id: "complaint", label: "Complaint" },
];

function labelDisplay(slug: string): string {
  return INTENT_LABELS.find((item) => item.slug === slug)?.label ?? slug;
}

function mergeDiscoverPost(posts: Post[], incoming: Post): Post[] {
  const next = posts.filter((item) => item.id !== incoming.id);
  next.push(incoming);
  next.sort((a, b) => {
    const score = (b.relevance_score ?? 0) - (a.relevance_score ?? 0);
    if (score !== 0) return score;
    return (b.created_utc ?? 0) - (a.created_utc ?? 0);
  });
  return next;
}

export function DiscoverView() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [query, setQuery] = useState("");
  const [labelFilter, setLabelFilter] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [apiDown, setApiDown] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [fetching, setFetching] = useState(false);
  const [pendingSlots, setPendingSlots] = useState(0);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(
    async (opts?: { silent?: boolean; label?: string | null }) => {
      if (!opts?.silent) setLoading(true);
      const activeLabel = opts?.label !== undefined ? opts.label : labelFilter;
      try {
        const data = await getPosts({
          undrafted: true,
          skipped: false,
          ...(activeLabel ? { label: activeLabel } : {}),
        });
        setPosts(data);
        setApiDown(false);
      } catch {
        setApiDown(true);
        setPosts([]);
      } finally {
        if (!opts?.silent) setLoading(false);
      }
    },
    [labelFilter],
  );

  useEffect(() => {
    load();
  }, [load]);

  const filtered = posts.filter((p) => {
    if (labelFilter && !(p.intent_labels ?? []).includes(labelFilter)) {
      return false;
    }
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      p.title.toLowerCase().includes(q) ||
      p.subreddit.toLowerCase().includes(q) ||
      (p.intent_labels ?? []).some((label) =>
        labelDisplay(label).toLowerCase().includes(q),
      )
    );
  });

  async function handleFetch() {
    setFetching(true);
    setPendingSlots(STREAM_SLOT_COUNT);
    setActionError(null);
    setMessage(null);
    let received = 0;
    try {
      const result = await streamFetchThreads((post) => {
        received += 1;
        setPosts((prev) => mergeDiscoverPost(prev, post));
        setPendingSlots((slots) => Math.max(2, slots - 1));
        setLoading(false);
        setApiDown(false);
        setMessage(
          `Found ${received} thread${received === 1 ? "" : "s"} so far…`,
        );
      });
      await load({ silent: true });
      setApiDown(false);
      const count = result.shown ?? received;
      setMessage(
        count === 0
          ? "No matching threads this round."
          : `Found ${count} thread${count === 1 ? "" : "s"}.`,
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
      setPendingSlots(0);
    }
  }

  async function handleAdd(postId: string) {
    setBusyId(postId);
    setActionError(null);
    setMessage(null);
    try {
      await queuePost(postId);
      setPosts((prev) => prev.filter((p) => p.id !== postId));
      setApiDown(false);
      setMessage("Added to the review queue.");
    } catch (error) {
      if (error instanceof ApiError) {
        setActionError(error.message);
        setApiDown(false);
      } else {
        setApiDown(true);
      }
    } finally {
      setBusyId(null);
    }
  }

  async function handleSkip(postId: string) {
    setBusyId(postId);
    setActionError(null);
    try {
      await skipPost(postId);
      setPosts((prev) => prev.filter((p) => p.id !== postId));
      setApiDown(false);
    } catch (error) {
      if (error instanceof ApiError) {
        setActionError(error.message);
        setApiDown(false);
      } else {
        setApiDown(true);
      }
    } finally {
      setBusyId(null);
    }
  }

  function handleLabelFilter(next: string | null) {
    setLabelFilter(next);
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-4 border-b border-line px-6 py-4">
        <div>
          <h1 className="text-[22px] font-semibold text-ink tracking-tight">
            Discover
          </h1>
          <p className="mt-0.5 text-[13px] text-ink-3">
            Pick threads to review. Draft replies in the queue.
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
        {fetching && (
          <Notice tone="accent">
            <span className="inline-flex items-center gap-2">
              Fetching threads from your communities… <Dots />
            </span>
          </Notice>
        )}
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Intent filters">
          {FILTERS.map((filter) => {
            const active = labelFilter === filter.id;
            return (
              <button
                key={filter.label}
                type="button"
                onClick={() => handleLabelFilter(filter.id)}
                className={[
                  "rounded-control px-2.5 py-1 text-[12px] transition-colors",
                  active
                    ? "bg-ink text-canvas"
                    : "bg-accent-50 text-ink-2 hover:text-ink",
                ].join(" ")}
              >
                {filter.label}
              </button>
            );
          })}
        </div>
        <Field>
          <Label htmlFor="discover-search" className="sr-only">
            Search results
          </Label>
          <Input
            id="discover-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by title, subreddit, or label…"
          />
        </Field>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading && posts.length === 0 && pendingSlots === 0 ? (
          <PageStatus
            kind="loading"
            message="Looking through your communities…"
          />
        ) : filtered.length === 0 && pendingSlots === 0 ? (
          <PageStatus
            kind="empty"
            message={
              query.trim() || labelFilter
                ? "Nothing matches that filter."
                : "No matching threads yet. Fetch a round, or check subreddits and what you make in Settings."
            }
          />
        ) : (
          <div className="grid gap-3" aria-busy={fetching}>
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
                    <SubredditName name={post.subreddit} />
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
                    {(post.intent_labels ?? []).length > 0 && (
                      <ul className="mt-3 flex flex-wrap gap-1.5">
                        {(post.intent_labels ?? []).map((slug) => (
                          <li
                            key={slug}
                            className="rounded-control bg-accent-50 px-2 py-0.5 text-[11px] text-ink-2"
                          >
                            {labelDisplay(slug)}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-col gap-2">
                    <Button
                      size="sm"
                      leading={<IconPlus size={14} />}
                      loading={busyId === post.id}
                      onClick={() => handleAdd(post.id)}
                    >
                      Add
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
            <StreamCardSkeletons kind="discover" count={pendingSlots} />
          </div>
        )}
      </div>
    </div>
  );
}
