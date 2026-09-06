"use client";

import { useState, type KeyboardEvent } from "react";
import { cn } from "@/lib/cn";
import { IconX } from "@/components/ui/icons";
import { SubredditName } from "@/components/ui/subreddit-name";

function normalizeTag(raw: string, stripSubPrefix: boolean): string {
  let value = raw.trim();
  if (stripSubPrefix) {
    value = value.replace(/^r\//i, "").replace(/^\//, "");
  }
  return value;
}

export function TagInput({
  id,
  values,
  onChange,
  placeholder = "Type and press Enter",
  stripSubPrefix = false,
  disabled = false,
}: {
  id?: string;
  values: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  /** Strip leading r/ when adding (for subreddit names). */
  stripSubPrefix?: boolean;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState("");

  function addFromText(text: string) {
    const parts = text
      .split(/[,;\n]+/)
      .map((part) => normalizeTag(part, stripSubPrefix))
      .filter(Boolean);
    if (!parts.length) return;
    const seen = new Set(values.map((v) => v.toLowerCase()));
    const next = [...values];
    for (const part of parts) {
      const key = part.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      next.push(part);
    }
    onChange(next);
    setDraft("");
  }

  function removeAt(index: number) {
    onChange(values.filter((_, i) => i !== index));
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addFromText(draft);
      return;
    }
    if (e.key === "Backspace" && !draft && values.length) {
      e.preventDefault();
      onChange(values.slice(0, -1));
    }
  }

  return (
    <div
      className={cn(
        "flex min-h-10 flex-wrap items-center gap-1.5 rounded-field border border-line bg-surface px-2 py-1.5",
        "focus-within:border-accent-200 focus-within:ring-2 focus-within:ring-accent-200/40",
        disabled && "opacity-60",
      )}
    >
      {values.map((tag, index) => (
        <span
          key={`${tag}-${index}`}
          className="inline-flex max-w-full items-center gap-1 rounded-control bg-well px-2 py-1 text-[13px] text-ink"
        >
          {stripSubPrefix ? (
            <SubredditName
              name={tag}
              className="text-[13px] text-ink"
              mono={false}
            />
          ) : (
            <span className="truncate">{tag}</span>
          )}
          <button
            type="button"
            aria-label={`Remove ${tag}`}
            disabled={disabled}
            onClick={() => removeAt(index)}
            className="rounded-sm text-ink-3 transition-colors hover:text-ink"
          >
            <IconX size={12} />
          </button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        disabled={disabled}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => {
          if (draft.trim()) addFromText(draft);
        }}
        placeholder={values.length ? "" : placeholder}
        className="min-w-[8rem] flex-1 border-0 bg-transparent px-1 py-1 text-[14px] text-ink outline-none placeholder:text-ink-3"
      />
    </div>
  );
}
