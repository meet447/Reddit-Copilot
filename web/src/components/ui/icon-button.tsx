import { cn } from "@/lib/cn";

export interface IconButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  active?: boolean;
  size?: "sm" | "md" | "lg";
}

const sizeClasses = {
  sm: "h-8 w-8 rounded-control",
  md: "h-10 w-10 rounded-control",
  lg: "h-11 w-11 rounded-control",
};

export function iconButtonClassName({
  active,
  size = "md",
  className,
}: {
  active?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  return cn(
    "inline-flex items-center justify-center text-ink-2 transition-colors duration-200 ease-[var(--ease-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-200 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas disabled:opacity-50 squircle",
    active
      ? "bg-surface-2 text-ink shadow-float"
      : "hover:bg-well hover:text-ink",
    sizeClasses[size],
    className,
  );
}

export function IconButton({
  label,
  active,
  size = "md",
  className,
  children,
  ...props
}: IconButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={iconButtonClassName({ active, size, className })}
      {...props}
    >
      {children}
    </button>
  );
}
