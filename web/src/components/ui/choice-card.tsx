import { cn } from "@/lib/cn";
import { IconCheck } from "./icons";

export interface ChoiceCardProps {
  selected?: boolean;
  onSelect?: () => void;
  title: string;
  description?: string;
  className?: string;
}

export function ChoiceCard({
  selected,
  onSelect,
  title,
  description,
  className,
}: ChoiceCardProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full text-left p-4 rounded-card transition-all duration-200 ease-[var(--ease-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-200 squircle",
        selected
          ? "bg-accent-50 shadow-soft ring-2 ring-accent-200"
          : "bg-surface hover:bg-surface-2 shadow-soft",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[14px] font-semibold text-ink">{title}</p>
          {description && (
            <p className="mt-1 text-[13px] text-ink-3 leading-relaxed">
              {description}
            </p>
          )}
        </div>
        {selected && (
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-ink text-white">
            <IconCheck size={12} />
          </span>
        )}
      </div>
    </button>
  );
}
