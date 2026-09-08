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
  generateDraftVariants,
  selectDraftVariant,
  type Draft,
} from "@/lib/api";
import {
  fromDatetimeLocalValue,
  toDatetimeLocalValue,
  truncate,
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
import { ChoiceCard } from "@/components/ui/choice-card";
import { Kbd, KeyCombo } from "@/components/ui/kbd";
import { Dots } from "@/components/ui/dots";
import { PageStatus } from "@/components/ui/page-status";
import { PostedDetailView } from "@/components/draft/posted-detail-view";
import { BestTimeChips } from "@/components/schedule/best-time-chips";
import { SubredditName } from "@/components/ui/subreddit-name";

export function DraftDetailView({ id }: { id: number }) {
  const router = useRouter();
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [body, setBody] = useState("");
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
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
      setTitle(d.title ?? "");
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
  const isSubmission = draft?.kind === "submission";
  const canPost =
    hasBody &&
    (!isSubmission || Boolean(title.trim())) &&
    draft != null &&
    draft.status !== "posted" &&
    draft.status !== "rejected";

  async function saveBody() {
    if (!draft) return;
    if (isSubmission) {
      await patchDraft(draft.id, body, title.trim());
    } else {
      await patchDraft(draft.id, body);
    }
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
      if (name !== "generate" && name !== "variant") await saveBody();
      const updated = await fn();
      setDraft(updated);
      setBody(updated.body);
      setTitle(updated.title ?? "");
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
    if (!draft || generating || draft.status === "posted" || isSubmission) return;
    const wasRegen = Boolean(
      (draft.variants && draft.variants.length > 0) ||
        draft.body.trim() ||
        body.trim(),
    );
    setGenerating(true);
    setBusy("generate");
    setError(null);
    setMessage(null);
    try {
      const updated = await generateDraftVariants(draft.id);
      setDraft(updated);
      setBody(updated.body);
      setMessage(
        wasRegen
          ? "New angles. Pick one, then edit."
          : "Pick an angle, then edit and post.",
      );
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Drafting failed. Try again.",
      );
      await load();
    } finally {
      setGenerating(false);
      setBusy(null);
    }
  }

  async function handleSelectVariant(variantId: string) {
    if (!draft || generating || draft.status === "posted") return;
    await runAction(
      "variant",
      () => selectDraftVariant(draft.id, variantId),
      "This angle is in the editor. Edit, then post or schedule.",
    );
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (draft?.status === "posted") return;
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
          if (!isSubmission) void handleGenerate();
          break;
        case "1":
        case "2":
        case "3": {
          const variants = draft?.variants ?? [];
          const picked = variants[Number(e.key) - 1];
          if (picked) {
            e.preventDefault();
            void handleSelectVariant(picked.id);
          }
          break;
        }
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
      <PageStatus
        kind="loading"
        message="Opening this draft…"
        className="h-full"
      />
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

  if (draft.status === "posted") {
    return (
      <PostedDetailView
        draft={draft}
        onDraftChange={(updated) => {
          setDraft(updated);
          setBody(updated.body);
        }}
      />
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
            <SubredditName
              name={draft.subreddit}
              prefix={isSubmission ? "original post · " : undefined}
            />
            <h1 className="truncate text-[18px] font-semibold text-ink tracking-tight">
              {isSubmission ? title || draft.title : draft.title}
            </h1>
          </div>
          <Pill status={draft.status} />
        </div>
        <div className="hidden lg:flex items-center gap-3 text-[12px] text-ink-3">
          {!isSubmission && (
            <span className="inline-flex items-center gap-1">
              <Kbd>D</Kbd> draft
            </span>
          )}
          {!isSubmission && (draft.variants?.length ?? 0) > 0 && (
            <span className="inline-flex items-center gap-1">
              <KeyCombo keys={["1", "2", "3"]} /> pick
            </span>
          )}
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
            {generating && (
              <Notice tone="accent">
                <span className="inline-flex items-center gap-2">
                  Drafting a few angles… <Dots />
                </span>
              </Notice>
            )}
            {!generating &&
              Boolean(body.trim()) &&
              body === draft.body &&
              (draft.lint_warnings?.length ?? 0) > 0 && (
                <Notice tone="honey">
                  Slop check:{" "}
                  {draft.lint_warnings!.map((w) => w.message).join(" · ")} Edit
                  before posting.
                </Notice>
              )}

            {!isSubmission && (draft.variants?.length ?? 0) > 0 && (
              <div className="shrink-0 space-y-2">
                <p className="text-[12px] font-medium text-ink-3">
                  Pick an angle
                </p>
                <div className="grid gap-2 sm:grid-cols-3">
                  {draft.variants!.map((variant) => (
                    <ChoiceCard
                      key={variant.id}
                      selected={body === variant.body}
                      title={variant.label}
                      description={truncate(variant.body, 140)}
                      onSelect={() => void handleSelectVariant(variant.id)}
                    />
                  ))}
                </div>
              </div>
            )}

            <Field className="flex min-h-0 flex-1 flex-col">
              <Label htmlFor="draft-body" className="shrink-0">
                {isSubmission ? "Post body" : "Your reply"}
              </Label>
              {isSubmission && (
                <Input
                  className="mb-3 shrink-0"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Post title"
                  disabled={generating}
                />
              )}
              <div className="relative min-h-0 flex-1">
                <Textarea
                  ref={editorRef}
                  id="draft-body"
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  readOnly={generating}
                  placeholder={
                    generating
                      ? ""
                      : isSubmission
                        ? "Write the post body."
                        : (draft.variants?.length ?? 0) > 0
                          ? "Pick an angle above, or type your own."
                          : "Click Draft for a few angles, or type your own."
                  }
                  className="absolute inset-0 h-full min-h-0 resize-none overflow-y-auto text-[15px]"
                />
              </div>
            </Field>
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-line px-6 py-4">
            {!isSubmission && (
              <Button
                leading={<IconDraft size={16} />}
                loading={busy === "generate"}
                disabled={generating || draft.status === "posted"}
                onClick={() => void handleGenerate()}
              >
                {(draft.variants?.length ?? 0) > 0 || hasBody || draft.body
                  ? "More angles"
                  : "Draft"}
              </Button>
            )}
            <Button
              variant="danger-soft"
              loading={busy === "reject"}
              disabled={generating}
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
                disabled={generating}
                onClick={() =>
                  runAction("unschedule", () => unscheduleDraft(draft.id))
                }
              >
                Cancel schedule
              </Button>
            ) : (
              <Button
                variant="secondary"
                disabled={!canPost || generating}
                onClick={() => setScheduleOpen(true)}
              >
                Schedule
              </Button>
            )}
            <Button
              variant="secondary"
              loading={busy === "post"}
              disabled={!canPost || generating}
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
            {isSubmission ? (
              <div>
                <p className="text-[12px] font-medium text-ink-3 mb-2">
                  Destination
                </p>
                <SubredditName name={draft.subreddit} size="md" mono={false} />
                <p className="mt-2 text-[13px] text-ink-2">
                  Self-post · edit title and body, then post or schedule.
                </p>
              </div>
            ) : (
              <>
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
              </>
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
              {isSubmission ? "Schedule post" : "Schedule reply"}
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
            <BestTimeChips
              subreddit={draft.subreddit}
              onPick={(value) => setScheduleValue(value)}
            />
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
