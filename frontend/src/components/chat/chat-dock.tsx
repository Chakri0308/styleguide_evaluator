"use client";

import {
  ArrowUp,
  Check,
  Copy,
  GitCompareArrows,
  Maximize2,
  MessageSquareText,
  Minimize2,
  RotateCcw,
  Square,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Tooltip } from "@/components/ui/tooltip";
import { useChat, type ChatMessage } from "@/lib/chat";
import { useGuides } from "@/lib/queries";
import { useUIState } from "@/lib/ui-state";
import { cn } from "@/lib/utils";
import { Answer } from "./answer";

const STARTERS = [
  "What are the primary brand colors?",
  "Which typefaces should headlines use?",
  "What are the logo don'ts?",
  "How should we write dates and numbers?",
];

const STAGE_LABEL: Record<string, string> = {
  retrieving: "Searching the guide",
  generating: "Reading the sources",
  writing: "Writing",
};

function useStored<T>(key: string, initial: T) {
  const [v, setV] = React.useState<T>(initial);
  React.useEffect(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw) setV(JSON.parse(raw));
    } catch {
      /* ignore */
    }
  }, [key]);
  const set = React.useCallback(
    (val: T) => {
      setV(val);
      try {
        localStorage.setItem(key, JSON.stringify(val));
      } catch {
        /* ignore */
      }
    },
    [key],
  );
  return [v, set] as const;
}

