"use client";

import * as HoverCard from "@radix-ui/react-hover-card";
import { AlertTriangle, FileSearch } from "lucide-react";
import type { Citation } from "@/lib/chat";
import { useUIState } from "@/lib/ui-state";
import { cn } from "@/lib/utils";

export function CitationChip({ n, citation }: { n: number; citation?: Citation }) {
  const ui = useUIState();
  const unsupported = citation?.supported === false;
  const open = () => {
    if (!citation) return;
    const first = citation.regions.find((r) => r.bbox) ?? citation.regions[0];
    ui.openSource({
      guideId: citation.guide_id,
      page: first?.page ?? citation.page,
      bbox: first?.bbox,
      regions: citation.regions.filter((r) => r !== first),
      elementId: citation.element_ids[0],
      elementIds: citation.element_ids,
      chunkId: citation.chunk_id,
      label: citation.heading_path.at(-1) ?? citation.guide_name,
      quote: citation.snippet,
    });
  };
  return (
    <HoverCard.Root openDelay={120} closeDelay={80}>
      <HoverCard.Trigger asChild>
        <button
          type="button"
          onClick={open}
          aria-label={`Source ${n}${citation ? `: ${citation.heading_path.at(-1) ?? ""}, page ${citation.page}` : ""}`}
          className={cn(
            "mx-px inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded-[5px] px-1 align-middle font-mono text-[10.5px] font-semibold leading-none transition-colors",
            unsupported
              ? "bg-warn-soft text-warn ring-1 ring-warn/40 hover:bg-warn/20"
              : "bg-accent-soft text-accent-soft-fg hover:bg-accent hover:text-accent-fg",
            !citation && "opacity-60",
          )}
        >
          {n}
        </button>
      </HoverCard.Trigger>
      {citation && (
        <HoverCard.Portal>
          <HoverCard.Content
            side="top"
            align="start"
            sideOffset={6}
            className="z-[60] w-80 rounded-lg border border-border bg-surface-raised p-3 shadow-lg data-[state=open]:animate-[fade-in_120ms_ease-out]"
          >
            <div className="flex items-center gap-2 text-[11px] text-fg-subtle">
              <FileSearch className="size-3.5" />
              <span className="min-w-0 flex-1 truncate">
                {citation.guide_name} · p. {citation.page}
              </span>
              {citation.kind === "image" && <span className="rounded bg-surface-sunken px-1">image</span>}
            </div>
            {citation.heading_path.length > 0 && (
              <p className="mt-1.5 truncate text-[12px] font-medium text-fg">{citation.heading_path.slice(-3).join(" › ")}</p>
            )}
            <p className="mt-1.5 line-clamp-6 whitespace-pre-line text-[12.5px] leading-snug text-fg-muted">{citation.snippet}</p>
            {unsupported && (
              <p className="mt-2 flex items-center gap-1.5 rounded-md bg-warn-soft px-2 py-1 text-[11.5px] text-warn">
                <AlertTriangle className="size-3.5" /> This source may not fully support the claim.
              </p>
            )}
            <button onClick={open} className="mt-2 text-[12px] font-medium text-accent hover:underline">
              Open in source →
            </button>
          </HoverCard.Content>
        </HoverCard.Portal>
      )}
    </HoverCard.Root>
  );
}
