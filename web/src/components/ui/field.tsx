import { cn } from "@/lib/cn";
import { forwardRef } from "react";

export function Label({
  className,
  children,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        "block text-[13px] font-medium text-ink-2 mb-1.5",
        className,
      )}
      {...props}
    >
      {children}
    </label>
  );
}

export function Field({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return <div className={cn("space-y-1", className)}>{children}</div>;
}

export function Hint({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <p className={cn("text-[12px] text-ink-3 leading-relaxed", className)}>
      {children}
    </p>
  );
}

export function FieldError({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <p className={cn("text-[12px] text-clay-300", className)} role="alert">
      {children}
    </p>
  );
}

const fieldBase =
  "w-full bg-well text-ink placeholder:text-ink-4 transition-all duration-200 ease-[var(--ease-soft)] focus:bg-surface-2 focus:outline-none focus:ring-2 focus:ring-accent-200 squircle";

export function Input({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        fieldBase,
        "h-10 px-3 text-[14px] rounded-field",
        className,
      )}
      {...props}
    />
  );
}

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...props }, ref) {
  return (
    <textarea
      ref={ref}
      className={cn(
        fieldBase,
        "min-h-[120px] px-3 py-2.5 text-[14px] leading-relaxed rounded-field resize-y",
        className,
      )}
      {...props}
    />
  );
});

export function Select({
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        fieldBase,
        "h-10 px-3 text-[14px] rounded-field appearance-none",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}
