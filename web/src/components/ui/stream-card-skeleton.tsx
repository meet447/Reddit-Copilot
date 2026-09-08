import { cn } from "@/lib/cn";
import { Surface } from "@/components/ui/surface";

export const STREAM_SLOT_COUNT = 5;

function Bone({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "block rounded-control bg-well-2 motion-safe:animate-bone [animation-delay:var(--bone-delay,0ms)]",
        className,
      )}
    />
  );
}

export function StreamCardSkeleton({
  kind,
  delayMs = 0,
}: {
  kind: "discover" | "post";
  delayMs?: number;
}) {
  return (
    <Surface
      tone="surface"
      radius="card"
      elevation="soft"
      aria-hidden
      className="p-4 squircle"
      style={{ ["--bone-delay" as string]: `${delayMs}ms` }}
    >
      {kind === "discover" ? (
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <Bone className="h-4 w-4 rounded-full" />
              <Bone className="h-3 w-24" />
            </div>
            <Bone className="mt-2 h-4 w-[88%]" />
            <Bone className="mt-1.5 h-4 w-[62%]" />
            <Bone className="mt-3 h-3 w-full" />
            <Bone className="mt-1.5 h-3 w-4/5" />
            <div className="mt-3 flex gap-1.5">
              <Bone className="h-5 w-16" />
              <Bone className="h-5 w-20" />
            </div>
          </div>
          <div className="flex shrink-0 flex-col gap-2">
            <Bone className="h-8 w-14" />
            <Bone className="h-8 w-14" />
          </div>
        </div>
      ) : (
        <>
          <div className="mb-2 flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <Bone className="h-4 w-4 rounded-full" />
                <Bone className="h-3 w-28" />
              </div>
              <Bone className="mt-2 h-4 w-[72%]" />
            </div>
            <Bone className="h-5 w-16" />
          </div>
          <Bone className="h-3 w-full" />
          <Bone className="mt-1.5 h-3 w-[94%]" />
          <Bone className="mt-1.5 h-3 w-3/4" />
          <div className="mt-4 flex flex-wrap gap-2">
            <Bone className="h-8 w-[4.75rem]" />
            <Bone className="h-8 w-[8.5rem]" />
            <Bone className="h-8 w-[4.5rem]" />
            <Bone className="h-8 w-12" />
            <Bone className="h-8 w-14" />
          </div>
        </>
      )}
    </Surface>
  );
}

export function StreamCardSkeletons({
  kind,
  count,
}: {
  kind: "discover" | "post";
  count: number;
}) {
  if (count < 1) return null;
  return Array.from({ length: count }, (_, index) => (
    <StreamCardSkeleton
      key={`${kind}-skeleton-${index}`}
      kind={kind}
      delayMs={index * 90}
    />
  ));
}
