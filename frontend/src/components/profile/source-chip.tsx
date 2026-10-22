"use client";

import { FileSearch } from "lucide-react";
import { Tooltip } from "@/components/ui/tooltip";
import type { SourceRef } from "@/lib/types";
import { useUIState } from "@/lib/ui-state";
import { cn } from "@/lib/utils";

/** Small "p. 4" button that opens the source viewer on the cited region. */
export function SourceChip({
  guideId,
  refs,
  label,
  className,
}: {
  guideId: string;
  refs: SourceRef[];
  label?: string;
  className?: string;
}) {
  const ui = useUIState();
  const first = refs[0];
  if (!first) return null;
  const pages = [...new Set(refs.map((r) => r.page))].sort((a, b) => a - b);
  const text = pages.length > 2 ? `p. ${pages[0]}–${pages.at(-1)}` : `p. ${pages.join(", ")}`;
  return (
    <Tooltip content={first.quote ? `“${first.quote.slice(0, 140)}${first.quote.length > 140 ? "…" : ""}”` : "View source"}>
      <button
        onClick={(e) => {
          e.stopPropagation();
          ui.openSource({
            guideId,
            page: first.page,
            bbox: first.bbox,
            elementId: first.element_id,
            elementIds: refs.map((r) => r.element_id),
            regions: refs.slice(1).map((r) => ({ page: r.page, bbox: r.bbox })),
            label,
            quote: first.quote,
          });
        }}
        className={cn(
          "inline-flex h-5 shrink-0 items-center gap-1 rounded-md px-1.5 font-mono text-[10.5px] text-fg-subtle ring-1 ring-border transition-colors",
          "hover:bg-accent-soft hover:text-accent-soft-fg hover:ring-accent/30",
          className,
        )}
        aria-label={`View source on ${text}`}
      >
        <FileSearch className="size-3" />
        {text}
      </button>
    </Tooltip>
  );
}
