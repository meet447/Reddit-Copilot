"use client";

import { useState } from "react";
import { Rail } from "./rail";
import { SettingsSheet } from "./settings-sheet";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <div className="flex h-screen gap-3 p-3 bg-canvas">
      <Rail onSettingsOpen={() => setSettingsOpen(true)} />
      <main className="flex min-w-0 flex-1 flex-col rounded-panel bg-surface shadow-soft squircle overflow-hidden">
        {children}
      </main>
      <SettingsSheet open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
