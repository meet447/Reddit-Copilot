"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getSchedule,
  scheduleDraft,
  unscheduleDraft,
  type Draft,
} from "@/lib/api";
import {
  formatDateTime,
  fromDatetimeLocalValue,
  toDatetimeLocalValue,
} from "@/lib/format";
import { Button } from "@/components/ui/button";
import { ApiDownNotice } from "@/components/ui/notice";
import { Pill } from "@/components/ui/pill";
import { Surface } from "@/components/ui/surface";
import { Field, Label, Input } from "@/components/ui/field";
import { Mascot } from "@/components/ui/mascot";
import { AsciiAccent } from "@/components/ui/ascii-accent";

function groupByDay(items: Draft[]): Map<string, Draft[]> {
  const map = new Map<string, Draft[]>();
  for (const item of items) {
    if (!item.run_at) continue;
    const day = new Date(item.run_at).toLocaleDateString(undefined, {
      weekday: "long",
      month: "short",
      day: "numeric",
    });
    const list = map.get(day) ?? [];
    list.push(item);
    map.set(day, list);
  }
  return map;
}

export function ScheduleView() {
  const [items, setItems] = useState<Draft[]>([]);
  const [loading, setLoading] = useState(true);
  const [apiDown, setApiDown] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getSchedule();
      setItems(data);
      setApiDown(false);
    } catch {
      setApiDown(true);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const grouped = groupByDay(items);

  async function handleReschedule(draftId: number) {
    setBusy(draftId);
    try {
      await scheduleDraft(draftId, fromDatetimeLocalValue(editValue));
      setEditingId(null);
      await load();
    } catch {
      setApiDown(true);
    } finally {
      setBusy(null);
    }
  }

  async function handleCancel(draftId: number) {
    setBusy(draftId);
    try {
      await unscheduleDraft(draftId);
      await load();
    } catch {
      setApiDown(true);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <header className="shrink-0 border-b border-line px-6 py-4">
        <h1 className="text-[22px] font-semibold text-ink tracking-tight">
          Schedule
        </h1>
        <p className="mt-0.5 text-[13px] text-ink-3">
          Approved replies queued for later.
        </p>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {apiDown && <ApiDownNotice />}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Mascot mood="thinking" />
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <AsciiAccent className="mb-4" />
            <Mascot mood="neutral" className="mb-4" />
            <p className="max-w-sm text-[15px] text-ink-2">
              Nothing scheduled yet. Approve a draft and pick a time.
            </p>
          </div>
        ) : (
          Array.from(grouped.entries()).map(([day, dayItems]) => (
            <section key={day}>
              <AsciiAccent className="mb-3" width="short" />
              <h2 className="text-[15px] font-semibold text-ink mb-3">
                {day}
              </h2>
              <div className="space-y-2">
                {dayItems.map((item) => (
                  <Surface
                    key={item.id}
                    tone="surface"
                    radius="card"
                    elevation="soft"
                    className="p-4 squircle"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Pill
                            status={
                              item.status === "posted"
                                ? "posted"
                                : item.status === "error"
                                  ? "error"
                                  : "scheduled"
                            }
                          />
                          <span className="text-[12px] font-mono text-ink-3">
                            r/{item.subreddit}
                          </span>
                        </div>
                        <p className="text-[14px] font-medium text-ink truncate">
                          {item.title}
                        </p>
                        <p className="mt-1 text-[13px] text-ink-2 line-clamp-1">
                          {item.body}
                        </p>
                        <p className="mt-2 text-[12px] text-ink-3">
                          {item.run_at ? formatDateTime(item.run_at) : "No time set"}
                        </p>
                      </div>
                      <div className="flex shrink-0 flex-col gap-2">
                        {editingId === item.id ? (
                          <div className="w-48 space-y-2">
                            <Field>
                              <Label htmlFor={`edit-${item.id}`} className="sr-only">
                                New time
                              </Label>
                              <Input
                                id={`edit-${item.id}`}
                                type="datetime-local"
                                value={editValue}
                                onChange={(e) => setEditValue(e.target.value)}
                              />
                            </Field>
                            <div className="flex gap-1">
                              <Button
                                size="sm"
                                loading={busy === item.id}
                                onClick={() => handleReschedule(item.id)}
                              >
                                Save
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => setEditingId(null)}
                              >
                                Cancel
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <>
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled={
                                item.status === "posted" || busy === item.id
                              }
                              onClick={() => {
                                setEditingId(item.id);
                                setEditValue(toDatetimeLocalValue(item.run_at));
                              }}
                            >
                              Edit time
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              loading={busy === item.id}
                              disabled={item.status === "posted"}
                              onClick={() => handleCancel(item.id)}
                            >
                              Cancel
                            </Button>
                          </>
                        )}
                      </div>
                    </div>
                  </Surface>
                ))}
              </div>
            </section>
          ))
        )}
      </div>
    </div>
  );
}
