"use client";

import * as React from "react";
import { API_BASE } from "./api";

export interface Citation {
  n: number;
  chunk_id: string;
  guide_id: string;
  guide_name: string;
  version_id: string;
  kind: string;
  page: number;
  regions: { page: number; bbox?: number[] | null; element_id?: string }[];
  heading_path: string[];
  snippet: string;
  score: number;
  element_ids: string[];
  supported?: boolean;
}

export interface ChatMessage {
  key: string;
  id?: string;
  role: "user" | "assistant";
  content: string;
  sources: Citation[];
  citations: Citation[];
  followups: string[];
  status: "streaming" | "done" | "error";
  stage?: string;
  mode?: string;
  cached?: boolean;
  rating?: -1 | 0 | 1;
}

interface Thread {
  conversationId: string | null;
  messages: ChatMessage[];
}

interface ChatState {
  thread: (guideId: string) => Thread;
  restore: (guideId: string) => Promise<void>;
  send: (guideId: string, text: string, comparisonId?: string | null) => Promise<void>;
  stop: () => void;
  reset: (guideId: string) => void;
  rate: (guideId: string, key: string, rating: -1 | 1) => Promise<void>;
  busy: boolean;
}

const Ctx = React.createContext<ChatState | null>(null);
const STORE_KEY = "stylelens-chat-conversations";

function loadConversationIds(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveConversationId(guideId: string, id: string | null) {
  try {
    const all = loadConversationIds();
    if (id) all[guideId] = id;
    else delete all[guideId];
    localStorage.setItem(STORE_KEY, JSON.stringify(all));
  } catch {
    /* storage unavailable */
  }
}

/** Minimal SSE parser for a fetch() body stream (EventSource can't POST). */
async function* readSSE(res: Response): AsyncGenerator<{ event: string; data: unknown }> {
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) {
        try {
          yield { event, data: JSON.parse(data.join("\n")) };
        } catch {
          /* ignore malformed */
        }
      }
    }
  }
}

let keySeq = 0;
const nextKey = () => `m${Date.now().toString(36)}${(keySeq++).toString(36)}`;

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [threads, setThreads] = React.useState<Record<string, Thread>>({});
  const [busy, setBusy] = React.useState(false);
  const abortRef = React.useRef<AbortController | null>(null);
  const loaded = React.useRef(new Set<string>());

  const update = React.useCallback((guideId: string, fn: (t: Thread) => Thread) => {
    setThreads((prev) => ({ ...prev, [guideId]: fn(prev[guideId] ?? { conversationId: null, messages: [] }) }));
  }, []);

  const patchMessage = React.useCallback(
    (guideId: string, key: string, patch: Partial<ChatMessage> | ((m: ChatMessage) => Partial<ChatMessage>)) =>
      update(guideId, (t) => ({
        ...t,
        messages: t.messages.map((m) => (m.key === key ? { ...m, ...(typeof patch === "function" ? patch(m) : patch) } : m)),
      })),
    [update],
  );

  // Restore the last conversation for a guide from the server
  const restore = React.useCallback(
    async (guideId: string) => {
      if (loaded.current.has(guideId)) return;
      loaded.current.add(guideId);
      const convId = loadConversationIds()[guideId];
      if (!convId) return;
      try {
        const res = await fetch(`${API_BASE}/conversations/${convId}/messages`);
        if (!res.ok) return;
        const rows: { id: string; role: "user" | "assistant"; content: string; citations: Citation[]; meta: Record<string, unknown> }[] =
          await res.json();
        update(guideId, (t) =>
          t.messages.length
            ? t
            : {
                conversationId: convId,
                messages: rows.map((r) => ({
                  key: r.id,
                  id: r.id,
                  role: r.role,
                  content: r.content,
                  sources: r.citations,
                  citations: r.citations,
                  followups: (r.meta?.followups as string[]) ?? [],
                  status: "done",
                  mode: r.meta?.mode as string | undefined,
                })),
              },
        );
      } catch {
        /* offline */
      }
    },
    [update],
  );

  const thread = React.useCallback(
    (guideId: string) => threads[guideId] ?? { conversationId: null, messages: [] },
    [threads],
  );

  const send = React.useCallback(
    async (guideId: string, text: string, comparisonId?: string | null) => {
      const question = text.trim();
      if (!question || busy) return;
      const userKey = nextKey();
      const botKey = nextKey();
      const current = threads[guideId];
      update(guideId, (t) => ({
        ...t,
        messages: [
          ...t.messages,
          { key: userKey, role: "user", content: question, sources: [], citations: [], followups: [], status: "done" },
          { key: botKey, role: "assistant", content: "", sources: [], citations: [], followups: [], status: "streaming", stage: "retrieving" },
        ],
      }));
      setBusy(true);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const res = await fetch(`${API_BASE}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify({
            guide_id: guideId,
            message: question,
            conversation_id: current?.conversationId ?? undefined,
            comparison_id: comparisonId ?? undefined,
          }),
          signal: controller.signal,
        });
        if (!res.ok || !res.body) throw new Error(`Request failed (${res.status})`);
        for await (const { event, data } of readSSE(res)) {
          const d = data as Record<string, unknown>;
          if (event === "status") {
            patchMessage(guideId, botKey, { stage: d.stage as string });
            if (d.conversation_id) {
              update(guideId, (t) => ({ ...t, conversationId: d.conversation_id as string }));
              saveConversationId(guideId, d.conversation_id as string);
            }
          } else if (event === "sources") {
            patchMessage(guideId, botKey, { sources: d.sources as Citation[] });
          } else if (event === "token") {
            patchMessage(guideId, botKey, (m) => ({ content: m.content + (d.text as string), stage: "writing" }));
          } else if (event === "citations") {
            patchMessage(guideId, botKey, { citations: d.citations as Citation[], content: d.answer as string });
          } else if (event === "followups") {
            patchMessage(guideId, botKey, { followups: d.questions as string[] });
          } else if (event === "done") {
            patchMessage(guideId, botKey, {
              status: "done",
              id: d.message_id as string,
              mode: d.mode as string,
              cached: d.cached as boolean,
            });
          } else if (event === "error") {
            patchMessage(guideId, botKey, { status: "error", content: (d.message as string) ?? "Something went wrong." });
          }
        }
        patchMessage(guideId, botKey, (m) => (m.status === "streaming" ? { status: "done" } : {}));
      } catch (err) {
        const aborted = (err as Error).name === "AbortError";
        patchMessage(guideId, botKey, (m) => ({
          status: aborted ? "done" : "error",
          content: aborted ? m.content || "_Stopped._" : `Couldn't reach the assistant. ${(err as Error).message}`,
        }));
      } finally {
        setBusy(false);
        abortRef.current = null;
      }
    },
    [busy, threads, update, patchMessage],
  );

  const value = React.useMemo<ChatState>(
    () => ({
      thread,
      restore,
      send,
      busy,
      stop: () => abortRef.current?.abort(),
      reset: (guideId) => {
        saveConversationId(guideId, null);
        setThreads((prev) => ({ ...prev, [guideId]: { conversationId: null, messages: [] } }));
      },
      rate: async (guideId, key, rating) => {
        const msg = threads[guideId]?.messages.find((m) => m.key === key);
        if (!msg?.id) return;
        patchMessage(guideId, key, { rating });
        await fetch(`${API_BASE}/messages/${msg.id}/feedback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rating }),
        });
      },
    }),
    [thread, restore, send, busy, threads, patchMessage],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useChat() {
  const ctx = React.useContext(Ctx);
  if (!ctx) throw new Error("useChat must be used inside ChatProvider");
  return ctx;
}
