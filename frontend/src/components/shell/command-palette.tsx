"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { useQuery } from "@tanstack/react-query";
import {
  BookMarked,
  FileSearch,
  FileCheck2,
  GitCompareArrows,
  Home,
  Laptop,
  MessageSquareText,
  Moon,
  Sun,
  Upload,
} from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { Kbd } from "@/components/ui/kbd";
import { API_BASE } from "@/lib/api";
import { useComparisons } from "@/lib/comparison-queries";
import { useGuides } from "@/lib/queries";
import { useTheme } from "@/lib/theme";
import { useUIState } from "@/lib/ui-state";

function Item({
  onSelect,
  icon: Icon,
  children,
  shortcut,
  value,
}: {
  onSelect: () => void;
  icon: React.ElementType;
  children: React.ReactNode;
  shortcut?: string;
  value?: string;
}) {
  return (
    <Command.Item
      value={value}
      onSelect={onSelect}
      className="flex h-9 cursor-pointer items-center gap-2.5 rounded-md px-2.5 text-sm text-fg-muted data-[selected=true]:bg-surface-sunken data-[selected=true]:text-fg"
    >
      <Icon className="size-4 shrink-0 text-fg-subtle" />
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {shortcut && <Kbd>{shortcut}</Kbd>}
    </Command.Item>
  );
}

const groupClass =
  "[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.08em] [&_[cmdk-group-heading]]:text-fg-subtle";

interface SearchHit {
  chunk_id: string;
  guide_id: string;
  guide_name: string;
  page: number;
  heading_path: string[];
  snippet: string;
  regions: { page: number; bbox?: number[] | null }[];
  element_ids: string[];
}

function useDebounced<T>(value: T, ms: number) {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function CommandPalette() {
  const ui = useUIState();
  const router = useRouter();
  const { setPref } = useTheme();
  const { data: guides } = useGuides();
  const { data: comparisons } = useComparisons();
  const [input, setInput] = React.useState("");
  const query = useDebounced(input.trim(), 250);
  const { data: results, isFetching } = useQuery({
    queryKey: ["search", query],
    enabled: ui.paletteOpen && query.length >= 3,
    staleTime: 60_000,
    queryFn: async (): Promise<SearchHit[]> => {
      const res = await fetch(`${API_BASE}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k: 6 }),
      });
      if (!res.ok) return [];
      return (await res.json()).hits;
    },
  });

  const run = (fn: () => void) => {
    ui.setPaletteOpen(false);
    fn();
  };

  return (
    <DialogPrimitive.Root
      open={ui.paletteOpen}
      onOpenChange={(o) => {
        ui.setPaletteOpen(o);
        if (!o) setInput("");
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/25 data-[state=open]:animate-[fade-in_120ms_ease-out]" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-[14vh] z-50 w-[min(92vw,600px)] -translate-x-1/2 overflow-hidden rounded-xl border border-border bg-surface-raised shadow-lg data-[state=open]:animate-[dialog-in_180ms_var(--ease-spring)]"
        >
          <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
          <Command loop>
            <Command.Input
              value={input}
              onValueChange={setInput}
              autoFocus
              placeholder="Search inside guides, or jump to anything…"
              className="h-12 w-full border-b border-border bg-transparent px-4 text-[15px] outline-none placeholder:text-fg-subtle"
            />
            <Command.List className="max-h-[min(60vh,420px)] overflow-y-auto p-1.5">
              <Command.Empty className="px-3 py-8 text-center text-sm text-fg-subtle">
                {isFetching ? "Searching guides…" : "No results."}
              </Command.Empty>

              {!!results?.length && input.trim().length >= 3 && (
                <Command.Group heading="Found in guides" className={groupClass}>
                  {results.map((h) => (
                    <Command.Item
                      key={h.chunk_id}
                      value={`${input} ${h.chunk_id}`}
                      onSelect={() =>
                        run(() =>
                          ui.openSource({
                            guideId: h.guide_id,
                            page: h.page,
                            bbox: h.regions.find((r) => r.bbox)?.bbox,
                            regions: h.regions.slice(1),
                            elementIds: h.element_ids,
                            elementId: h.element_ids[0],
                            chunkId: h.chunk_id,
                            label: h.heading_path.at(-1) ?? h.guide_name,
                          }),
                        )
                      }
                      className="flex cursor-pointer items-start gap-2.5 rounded-md px-2.5 py-2 text-sm text-fg-muted data-[selected=true]:bg-surface-sunken data-[selected=true]:text-fg"
                    >
                      <FileSearch className="mt-0.5 size-4 shrink-0 text-fg-subtle" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[12px] text-fg-subtle">
                          {h.guide_name} · {h.heading_path.slice(-2).join(" › ")} · p. {h.page}
                        </span>
                        <span className="line-clamp-2 text-[13px] leading-snug">{h.snippet}</span>
                      </span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}

              {!!guides?.length && (
                <Command.Group heading="Guides" className={groupClass}>
                  {guides.map((g) => (
                    <Item
                      key={g.id}
                      value={`${g.name} ${g.filename} ${g.role}`}
                      icon={g.role === "reference" ? BookMarked : FileCheck2}
                      onSelect={() => run(() => router.push(`/guides/${g.id}`))}
                    >
                      {g.name}
                      <span className="ml-2 text-xs text-fg-subtle">{g.role}</span>
                    </Item>
                  ))}
                </Command.Group>
              )}

              {!!comparisons?.length && (
                <Command.Group heading="Comparisons" className={groupClass}>
                  {comparisons.map((c) => (
                    <Item
                      key={c.id}
                      value={`compare ${c.candidate_name} ${c.reference_name}`}
                      icon={GitCompareArrows}
                      onSelect={() => run(() => router.push(`/comparisons/${c.id}`))}
                    >
                      {c.candidate_name} <span className="text-fg-subtle">vs</span> {c.reference_name}
                    </Item>
                  ))}
                </Command.Group>
              )}

              <Command.Group heading="Actions" className={groupClass}>
                <Item icon={Upload} shortcut="⌘U" onSelect={() => run(() => ui.openUpload("reference"))}>
                  Upload reference guide
                </Item>
                <Item icon={Upload} onSelect={() => run(() => ui.openUpload("candidate"))}>
                  Upload document to check
                </Item>
                <Item icon={GitCompareArrows} onSelect={() => run(() => router.push("/compare"))}>
                  New comparison
                </Item>
                <Item
                  icon={MessageSquareText}
                  shortcut="⌘J"
                  onSelect={() => run(() => (ui.setChatOpen(true), ui.focusChat()))}
                >
                  Ask the guide
                </Item>
                <Item icon={Home} onSelect={() => run(() => router.push("/"))}>
                  Go home
                </Item>
              </Command.Group>

              <Command.Group heading="Theme" className={groupClass}>
                <Item icon={Sun} onSelect={() => run(() => setPref("light"))}>Light theme</Item>
                <Item icon={Moon} onSelect={() => run(() => setPref("dark"))}>Dark theme</Item>
                <Item icon={Laptop} onSelect={() => run(() => setPref("system"))}>System theme</Item>
              </Command.Group>
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
