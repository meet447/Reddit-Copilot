import { cn } from "@/lib/cn";

type SurfaceTone = "surface" | "raised" | "well" | "canvas";
type SurfaceRadius = "control" | "field" | "card" | "panel" | "sheet";
type SurfaceElevation = "none" | "soft" | "float" | "pop";

const toneClasses: Record<SurfaceTone, string> = {
  surface: "bg-surface",
  raised: "bg-surface-2",
  well: "bg-well",
  canvas: "bg-canvas",
};

const radiusClasses: Record<SurfaceRadius, string> = {
  control: "rounded-control",
  field: "rounded-field",
  card: "rounded-card",
  panel: "rounded-panel",
  sheet: "rounded-sheet",
};

const elevationClasses: Record<SurfaceElevation, string> = {
  none: "",
  soft: "shadow-soft",
  float: "shadow-float",
  pop: "shadow-pop",
};

export interface SurfaceProps extends React.HTMLAttributes<HTMLDivElement> {
  tone?: SurfaceTone;
  radius?: SurfaceRadius;
  elevation?: SurfaceElevation;
  interactive?: boolean;
  as?: "div" | "section" | "article";
}

export function Surface({
  tone = "surface",
  radius = "card",
  elevation = "none",
  interactive,
  as: Tag = "div",
  className,
  children,
  ...props
}: SurfaceProps) {
  return (
    <Tag
      className={cn(
        toneClasses[tone],
        radiusClasses[radius],
        elevationClasses[elevation],
        interactive &&
          "transition-colors duration-200 ease-[var(--ease-soft)] hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-200",
        "squircle",
        className,
      )}
      {...props}
    >
      {children}
    </Tag>
  );
}
