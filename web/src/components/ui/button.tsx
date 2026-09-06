import { cn } from "@/lib/cn";
import { IconLoader } from "./icons";

type ButtonVariant =
  | "primary"
  | "secondary"
  | "soft"
  | "ghost"
  | "danger"
  | "danger-soft";
type ButtonSize = "sm" | "md" | "lg";

const variantClasses: Record<ButtonVariant, string> = {
  primary: "bg-ink text-white hover:bg-ink-2",
  secondary:
    "bg-surface-2 text-ink shadow-float hover:bg-surface",
  soft: "bg-accent-50 text-ink hover:bg-accent-100",
  ghost: "text-ink-2 hover:bg-well hover:text-ink",
  danger: "bg-clay-100 text-ink hover:bg-clay-200",
  "danger-soft": "bg-clay-50 text-clay-300 hover:bg-clay-100",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5 rounded-control",
  md: "h-10 px-4 text-[14px] gap-2 rounded-control",
  lg: "h-11 px-5 text-[15px] gap-2 rounded-control",
};

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  leading?: React.ReactNode;
  trailing?: React.ReactNode;
  loading?: boolean;
}

export function Button({
  variant = "primary",
  size = "md",
  leading,
  trailing,
  loading,
  disabled,
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center font-medium transition-colors duration-200 ease-[var(--ease-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-200 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas disabled:opacity-50 disabled:pointer-events-none squircle",
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    >
      {loading ? (
        <IconLoader size={16} />
      ) : (
        leading && <span className="shrink-0">{leading}</span>
      )}
      {children}
      {!loading && trailing && <span className="shrink-0">{trailing}</span>}
    </button>
  );
}
