"use client";

import type { Components } from "react-markdown";
import Markdown from "react-markdown";
import { cn } from "@/lib/cn";

const components: Components = {
  p: ({ children }) => (
    <p className="mb-2 last:mb-0 text-[14px] leading-[1.55]">{children}</p>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-ink">{children}</strong>
  ),
  em: ({ children }) => <em className="italic">{children}</em>,
  ul: ({ children }) => (
    <ul className="mb-2 list-disc last:mb-0 space-y-1 pl-4 marker:text-ink-3">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-2 list-decimal last:mb-0 space-y-1 pl-4 marker:text-ink-3">
      {children}
    </ol>
  ),
  li: ({ children }) => (
    <li className="text-[14px] leading-[1.55]">{children}</li>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-ink underline decoration-accent-300 underline-offset-2 hover:decoration-accent-400"
    >
      {children}
    </a>
  ),
  code: ({ children, className }) => {
    const block = Boolean(className);
    if (block) {
      return (
        <code className="block overflow-x-auto rounded-field bg-well px-3 py-2 font-mono text-[12px] text-ink-2">
          {children}
        </code>
      );
    }
    return (
      <code className="rounded-[6px] bg-well px-1 py-0.5 font-mono text-[12.5px] text-ink">
        {children}
      </code>
    );
  },
  pre: ({ children }) => <pre className="mb-2 last:mb-0">{children}</pre>,
  h1: ({ children }) => (
    <p className="mb-2 text-[15px] font-semibold tracking-tight last:mb-0">
      {children}
    </p>
  ),
  h2: ({ children }) => (
    <p className="mb-2 text-[15px] font-semibold tracking-tight last:mb-0">
      {children}
    </p>
  ),
  h3: ({ children }) => (
    <p className="mb-2 text-[14px] font-semibold tracking-tight last:mb-0">
      {children}
    </p>
  ),
  blockquote: ({ children }) => (
    <blockquote className="mb-2 border-l-2 border-accent-300 pl-3 text-ink-2 last:mb-0">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-3 border-line" />,
};

export function MarkdownBody({
  text,
  className,
  tone = "agent",
}: {
  text: string;
  className?: string;
  tone?: "agent" | "user";
}) {
  return (
    <div
      className={cn(
        "min-w-0",
        tone === "user"
          ? "text-white [&_p]:text-white [&_strong]:text-white [&_em]:text-white [&_li]:text-white [&_a]:text-accent-200 [&_code]:bg-white/15 [&_code]:text-white [&_blockquote]:border-accent-300 [&_blockquote]:text-white/90"
          : "text-ink [&_p]:text-ink",
        className,
      )}
    >
      <Markdown components={components} skipHtml>
        {text}
      </Markdown>
    </div>
  );
}
