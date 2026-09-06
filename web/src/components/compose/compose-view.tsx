"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  createSubmission,
  getConfig,
  patchDraft,
  postDraft,
  scheduleDraft,
  ApiError,
} from "@/lib/api";
import {
  fromDatetimeLocalValue,
  toDatetimeLocalValue,
} from "@/lib/format";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { IconChevronLeft } from "@/components/ui/icons";
import { Field, Input, Label, Textarea } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { Surface } from "@/components/ui/surface";
import { BestTimeChips } from "@/components/schedule/best-time-chips";

export function ComposeView() {
  const router = useRouter();
  const [subreddits, setSubreddits] = useState<string[]>([]);
  const [subreddit, setSubreddit] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleValue, setScheduleValue] = useState(
    toDatetimeLocalValue(new Date(Date.now() + 3600_000).toISOString()),
  );
  const [draftId, setDraftId] = useState<number | null>(null);

  useEffect(() => {
    getConfig()
      .then((config) => {
        const list = config.subreddits ?? [];
        setSubreddits(list);
        if (list[0]) setSubreddit(list[0]);
      })
      .catch(() => {
        setError("Could not load settings. Is the API running?");
      });
  }, []);

  async function ensureDraft(): Promise<number> {
    if (draftId != null) {
      await patchDraft(draftId, body.trim(), title.trim());
      return draftId;
    }
    const draft = await createSubmission({
      subreddit,
      title: title.trim(),
      body: body.trim(),
    });
    setDraftId(draft.id);
    return draft.id;
  }

  async function handleSave() {
    setBusy("save");
    setError(null);
    setMessage(null);
    try {
      const id = await ensureDraft();
      setMessage("Saved to the review queue.");
      router.push(`/queue/${id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save post.");
    } finally {
      setBusy(null);
    }
  }

  async function handlePostNow() {
    setBusy("post");
    setError(null);
    setMessage(null);
    try {
      const id = await ensureDraft();
      await postDraft(id);
      setMessage("Posted to Reddit.");
      router.push(`/queue/${id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not post.");
    } finally {
      setBusy(null);
    }
  }

  async function handleSchedule() {
    setBusy("schedule");
    setError(null);
    setMessage(null);
    try {
      const id = await ensureDraft();
      await scheduleDraft(id, fromDatetimeLocalValue(scheduleValue));
      setScheduleOpen(false);
      setMessage("Queued for later.");
      router.push(`/queue/${id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not schedule.");
    } finally {
      setBusy(null);
    }
  }

  const canSubmit =
    Boolean(subreddit.trim()) &&
    Boolean(title.trim()) &&
    Boolean(body.trim()) &&
    !busy;

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <header className="flex shrink-0 items-center gap-3 border-b border-line px-6 py-4">
        <Link href="/schedule">
          <IconButton label="Back to schedule">
            <IconChevronLeft size={18} />
          </IconButton>
        </Link>
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">
            New post
          </h1>
          <p className="mt-0.5 text-[13px] text-ink-3">
            Compose a self-post, then save, schedule, or post now.
          </p>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-4 overflow-y-auto px-6 py-6">
        {error && <Notice tone="clay">{error}</Notice>}
        {message && <Notice tone="sage">{message}</Notice>}

        <Field>
          <Label htmlFor="compose-sub">Subreddit</Label>
          {subreddits.length > 0 ? (
            <select
              id="compose-sub"
              value={subreddit}
              onChange={(e) => setSubreddit(e.target.value)}
              className="w-full rounded-field border border-line bg-surface px-3 py-2 text-[14px] text-ink"
            >
              {subreddits.map((name) => (
                <option key={name} value={name}>
                  r/{name}
                </option>
              ))}
            </select>
          ) : (
            <Input
              id="compose-sub"
              value={subreddit}
              onChange={(e) => setSubreddit(e.target.value)}
              placeholder="python"
            />
          )}
        </Field>

        <Field>
          <Label htmlFor="compose-title">Title</Label>
          <Input
            id="compose-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="What are you sharing?"
          />
        </Field>

        <Field className="flex min-h-[220px] flex-1 flex-col">
          <Label htmlFor="compose-body">Body</Label>
          <Textarea
            id="compose-body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="min-h-[200px] flex-1 resize-y"
            placeholder="Write the post in your voice."
          />
        </Field>
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-line px-6 py-4">
        <Button
          variant="secondary"
          loading={busy === "save"}
          disabled={!canSubmit}
          onClick={() => void handleSave()}
        >
          Save to queue
        </Button>
        <div className="flex-1" />
        <Button
          variant="secondary"
          disabled={!canSubmit}
          onClick={() => setScheduleOpen(true)}
        >
          Schedule
        </Button>
        <Button
          loading={busy === "post"}
          disabled={!canSubmit}
          onClick={() => void handlePostNow()}
        >
          Post now
        </Button>
      </div>

      {scheduleOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
          <button
            type="button"
            className="absolute inset-0 bg-ink/20"
            aria-label="Close schedule"
            onClick={() => setScheduleOpen(false)}
          />
          <Surface
            tone="surface"
            radius="sheet"
            elevation="pop"
            className="relative w-full max-w-sm p-6 motion-safe:animate-pop-in squircle"
          >
            <h2 className="mb-4 text-[16px] font-semibold text-ink">
              Schedule post
            </h2>
            <Field>
              <Label htmlFor="compose-schedule-at">Post at</Label>
              <Input
                id="compose-schedule-at"
                type="datetime-local"
                value={scheduleValue}
                onChange={(e) => setScheduleValue(e.target.value)}
              />
            </Field>
            <BestTimeChips
              subreddit={subreddit}
              onPick={(value) => setScheduleValue(value)}
            />
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setScheduleOpen(false)}>
                Cancel
              </Button>
              <Button
                loading={busy === "schedule"}
                disabled={!canSubmit}
                onClick={() => void handleSchedule()}
              >
                Schedule
              </Button>
            </div>
          </Surface>
        </div>
      )}
    </div>
  );
}
