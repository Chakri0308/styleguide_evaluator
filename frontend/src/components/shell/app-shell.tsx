"use client";

import * as React from "react";
import { ChatDock } from "@/components/chat/chat-dock";
import { CommandPalette } from "@/components/shell/command-palette";
import { Sidebar } from "@/components/shell/sidebar";
import { SourceViewer } from "@/components/source/source-viewer";
import { UploadDialog } from "@/components/upload/upload-dialog";
import { UIStateProvider, useUIState } from "@/lib/ui-state";

function GlobalShortcuts() {
  const ui = useUIState();
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      const target = e.target as HTMLElement | null;
      const typing = target?.closest("input, textarea, [contenteditable=true]");
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        ui.setPaletteOpen((o) => !o);
      } else if (mod && e.key.toLowerCase() === "j") {
        e.preventDefault();
        ui.setChatOpen((o) => !o);
      } else if (mod && e.key.toLowerCase() === "u") {
        e.preventDefault();
        ui.openUpload("reference");
      } else if (!typing && !mod && e.key === "/") {
        e.preventDefault();
        ui.setChatOpen(true);
        ui.focusChat();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ui]);
  return null;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <UIStateProvider>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[100] focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:shadow-md"
      >
        Skip to content
      </a>
      <div className="flex h-dvh overflow-hidden">
        <Sidebar />
        <main id="main" className="relative min-w-0 flex-1 overflow-hidden">
          {children}
        </main>
      </div>
      <SourceViewer />
      <ChatDock />
      <UploadDialog />
      <CommandPalette />
      <GlobalShortcuts />
    </UIStateProvider>
  );
}
