"use client";

import * as React from "react";

type Role = "reference" | "candidate";
type SetBool = React.Dispatch<React.SetStateAction<boolean>>;

export interface CitationTarget {
  chunkId: string;
  guideId?: string;
}

interface UIState {
  paletteOpen: boolean;
  setPaletteOpen: SetBool;
  chatOpen: boolean;
  setChatOpen: SetBool;
  chatExpanded: boolean;
  setChatExpanded: SetBool;
  focusChat: () => void;
  registerChatInput: (el: HTMLTextAreaElement | null) => void;
  uploadRole: Role | null;
  uploadFile: File | null;
  openUpload: (role: Role, file?: File) => void;
  closeUpload: () => void;
  /** Guide the chat is scoped to (current page context). */
  chatGuideId: string | null;
  setChatGuideId: (id: string | null) => void;
  chatComparisonId: string | null;
  setChatComparisonId: (id: string | null) => void;
  /** Open the source viewer at a chunk (citation click). */
  sourceTarget: CitationTarget | null;
  openSource: (t: CitationTarget | null) => void;
}

const Ctx = React.createContext<UIState | null>(null);

export function UIStateProvider({ children }: { children: React.ReactNode }) {
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const [chatOpen, setChatOpen] = React.useState(false);
  const [chatExpanded, setChatExpanded] = React.useState(false);
  const [uploadRole, setUploadRole] = React.useState<Role | null>(null);
  const [uploadFile, setUploadFile] = React.useState<File | null>(null);
  const [chatGuideId, setChatGuideId] = React.useState<string | null>(null);
  const [chatComparisonId, setChatComparisonId] = React.useState<string | null>(null);
  const [sourceTarget, setSourceTarget] = React.useState<CitationTarget | null>(null);
  const chatInput = React.useRef<HTMLTextAreaElement | null>(null);

  const value = React.useMemo<UIState>(
    () => ({
      paletteOpen,
      setPaletteOpen,
      chatOpen,
      setChatOpen,
      chatExpanded,
      setChatExpanded,
      focusChat: () => requestAnimationFrame(() => chatInput.current?.focus()),
      registerChatInput: (el) => {
        chatInput.current = el;
      },
      uploadRole,
      uploadFile,
      openUpload: (role, file) => {
        setUploadFile(file ?? null);
        setUploadRole(role);
      },
      closeUpload: () => {
        setUploadRole(null);
        setUploadFile(null);
      },
      chatGuideId,
      setChatGuideId,
      chatComparisonId,
      setChatComparisonId,
      sourceTarget,
      openSource: setSourceTarget,
    }),
    [paletteOpen, chatOpen, chatExpanded, uploadRole, uploadFile, chatGuideId, chatComparisonId, sourceTarget],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useUIState() {
  const ctx = React.useContext(Ctx);
  if (!ctx) throw new Error("useUIState must be used inside UIStateProvider");
  return ctx;
}
