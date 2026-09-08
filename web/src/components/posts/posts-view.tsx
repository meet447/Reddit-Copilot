"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  getBestTimes,
  getDrafts,
  postDraft,
  rejectDraft,
  scheduleDraft,
  streamGenerateSubmissions,
  ApiError,
  type Draft,
} from "@/lib/api";
import { truncate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { ApiDownNotice, Notice } from "@/components/ui/notice";
import { Pill } from "@/components/ui/pill";
import { Surface } from "@/components/ui/surface";
import { PageStatus } from "@/components/ui/page-status";
import { IconDraft, IconPlus } from "@/components/ui/icons";
import { BestTimeChips } from "@/components/schedule/best-time-chips";
import { Field, Input, Label } from "@/components/ui/field";
import {
  fromDatetimeLocalValue,
  toDatetimeLocalValue,
} from "@/lib/format";
import { SubredditName } from "@/components/ui/subreddit-name";
import { Dots } from "@/components/ui/dots";

function mergeSubmissionDraft(drafts: Draft[], incoming: Draft): Draft[] {
  const next = drafts.filter((item) => item.id !== incoming.id);
  next.push(incoming);
  next.sort((a, b) => {
    const time = (b.created_at || "").localeCompare(a.created_at || "");
    if (time !== 0) return time;
    return b.id - a.id;
  });
  return next;
}

export function PostsView() {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [loading, setLoading] = useState(true);
  const [apiDown, setApiDown] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [schedulingId, setSchedulingId] = useState<number | null>(null);
  const [scheduleValue, setScheduleValue] = useState(
    toDatetimeLocalValue(new Date(Date.now() + 3600_000).toISOString()),
  );

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    try {
      const all = await getDrafts("pending");
      setDrafts(all.filter((d) => d.kind === "submission"));
      setApiDown(false);
    } catch {
      setApiDown(true);
      setDrafts([]);
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    setMessage(null);
    let received = 0;
    try {
      const result = await streamGenerateSubmissions((draft) => {
        received += 1;
        setDrafts((prev) => mergeSubmissionDraft(prev, draft));
        setLoading(false);
        setApiDown(false);
        setMessage(
          `Drafted ${received} post${received === 1 ? "" : "s"} so far…`,
        );
      });
      await load({ silent: true });
      setApiDown(false);
      const count = result.created || received;
      setMessage(
        count
          ? `Drafted ${count} post${count === 1 ? "" : "s"}. Review, then post or schedule.`
          : "No posts were generated. Check your LLM key and subreddits.",
      );
    } catch (e) {
      if (e instanceof ApiError && e.status < 500) {
        setError(e.message);
        setApiDown(false);
      } else if (e instanceof Error) {
        setError(e.message);
      } else {
        setError("Could not generate posts.");
      }
    } finally {
      setGenerating(false);
    }
  }

  async function handlePost(id: number) {
    setBusy(`post-${id}`);
    setError(null);
    try {
      await postDraft(id);
      setMessage("Posted to Reddit.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not post.");
    } finally {
      setBusy(null);
    }
  }

  async function handleReject(id: number) {
    setBusy(`reject-${id}`);
    try {
      await rejectDraft(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not reject.");
    } finally {
      setBusy(null);
    }
  }

  async function handleScheduleBest(draft: Draft) {
    setBusy(`best-${draft.id}`);
    setError(null);
    try {
      const data = await getBestTimes(draft.subreddit, { count: 1 });
      const first = data.suggestions[0];
      if (!first?.run_at) {
        throw new Error("No best-time suggestion available.");
      }
      await scheduleDraft(draft.id, first.run_at);
      setMessage(`Scheduled for ${first.label}.`);
      setSchedulingId(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not schedule.");
    } finally {
      setBusy(null);
    }
  }

  async function handleScheduleCustom(id: number) {
    setBusy(`schedule-${id}`);
    setError(null);
    try {
      await scheduleDraft(id, fromDatetimeLocalValue(scheduleValue));
      setMessage("Queued on the schedule.");
      setSchedulingId(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not schedule.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-4 border-b border-line px-6 py-4">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">
            Posts
          </h1>
          <p className="mt-0.5 text-[13px] text-ink-3">
            Write a self-post yourself, or let Copilot draft ideas across your
            subs — then post now or schedule at a busy hour.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href="/compose">
            <Button variant="secondary" leading={<IconPlus size={16} />}>
              Write post
            </Button>
          </Link>
          <Button
            leading={<IconDraft size={16} />}
            loading={generating}
            onClick={() => void handleGenerate()}
          >
            Generate ideas
          </Button>
        </div>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto px-6 py-4">
        {apiDown && <ApiDownNotice />}
        {error && <Notice tone="clay">{error}</Notice>}
        {message && <Notice tone="sage">{message}</Notice>}
        {generating && (
          <Notice tone="accent">
            <span className="inline-flex items-center gap-2">
              Drafting posts for your communities… <Dots />
            </span>
          </Notice>
        )}

        {loading && drafts.length === 0 ? (
          <PageStatus kind="loading" message="Loading posts…" />
        ) : drafts.length === 0 && generating ? (
          <PageStatus
            kind="loading"
            message="Drafting posts for your communities…"
          />
        ) : drafts.length === 0 ? (
          <PageStatus
            kind="empty"
            message="No pending posts yet. Write one manually, or generate a batch for your configured subreddits."
          />
        ) : (
          <div className="space-y-3">
            {drafts.map((draft) => (
              <Surface
                key={draft.id}
                tone="surface"
                radius="card"
                elevation="soft"
                className="p-4 squircle"
              >
                <div className="mb-2 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <SubredditName
                      name={draft.subreddit}
                      prefix="Post · "
                    />
                    <Link
                      href={`/queue/${draft.id}`}
                      className="mt-0.5 block truncate text-[15px] font-semibold text-ink hover:text-ink-2"
                    >
                      {draft.title}
                    </Link>
                  </div>
                  <Pill status={draft.status} />
                </div>
                <p className="text-[14px] leading-relaxed text-ink-2 line-clamp-3">
                  {truncate(draft.body, 220)}
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    loading={busy === `post-${draft.id}`}
                    onClick={() => void handlePost(draft.id)}
                  >
                    Post now
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    loading={busy === `best-${draft.id}`}
                    onClick={() => void handleScheduleBest(draft)}
                  >
                    Schedule best time
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setSchedulingId(draft.id);
                      setScheduleValue(
                        toDatetimeLocalValue(
                          new Date(Date.now() + 3600_000).toISOString(),
                        ),
                      );
                    }}
                  >
                    Pick time
                  </Button>
                  <Link href={`/queue/${draft.id}`}>
                    <Button size="sm" variant="ghost">
                      Edit
                    </Button>
                  </Link>
                  <Button
                    size="sm"
                    variant="danger-soft"
                    loading={busy === `reject-${draft.id}`}
                    onClick={() => void handleReject(draft.id)}
                  >
                    Reject
                  </Button>
                </div>

                {schedulingId === draft.id && (
                  <div className="mt-4 border-t border-line pt-4">
                    <Field>
                      <Label htmlFor={`post-schedule-${draft.id}`}>
                        Schedule at
                      </Label>
                      <Input
                        id={`post-schedule-${draft.id}`}
                        type="datetime-local"
                        value={scheduleValue}
                        onChange={(e) => setScheduleValue(e.target.value)}
                      />
                    </Field>
                    <BestTimeChips
                      subreddit={draft.subreddit}
                      onPick={(value) => setScheduleValue(value)}
                    />
                    <div className="mt-3 flex gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setSchedulingId(null)}
                      >
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        loading={busy === `schedule-${draft.id}`}
                        onClick={() => void handleScheduleCustom(draft.id)}
                      >
                        Schedule
                      </Button>
                    </div>
                  </div>
                )}
              </Surface>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
