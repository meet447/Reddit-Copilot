"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  getDraft,
  getDrafts,
  patchDraft,
  rejectDraft,
  postDraft,
  scheduleDraft,
  unscheduleDraft,
  streamDraftGenerate,
  type Draft,
} from "@/lib/api";
import {
  fromDatetimeLocalValue,
  toDatetimeLocalValue,
} from "@/lib/format";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import {
  IconChevronLeft,
  IconExternal,
  IconDraft,
} from "@/components/ui/icons";
import { Textarea, Field, Label, Input } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { Pill } from "@/components/ui/pill";
import { Surface } from "@/components/ui/surface";
import { Kbd, KeyCombo } from "@/components/ui/kbd";
import { Dots } from "@/components/ui/dots";
import { Mascot } from "@/components/ui/mascot";

export function DraftDetailView({ id }: { id: number }) {
  const router = useRouter();
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [body, setBody] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleValue, setScheduleValue] = useState("");
  const [siblingIds, setSiblingIds] = useState<number[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [d, all] = await Promise.all([
        getDraft(id),
        getDrafts("pending"),
      ]);
      setDraft(d);
      setBody(d.body);
      setScheduleValue(toDatetimeLocalValue(d.run_at));
      setSiblingIds(all.map((x) => x.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load draft.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const currentIndex = siblingIds.indexOf(id);
  const prevId = currentIndex > 0 ? siblingIds[currentIndex - 1] : null;
  const nextId =
    currentIndex >= 0 && currentIndex < siblingIds.length - 1
      ? siblingIds[currentIndex + 1]
      : null;

  const hasBody = Boolean(body.trim());
  const canPost =
    hasBody &&
    draft != null &&
    draft.status !== "posted" &&
    draft.status !== "rejected";

  async function saveBody() {
    if (!draft) return;
    await patchDraft(draft.id, body);
  }

  async function runAction(
    name: string,
    fn: () => Promise<Draft>,
    successMsg?: string,
  ) {
    setBusy(name);
    setError(null);
    setMessage(null);
    try {
      if (name !== "generate") await saveBody();
      const updated = await fn();
      setDraft(updated);
      setBody(updated.body);
      if (successMsg) setMessage(successMsg);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "That didn't go through. Check the note and try again.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function handleGenerate() {
    if (!draft || streaming) return;
    const wasRegen = Boolean(draft.body.trim() || body.trim());
    setStreaming(true);
    setBusy("generate");
    setError(null);
    setMessage(null);
    setBody("");
    try {
      const updated = await streamDraftGenerate(draft.id, (delta) => {
        setBody((prev) => prev + delta);
      });
      setDraft(updated);
      setBody(updated.body);
      setMessage(
        wasRegen
          ? "Regenerated. Edit, then post or schedule."
          : "Draft ready. Edit, then post or schedule.",
      );
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Drafting failed. Try again.",
      );
      await load();
    } finally {
      setStreaming(false);
      setBusy(null);
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        if (e.key === "Escape") (e.target as HTMLElement).blur();
        return;
      }

      switch (e.key.toLowerCase()) {
        case "r":
          e.preventDefault();
          if (draft)
            runAction("reject", () => rejectDraft(draft.id)).then(() =>
              router.push("/queue"),
            );
          break;
        case "e":
          e.preventDefault();
          editorRef.current?.focus();
          break;
        case "s":
          e.preventDefault();
          setScheduleOpen(true);
          break;
        case "g":
        case "d":
          e.preventDefault();
          void handleGenerate();
          break;
        case "j":
          if (nextId) router.push(`/queue/${nextId}`);
          break;
        case "k":
          if (prevId) router.push(`/queue/${prevId}`);
          break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Mascot mood="thinking" />
      </div>
    );
  }

  if (!draft) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-6">
        <Notice tone="clay">{error ?? "Draft not found."}</Notice>
        <Link href="/queue">
          <Button variant="secondary">Back to queue</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-line px-6 py-4">
        <div className="flex items-center gap-3 min-w-0">
          <Link href="/queue">
            <IconButton label="Back to queue">
              <IconChevronLeft size={18} />
            </IconButton>
          </Link>
          <div className="min-w-0">
            <p className="text-[12px] font-mono text-ink-3">
              r/{draft.subreddit}
            </p>
            <h1 className="truncate text-[18px] font-semibold text-ink tracking-tight">
              {draft.title}
            </h1>
          </div>
          <Pill status={draft.status} />
        </div>
        <div className="hidden lg:flex items-center gap-3 text-[12px] text-ink-3">
          <span className="inline-flex items-center gap-1">
            <Kbd>D</Kbd> draft
          </span>
          <span className="inline-flex items-center gap-1">
            <Kbd>R</Kbd> reject
          </span>
          <span className="inline-flex items-center gap-1">
            <Kbd>E</Kbd> edit
          </span>
          <span className="inline-flex items-center gap-1">
            <Kbd>S</Kbd> schedule
          </span>
          {(prevId || nextId) && (
            <span className="inline-flex items-center gap-1">
              <KeyCombo keys={["J", "K"]} /> navigate
            </span>
          )}
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col border-r border-line">
          <div className="flex min-h-0 flex-1 flex-col gap-4 px-6 py-5">
            {message && <Notice tone="sage">{message}</Notice>}
            {(error || draft.error) && (
              <Notice tone="clay">
                {error ??
                  draft.error ??
                  "That didn't go through. Check the note and try again."}
              </Notice>
            )}
            {streaming && (
              <Notice tone="accent">
                <span className="inline-flex items-center gap-2">
                  Writing reply… <Dots />
                </span>
              </Notice>
            )}
            {!streaming &&
              body === draft.body &&
              (draft.lint_warnings?.length ?? 0) > 0 && (
                <Notice tone="honey">
                  Slop check:{" "}
                  {draft.lint_warnings!.map((w) => w.message).join(" · ")} Edit
                  before posting.
                </Notice>
              )}

            <Field className="flex min-h-0 flex-1 flex-col">
              <Label htmlFor="draft-body" className="shrink-0">
                Your reply
              </Label>
              <div className="relative min-h-0 flex-1">
                <Textarea
                  ref={editorRef}
                  id="draft-body"
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  readOnly={streaming}
                  placeholder={
                    streaming
                      ? ""
                      : "Click Draft to write a reply, or type your own."
                  }
                  className="absolute inset-0 h-full min-h-0 resize-none overflow-y-auto text-[15px]"
                />
              </div>
            </Field>
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-line px-6 py-4">
            <Button
              leading={<IconDraft size={16} />}
              loading={busy === "generate"}
              disabled={streaming || draft.status === "posted"}
              onClick={() => void handleGenerate()}
            >
              {hasBody || draft.body ? "Regenerate" : "Draft"}
            </Button>
            <Button
              variant="danger-soft"
              loading={busy === "reject"}
              disabled={streaming}
              onClick={() =>
                runAction("reject", () => rejectDraft(draft.id)).then(() =>
                  router.push("/queue"),
                )
              }
            >
              Reject
            </Button>
            <div className="flex-1" />
            {draft.status === "scheduled" ? (
              <Button
                variant="ghost"
                loading={busy === "unschedule"}
                disabled={streaming}
                onClick={() =>
                  runAction("unschedule", () => unscheduleDraft(draft.id))
                }
              >
                Cancel schedule
              </Button>
            ) : (
              <Button
                variant="secondary"
                disabled={!canPost || streaming}
                onClick={() => setScheduleOpen(true)}
              >
                Schedule
              </Button>
            )}
            <Button
              variant="secondary"
              loading={busy === "post"}
              disabled={!canPost || streaming}
              onClick={() =>
                runAction(
                  "post",
                  () => postDraft(draft.id),
                  "Posted. Nice work.",
                )
              }
            >
              Post now
            </Button>
          </div>
        </div>

        <aside className="hidden w-[340px] shrink-0 overflow-y-auto bg-well xl:block">
          <div className="p-5 space-y-4">
            <div>
              <p className="text-[12px] font-medium text-ink-3 mb-2">Thread</p>
              <a
                href={draft.post_permalink || draft.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-start gap-1.5 text-[15px] font-semibold text-ink hover:text-ink-2"
              >
                {draft.title}
                <IconExternal size={14} className="mt-1 shrink-0" />
              </a>
            </div>

            {draft.selftext && (
              <Surface tone="raised" radius="card" className="p-4">
                <p className="text-[14px] text-ink-2 leading-relaxed whitespace-pre-wrap">
                  {draft.selftext}
                </p>
              </Surface>
            )}

            {draft.top_comments?.length > 0 && (
              <div>
                <p className="text-[12px] font-medium text-ink-3 mb-2">
                  Top comments
                </p>
                <div className="space-y-2">
                  {draft.top_comments.map((c, i) => (
                    <Surface
                      key={i}
                      tone="raised"
                      radius="card"
                      className="p-3"
                    >
                      <p className="text-[13px] text-ink-2 leading-relaxed">
                        {c.body}
                      </p>
                      <p className="mt-1 font-mono text-[11px] text-ink-3">
                        {c.score} pts
                      </p>
                    </Surface>
                  ))}
                </div>
              </div>
            )}

            {draft.score_reasons?.length > 0 && (
              <div>
                <p className="text-[12px] font-medium text-ink-3 mb-2">
                  Relevance
                </p>
                <ul className="space-y-1">
                  {draft.score_reasons.map((r) => (
                    <li key={r} className="text-[13px] text-ink-2">
                      · {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </aside>
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
            <h2 className="text-[16px] font-semibold text-ink mb-4">
              Schedule reply
            </h2>
            <Field>
              <Label htmlFor="schedule-at">Post at</Label>
              <Input
                id="schedule-at"
                type="datetime-local"
                value={scheduleValue}
                onChange={(e) => setScheduleValue(e.target.value)}
              />
            </Field>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setScheduleOpen(false)}>
                Cancel
              </Button>
              <Button
                loading={busy === "schedule"}
                onClick={() =>
                  runAction(
                    "schedule",
                    () =>
                      scheduleDraft(
                        draft.id,
                        fromDatetimeLocalValue(scheduleValue),
                      ),
                    "Queued for later. You can still edit or cancel.",
                  ).then(() => setScheduleOpen(false))
                }
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
