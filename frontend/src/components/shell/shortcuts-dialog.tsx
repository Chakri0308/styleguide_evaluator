"use client";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Kbd } from "@/components/ui/kbd";
import { useUIState } from "@/lib/ui-state";

const SHORTCUTS: [string[], string][] = [
  [["⌘", "K"], "Search guides and jump anywhere"],
  [["⌘", "U"], "Upload a document"],
  [["⌘", "J"], "Open or close the assistant"],
  [["/"], "Ask the guide"],
  [["Esc"], "Close the source viewer or dialog"],
  [["?"], "Show this list"],
];

export function ShortcutsDialog() {
  const ui = useUIState();
  return (
    <Dialog open={ui.shortcutsOpen} onOpenChange={ui.setShortcutsOpen}>
      <DialogContent className="w-[min(92vw,420px)]">
        <DialogTitle className="font-display text-2xl">Keyboard shortcuts</DialogTitle>
        <DialogDescription className="mt-1 text-[13px] text-fg-muted">Use Ctrl instead of ⌘ on Windows and Linux.</DialogDescription>
        <dl className="mt-4 divide-y divide-border">
          {SHORTCUTS.map(([keys, label]) => (
            <div key={label} className="flex items-center justify-between py-2.5 text-[13.5px]">
              <dt className="text-fg-muted">{label}</dt>
              <dd className="flex gap-1">
                {keys.map((k) => (
                  <Kbd key={k}>{k}</Kbd>
                ))}
              </dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  );
}
