"use client";

import { ChevronLeft, ChevronRight, ExternalLink, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import dynamic from "next/dynamic";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { useElements, useGuide, usePages } from "@/lib/queries";
import { useUIState, type SourceTarget } from "@/lib/ui-state";
import { cn } from "@/lib/utils";
import { HighlightBox } from "./highlight-box";

const PdfPage = dynamic(() => import("./pdf-page"), { ssr: false });

const PANEL_WIDTH = 560;

function useHighlightScroll(dep: unknown) {
  const ref = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    let tries = 0;
    const tick = () => {
      const el = ref.current?.querySelector("[data-highlight]");
      if (el) {
        el.scrollIntoView({ block: "center", behavior: "smooth" });
      } else if (tries++ < 30) {
        setTimeout(tick, 100);
      }
    };
    tick();
  }, [dep]);
  return ref;
}

function PagedView({ target, format, page }: { target: SourceTarget; format: string; page: number }) {
  const { data: pages } = usePages(target.guideId);
  const info = pages?.find((p) => p.page === page);
  const width = PANEL_WIDTH - 48;
  const highlights = [
    ...(target.page === page && target.bbox ? [{ bbox: target.bbox, strong: true }] : []),
    ...(target.regions ?? []).filter((r) => r.page === page && r.bbox).map((r) => ({ bbox: r.bbox!, strong: false })),
  ];

  if (format === "pdf") {
    return <PdfPage url={api.fileUrl(target.guideId)} page={page} width={width} highlights={highlights} />;
  }
  if (!info) return <Skeleton style={{ width, height: width * 1.29 }} />;
  const scale = width / info.width;
  return (
    <div className="relative" style={{ width }}>
      {info.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={api.assetUrl(info.image_url)} alt={`Page ${page}`} width={width} className="block rounded-sm" />
      ) : (
        <div className="grid place-items-center bg-surface-sunken text-sm text-fg-subtle" style={{ width, height: info.height * scale }}>
          No preview
        </div>
      )}
      {highlights.map((h, i) => (
        <HighlightBox key={i} bbox={h.bbox} scale={scale} strong={h.strong} />
      ))}
    </div>
  );
}

function TextView({ target }: { target: SourceTarget }) {
  const { data: elements, isLoading } = useElements(target.guideId);
  if (isLoading || !elements) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-4" style={{ width: `${60 + ((i * 17) % 40)}%` }} />
        ))}
      </div>
    );
  }
  const highlighted = new Set([target.elementId, ...(target.elementIds ?? [])].filter(Boolean));
  return (
    <article className="max-w-none text-[14px] leading-relaxed text-fg">
      {elements
        .filter((e) => e.type !== "swatch" && e.type !== "image")
        .map((e) => {
          const hit = highlighted.has(e.id);
          const cls = cn(
            "rounded px-1 -mx-1 transition-colors",
            hit && "bg-highlight-strong ring-2 ring-warn/50",
          );
          const props = hit ? { "data-highlight": true } : {};
          if (e.type === "heading")
            return (
              <h3 key={e.id} {...props} className={cn(cls, "mt-5 font-semibold", (e.level ?? 2) <= 1 ? "text-lg" : "text-[15px]")}>
                {e.text}
              </h3>
            );
          if (e.type === "list_item")
            return (
              <p key={e.id} {...props} className={cn(cls, "my-1 pl-4 before:-ml-3 before:mr-1.5 before:content-['•']")}>
                {e.text}
              </p>
            );
          if (e.type === "table" || e.type === "code")
            return (
              <pre key={e.id} {...props} className={cn(cls, "my-2 overflow-x-auto rounded-md bg-surface-sunken p-2 font-mono text-[12px]")}>
                {e.text}
              </pre>
            );
          return (
            <p key={e.id} {...props} className={cn(cls, "my-2")}>
              {e.text}
            </p>
          );
        })}
    </article>
  );
}

export function SourceViewer() {
  const ui = useUIState();
  const target = ui.sourceTarget;
  const { data: guide } = useGuide(target?.guideId ?? "");
  const { data: pages } = usePages(target?.guideId);
  const [page, setPage] = React.useState(1);
  React.useEffect(() => {
    if (target) setPage(target.page || 1);
  }, [target]);
  const scrollRef = useHighlightScroll(`${target?.elementId}-${target?.page}-${page}-${target?.chunkId}`);

  React.useEffect(() => {
    if (!target) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") ui.openSource(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [target, ui]);

  const format = guide?.format ?? "";
  const paged = ["pdf", "image", "svg"].includes(format);
  const pageCount = pages?.length ?? 1;

  return (
    <AnimatePresence>
      {target && (
        <motion.aside
          key="source"
          role="complementary"
          aria-label="Source viewer"
          initial={{ x: 40, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 40, opacity: 0 }}
          transition={{ type: "spring", stiffness: 420, damping: 38 }}
          className="fixed inset-y-0 right-0 z-30 flex w-[min(560px,100vw)] flex-col border-l border-border bg-surface-raised shadow-lg"
        >
          <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-4">
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium">{target.label || guide?.name || "Source"}</p>
              <p className="truncate text-[11px] text-fg-subtle">
                {guide?.name}
                {paged ? ` · Page ${page} of ${pageCount}` : ""}
              </p>
            </div>
            {paged && (
              <div className="flex items-center">
                <Button variant="ghost" size="icon-sm" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                  <ChevronLeft />
                </Button>
                <Button variant="ghost" size="icon-sm" aria-label="Next page" disabled={page >= pageCount} onClick={() => setPage((p) => p + 1)}>
                  <ChevronRight />
                </Button>
              </div>
            )}
            <Tooltip content="Open original file">
              <Button variant="ghost" size="icon-sm" asChild>
                <a href={api.fileUrl(target.guideId)} target="_blank" rel="noreferrer" aria-label="Open original file">
                  <ExternalLink />
                </a>
              </Button>
            </Tooltip>
            <Tooltip content="Close (Esc)">
              <Button variant="ghost" size="icon-sm" aria-label="Close source viewer" onClick={() => ui.openSource(null)}>
                <X />
              </Button>
            </Tooltip>
          </header>
          {target.quote && (
            <blockquote className="mx-4 mt-3 border-l-2 border-warn/70 bg-warn-soft/40 py-1.5 pl-3 pr-2 text-[12.5px] leading-snug text-fg-muted">
              {target.quote}
            </blockquote>
          )}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
            {!guide ? (
              <Skeleton className="h-[600px] w-full" />
            ) : paged ? (
              <div className="overflow-hidden rounded-md shadow-md ring-1 ring-border">
                <PagedView target={target} format={format} page={page} />
              </div>
            ) : (
              <TextView target={target} />
            )}
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
