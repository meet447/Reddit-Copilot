"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  listProjects,
  setActiveProject,
  type ProjectSummary,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { IconPlus } from "@/components/ui/icons";

export function ProjectSwitcher({
  onChanged,
}: {
  onChanged?: (id: string) => void;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [activeId, setActiveId] = useState("");
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    listProjects()
      .then((data) => {
        if (cancelled) return;
        setProjects(data.projects ?? []);
        setActiveId(data.active_project_id ?? "");
      })
      .catch(() => {
        if (!cancelled) {
          setProjects([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    function onDoc(event: MouseEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const active =
    projects.find((item) => item.id === activeId) ?? projects[0] ?? null;
  const initial = (active?.name || "W").trim().charAt(0).toUpperCase() || "W";

  async function switchTo(id: string) {
    if (id === activeId) {
      setOpen(false);
      return;
    }
    await setActiveProject(id);
    setActiveId(id);
    setOpen(false);
    onChanged?.(id);
  }

  return (
    <div ref={root} className="relative mb-4">
      <button
        type="button"
        aria-label={active ? `Workspace ${active.name}` : "Workspaces"}
        title={active?.name || "Workspaces"}
        onClick={() => setOpen((value) => !value)}
        className={cn(
          "flex h-10 w-10 items-center justify-center rounded-control text-[13px] font-semibold text-ink",
          "bg-surface-2 shadow-float transition-colors hover:bg-surface",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-200 squircle",
        )}
      >
        {initial}
      </button>
      {open && (
        <div className="absolute left-14 top-0 z-30 w-56 rounded-card bg-surface p-1.5 shadow-pop squircle">
          <p className="px-2 py-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-3">
            Workspaces
          </p>
          <div className="max-h-64 space-y-0.5 overflow-y-auto">
            {projects.map((project) => (
              <button
                key={project.id}
                type="button"
                onClick={() => void switchTo(project.id)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-control px-2 py-2 text-left text-[13px]",
                  project.id === activeId
                    ? "bg-accent-50 text-ink font-medium"
                    : "text-ink-2 hover:bg-well hover:text-ink",
                )}
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-control bg-well text-[11px] font-semibold text-ink">
                  {(project.name || "W").trim().charAt(0).toUpperCase()}
                </span>
                <span className="min-w-0 flex-1 truncate">{project.name}</span>
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              router.push("/onboarding?new=1");
            }}
            className="mt-1 flex w-full items-center gap-2 rounded-control px-2 py-2 text-left text-[13px] text-ink-2 hover:bg-well hover:text-ink"
          >
            <IconPlus size={14} />
            New project
          </button>
        </div>
      )}
    </div>
  );
}
