"use client";

import { MessageSquareText, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { Kbd } from "@/components/ui/kbd";
import { useUIState } from "@/lib/ui-state";

export function ChatDock() {
  const ui = useUIState();
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-40 flex flex-col items-end gap-3">
      <AnimatePresence>
        {ui.chatOpen && (
          <motion.section
            aria-label="Guide assistant"
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            className="glass pointer-events-auto flex h-[520px] w-[400px] flex-col rounded-xl border border-border shadow-lg"
          >
            <header className="flex h-11 items-center justify-between border-b border-border px-3">
              <span className="text-sm font-medium">Ask the guide</span>
              <button
                aria-label="Close assistant"
                onClick={() => ui.setChatOpen(false)}
                className="rounded p-1 text-fg-subtle hover:bg-surface-sunken hover:text-fg"
              >
                <X className="size-4" />
              </button>
            </header>
            <div className="grid flex-1 place-items-center p-6 text-center text-sm text-fg-subtle">
              The assistant arrives in milestone 5.
            </div>
          </motion.section>
        )}
      </AnimatePresence>
      <motion.button
        whileHover={{ y: -1 }}
        whileTap={{ scale: 0.97 }}
        onClick={() => ui.setChatOpen((o) => !o)}
        aria-expanded={ui.chatOpen}
        className="pointer-events-auto flex h-10 items-center gap-2 rounded-full bg-fg pl-3.5 pr-2.5 text-sm font-medium text-bg shadow-lg"
      >
        <MessageSquareText className="size-4" />
        Ask the guide
        <Kbd className="border-transparent bg-bg/15 text-bg/80">⌘J</Kbd>
      </motion.button>
    </div>
  );
}
