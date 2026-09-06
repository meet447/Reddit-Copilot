"use client";

import { useEffect, useRef, useState } from "react";
import type { InterviewMessage, ProjectLink } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { IconSend } from "@/components/ui/icons";
import { Mascot } from "@/components/ui/mascot";
import { MarkdownBody } from "@/components/ui/markdown";
import { Dots } from "@/components/ui/dots";

export function InterviewChat({
  messages,
  streaming,
  researched,
  busy,
  setup,
  disabled,
  onSend,
}: {
  messages: InterviewMessage[];
  streaming: string;
  researched: ProjectLink[];
  busy?: boolean;
  setup?: boolean;
  disabled?: boolean;
  onSend: (text: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const visible = messages.filter((item) => item.role !== "system");
  const waiting = Boolean(busy) && !streaming;
  const speaking = Boolean(streaming);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [visible, streaming, researched, waiting]);

  function submit() {
    const text = draft.trim();
    if (!text || disabled) return;
    setDraft("");
    onSend(text);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-1 py-1">
        {visible.map((item, index) =>
          item.role === "user" ? (
            <div
              key={`user-${index}`}
              className="flex justify-end pl-12 motion-safe:animate-rise-in"
            >
              <div className="max-w-[78%] rounded-[18px] rounded-br-md bg-ink px-3.5 py-2.5 text-left squircle">
                <MarkdownBody text={item.content} tone="user" />
              </div>
            </div>
          ) : (
            <div
              key={`assistant-${index}`}
              className="flex items-start gap-2.5 pr-8 motion-safe:animate-rise-in"
            >
              <Mascot
                mood="happy"
                size={40}
                className="mt-0.5 shrink-0"
              />
              <div className="min-w-0 max-w-[78%] rounded-[18px] rounded-bl-md bg-well px-3.5 py-2.5 text-left squircle">
                <MarkdownBody text={item.content} />
              </div>
            </div>
          ),
        )}

        {(waiting || speaking) && (
          <div
            className="flex items-start gap-2.5 pr-8"
            aria-live="polite"
            aria-busy="true"
          >
            <Mascot
              mood="happy"
              talking
              size={40}
              className="mt-0.5 shrink-0"
            />
            <div className="min-w-0 max-w-[78%] rounded-[18px] rounded-bl-md bg-well px-3.5 py-2.5 text-left squircle">
              {speaking ? (
                <div className="[&_p:last-child]:mb-0 [&_p:last-child]:inline">
                  <MarkdownBody text={streaming} className="inline" />
                  <span
                    className="ml-0.5 inline-block h-[0.9em] w-[2px] translate-y-[2px] bg-ink motion-safe:animate-caret"
                    aria-hidden="true"
                  />
                </div>
              ) : setup ? (
                <p className="text-[14px] leading-[1.55] text-ink">
                  Setting up your workspace…
                </p>
              ) : (
                <Dots className="py-1" />
              )}
            </div>
          </div>
        )}

        {researched.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pl-[50px]">
            {researched.map((item) => (
              <span
                key={item.url}
                title={item.title || item.url}
                className="max-w-[min(100%,18rem)] truncate rounded-full bg-well px-2.5 py-1 text-[12px] text-ink-2"
              >
                {researchLabel(item)}
              </span>
            ))}
          </div>
        )}
        <div ref={end} />
      </div>

      <div className="mt-3 flex items-end gap-2">
        <textarea
          value={draft}
          disabled={disabled}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={2}
          placeholder="Write a reply…"
          aria-label="Message"
          className="min-h-[56px] max-h-32 flex-1 resize-none rounded-field bg-well px-3 py-2.5 text-[14px] leading-relaxed text-ink placeholder:text-ink-4 focus:bg-surface-2 focus:outline-none focus:ring-2 focus:ring-accent-200 squircle"
        />
        <Button
          size="sm"
          disabled={disabled || !draft.trim()}
          onClick={submit}
          leading={<IconSend size={14} />}
        >
          Send
        </Button>
      </div>
    </div>
  );
}

function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function githubRepo(url: string) {
  try {
    const parts = new URL(url).pathname.split("/").filter(Boolean);
    if (parts.length >= 2) return `${parts[0]}/${parts[1]}`;
  } catch {
    return "";
  }
  return "";
}

function researchLabel(item: ProjectLink) {
  const host = hostOf(item.url);
  if (item.ok === false) return `Couldn’t read ${host}`;
  if (host === "github.com") {
    return `Read ${githubRepo(item.url) || host}`;
  }
  const title = (item.title || "").replace(/\s*[·|].*$/, "").trim();
  if (!title || title.toLowerCase() === host) return `Read ${host}`;
  return title.length > 36 ? `Read ${title.slice(0, 33)}…` : `Read ${title}`;
}