function AssistantMessage({
  m,
  guideId,
  last,
  onFollowup,
}: {
  m: ChatMessage;
  guideId: string;
  last: boolean;
  onFollowup: (q: string) => void;
}) {
  const chat = useChat();
  const [copied, setCopied] = React.useState(false);
  const streaming = m.status === "streaming";
  return (
    <div className="group/msg flex gap-2.5">
      <span aria-hidden className="mt-1 grid size-5 shrink-0 place-items-center rounded-md bg-fg text-bg">
        <span className="size-2 rounded-full border-2 border-current" />
      </span>
      <div className="min-w-0 flex-1">
        {streaming && !m.content ? (
          <p className="flex items-center gap-2 text-[13px] text-fg-subtle" aria-live="polite">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent/60" />
              <span className="relative inline-flex size-2 rounded-full bg-accent" />
            </span>
            {STAGE_LABEL[m.stage ?? "retrieving"] ?? "Thinking"}…
          </p>
        ) : m.status === "error" ? (
          <p className="text-[13.5px] text-bad">{m.content}</p>
        ) : (
          <div aria-live={streaming ? "polite" : undefined}>
            <Answer content={m.content} citations={m.citations} sources={m.sources} />
            {streaming && <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-[3px] animate-pulse bg-accent" />}
          </div>
        )}

        {m.status === "done" && m.content && (
          <div className="mt-2 flex items-center gap-0.5 text-fg-subtle opacity-70 transition-opacity group-hover/msg:opacity-100">
            <Tooltip content={copied ? "Copied" : "Copy answer"}>
              <button
                className="rounded p-1 hover:bg-surface-sunken hover:text-fg"
                aria-label="Copy answer"
                onClick={async () => {
                  await navigator.clipboard.writeText(m.content.replace(/\[(\d+)\]/g, "[$1]"));
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1400);
                }}
              >
                {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
              </button>
            </Tooltip>
            {m.id && (
              <>
                <Tooltip content="Good answer">
                  <button
                    aria-label="Good answer"
                    aria-pressed={m.rating === 1}
                    className={cn("rounded p-1 hover:bg-surface-sunken hover:text-fg", m.rating === 1 && "text-ok")}
                    onClick={() => chat.rate(guideId, m.key, 1).then(() => toast.success("Thanks for the feedback"))}
                  >
                    <ThumbsUp className="size-3.5" />
                  </button>
                </Tooltip>
                <Tooltip content="Bad answer">
                  <button
                    aria-label="Bad answer"
                    aria-pressed={m.rating === -1}
                    className={cn("rounded p-1 hover:bg-surface-sunken hover:text-fg", m.rating === -1 && "text-bad")}
                    onClick={() => chat.rate(guideId, m.key, -1).then(() => toast("Feedback saved for evaluation"))}
                  >
                    <ThumbsDown className="size-3.5" />
                  </button>
                </Tooltip>
              </>
            )}
            <span className="ml-auto flex items-center gap-1.5 text-[10.5px]">
              {m.mode === "extractive" && (
                <Tooltip content="No LLM is configured, so this answer quotes the guide directly.">
                  <span className="rounded bg-surface-sunken px-1.5 py-0.5">quoted</span>
                </Tooltip>
              )}
              {m.cached && (
                <Tooltip content="Same question, same sources: served the identical earlier answer.">
                  <span className="rounded bg-surface-sunken px-1.5 py-0.5">consistent</span>
                </Tooltip>
              )}
              {m.citations.length > 0 && `${m.citations.length} source${m.citations.length > 1 ? "s" : ""}`}
            </span>
          </div>
        )}

        {last && m.status === "done" && m.followups.length > 0 && (
          <div className="mt-3 flex flex-col items-start gap-1.5">
            {m.followups.map((q) => (
              <button
                key={q}
                onClick={() => onFollowup(q)}
                className="rounded-full border border-border bg-surface px-3 py-1 text-left text-[12.5px] text-fg-muted transition-colors hover:border-accent/40 hover:bg-accent-soft hover:text-accent-soft-fg"
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function ChatPanel({ mode }: { mode: "floating" | "side" }) {
  const ui = useUIState();
  const chat = useChat();
  const { data: guides } = useGuides();
  const refs = (guides ?? []).filter((g) => g.role === "reference" && g.status === "ready");
  const guideId = ui.chatGuideId && refs.some((g) => g.id === ui.chatGuideId) ? ui.chatGuideId : refs[0]?.id;
  const guide = refs.find((g) => g.id === guideId);
  const thread = guideId ? chat.thread(guideId) : { messages: [], conversationId: null };
  const [draft, setDraft] = React.useState("");
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);
  const comparisonId = ui.chatComparisonId;

  React.useEffect(() => {
    if (guideId) void chat.restore(guideId);
  }, [guideId, chat]);

  React.useEffect(() => {
    ui.registerChatInput(inputRef.current);
    return () => ui.registerChatInput(null);
  }, [ui]);

  const lastContent = thread.messages.at(-1)?.content.length ?? 0;
  React.useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 160;
    if (nearBottom || thread.messages.at(-1)?.role === "user") el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [thread.messages.length, lastContent, thread.messages]);

  const submit = (text = draft) => {
    if (!guideId || !text.trim() || chat.busy) return;
    void chat.send(guideId, text, comparisonId);
    setDraft("");
    requestAnimationFrame(() => {
      if (inputRef.current) inputRef.current.style.height = "auto";
    });
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border pl-3.5 pr-2">
        <MessageSquareText className="size-4 text-accent" />
        {refs.length > 1 ? (
          <select
            aria-label="Guide to ask"
            value={guideId}
            onChange={(e) => ui.setChatGuideId(e.target.value)}
            className="h-7 min-w-0 max-w-[60%] truncate rounded-md bg-transparent pr-1 text-[13px] font-medium outline-none hover:bg-surface-sunken focus-visible:ring-2 focus-visible:ring-ring"
          >
            {refs.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        ) : (
          <span className="min-w-0 truncate text-[13px] font-medium">{guide?.name ?? "Ask the guide"}</span>
        )}
        {comparisonId && (
          <Tooltip content="Answers can explain the open comparison's findings">
            <span className="flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-medium text-accent-soft-fg">
              <GitCompareArrows className="size-3" /> comparison
            </span>
          </Tooltip>
        )}
        <div className="ml-auto flex items-center">
          {thread.messages.length > 0 && guideId && (
            <Tooltip content="New conversation">
              <Button variant="ghost" size="icon-sm" aria-label="New conversation" onClick={() => chat.reset(guideId)}>
                <RotateCcw />
              </Button>
            </Tooltip>
          )}
          <Tooltip content={mode === "side" ? "Float" : "Expand to side panel"}>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={mode === "side" ? "Float the assistant" : "Expand the assistant"}
              onClick={() => ui.setChatExpanded((e) => !e)}
            >
              {mode === "side" ? <Minimize2 /> : <Maximize2 />}
            </Button>
          </Tooltip>
          <Tooltip content="Close (⌘J)">
            <Button variant="ghost" size="icon-sm" aria-label="Close assistant" onClick={() => ui.setChatOpen(false)}>
              <X />
            </Button>
          </Tooltip>
        </div>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-4" role="log" aria-label="Conversation">
        {!guide ? (
          <div className="grid h-full place-items-center px-6 text-center">
            <div>
              <p className="font-display text-2xl">Nothing to ask yet</p>
              <p className="mt-1.5 text-[13px] text-fg-muted">Upload a reference guide and I&apos;ll answer questions about it — with sources.</p>
              <Button className="mt-4" variant="primary" size="sm" onClick={() => ui.openUpload("reference")}>
                Upload a guide
              </Button>
            </div>
          </div>
        ) : thread.messages.length === 0 ? (
          <div className="flex h-full flex-col justify-end">
            <p className="font-display text-[26px] leading-tight">Ask {guide.name}</p>
            <p className="mt-1 text-[13px] text-fg-muted">
              Answers come only from the guide, with numbered sources that open the exact passage.
            </p>
            <div className="mt-4 flex flex-col items-start gap-1.5">
              {STARTERS.map((q) => (
                <button
                  key={q}
                  onClick={() => submit(q)}
                  className="rounded-full border border-border bg-surface px-3 py-1.5 text-left text-[13px] text-fg-muted transition-colors hover:border-accent/40 hover:bg-accent-soft hover:text-accent-soft-fg"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            {thread.messages.map((m, i) =>
              m.role === "user" ? (
                <div key={m.key} className="flex justify-end">
                  <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-fg px-3.5 py-2 text-[13.5px] text-bg">
                    {m.content}
                  </p>
                </div>
              ) : (
                <AssistantMessage
                  key={m.key}
                  m={m}
                  guideId={guideId!}
                  last={i === thread.messages.length - 1}
                  onFollowup={(q) => submit(q)}
                />
              ),
            )}
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="shrink-0 border-t border-border p-2.5"
      >
        <div className="flex items-end gap-2 rounded-xl border border-border bg-surface px-3 py-2 shadow-sm transition-shadow focus-within:border-accent/50 focus-within:ring-2 focus-within:ring-ring">
          <textarea
            ref={inputRef}
            rows={1}
            value={draft}
            disabled={!guide}
            placeholder={guide ? "Ask about colors, type, logo, voice…" : "Upload a guide first"}
            aria-label="Message"
            onChange={(e) => {
              setDraft(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            className="max-h-40 min-h-6 flex-1 resize-none bg-transparent text-[14px] leading-6 outline-none placeholder:text-fg-subtle"
          />
          {chat.busy ? (
            <Button type="button" size="icon-sm" variant="secondary" aria-label="Stop" onClick={chat.stop}>
              <Square className="!size-3 fill-current" />
            </Button>
          ) : (
            <Button type="submit" size="icon-sm" variant="primary" aria-label="Send" disabled={!draft.trim() || !guide}>
              <ArrowUp />
            </Button>
          )}
        </div>
        <p className="mt-1.5 px-1 text-[10.5px] text-fg-subtle">
          <Kbd className="h-4 min-w-4 text-[10px]">↵</Kbd> send · <Kbd className="h-4 min-w-4 text-[10px]">⇧↵</Kbd> new line
        </p>
      </form>
    </div>
  );
}

/** Floating dock (bottom-right) with a launcher; resizable from its top-left corner. */
export function ChatDock() {
  const ui = useUIState();
  const [size, setSize] = useStored("stylelens-chat-size", { w: 420, h: 620 });
  const dragging = React.useRef<{ x: number; y: number; w: number; h: number } | null>(null);

  const onPointerDown = (e: React.PointerEvent) => {
    dragging.current = { x: e.clientX, y: e.clientY, w: size.w, h: size.h };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = dragging.current;
    if (!d) return;
    setSize({
      w: Math.round(Math.min(Math.max(d.w + (d.x - e.clientX), 340), Math.min(760, window.innerWidth - 32))),
      h: Math.round(Math.min(Math.max(d.h + (d.y - e.clientY), 420), window.innerHeight - 96)),
    });
  };
  const floating = ui.chatOpen && !ui.chatExpanded;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-40 flex flex-col items-end gap-3">
      <AnimatePresence>
        {floating && (
          <motion.section
            key="dock"
            aria-label="Guide assistant"
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 460, damping: 38 }}
            style={{ width: `min(${size.w}px, calc(100vw - 32px))`, height: `min(${size.h}px, calc(100dvh - 96px))` }}
            className="glass pointer-events-auto relative origin-bottom-right overflow-hidden rounded-2xl border border-border shadow-lg"
          >
            <div
              role="separator"
              aria-label="Resize assistant"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={() => (dragging.current = null)}
              className="absolute left-0 top-0 z-10 size-4 cursor-nwse-resize"
            />
            <ChatPanel mode="floating" />
          </motion.section>
        )}
      </AnimatePresence>
      {!ui.chatOpen && (
        <motion.button
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          whileHover={{ y: -1 }}
          whileTap={{ scale: 0.97 }}
          onClick={() => {
            ui.setChatOpen(true);
            ui.focusChat();
          }}
          aria-expanded={ui.chatOpen}
          className="pointer-events-auto flex h-10 items-center gap-2 rounded-full bg-fg pl-3.5 pr-2.5 text-sm font-medium text-bg shadow-lg"
        >
          <MessageSquareText className="size-4" />
          Ask the guide
          <Kbd className="border-transparent bg-bg/15 text-bg/80">⌘J</Kbd>
        </motion.button>
      )}
    </div>
  );
}

/** Side-panel mode: a resizable column on the right edge of the layout. */
export function ChatSidePanel() {
  const ui = useUIState();
  const [width, setWidth] = useStored("stylelens-chat-side-width", 440);
  const drag = React.useRef<{ x: number; w: number } | null>(null);
  const open = ui.chatOpen && ui.chatExpanded;

  React.useEffect(() => {
    document.documentElement.style.setProperty("--chat-side-width", open ? `${width}px` : "0px");
  }, [open, width]);

  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.aside
          key="side"
          aria-label="Guide assistant"
          initial={{ width: 0, opacity: 0 }}
          animate={{ width, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ type: "spring", stiffness: 420, damping: 40 }}
          className="relative hidden shrink-0 overflow-hidden border-l border-border bg-surface md:block"
        >
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize assistant"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "ArrowLeft") setWidth(Math.min(width + 24, 760));
              if (e.key === "ArrowRight") setWidth(Math.max(width - 24, 340));
            }}
            onPointerDown={(e) => {
              drag.current = { x: e.clientX, w: width };
              (e.target as HTMLElement).setPointerCapture(e.pointerId);
            }}
            onPointerMove={(e) => {
              if (drag.current) setWidth(Math.round(Math.min(Math.max(drag.current.w + drag.current.x - e.clientX, 340), 760)));
            }}
            onPointerUp={() => (drag.current = null)}
            className="absolute inset-y-0 left-0 z-10 w-1.5 cursor-col-resize transition-colors hover:bg-accent/30 focus-visible:bg-accent/40"
          />
          <div style={{ width }} className="h-full">
            <ChatPanel mode="side" />
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
