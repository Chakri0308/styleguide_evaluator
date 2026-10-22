"use client";

import { Link2, Link2Off } from "lucide-react";
import * as React from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { useElements, usePages } from "@/lib/queries";
import type { CitationRefT, Comparison, FindingT } from "@/lib/types";
import { cn } from "@/lib/utils";
import { STATUS_META, type StatusKey } from "./status";

type Side = "reference" | "candidate";

interface Mark {
  finding: FindingT;
  cite: CitationRefT;
}

function useWidth(ref: React.RefObject<HTMLElement | null>) {
  const [w, setW] = React.useState(0);
  React.useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.floor(e!.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

function marksFor(findings: FindingT[], side: Side): Mark[] {
  const out: Mark[] = [];
  for (const f of findings) {
    for (const c of side === "reference" ? f.reference_citations : f.candidate_citations) out.push({ finding: f, cite: c });
  }
  return out;
}

function PagedDoc({
  guideId,
  versionId,
  marks,
  selectedId,
  onSelect,
}: {
  guideId: string;
  versionId: string;
  marks: Mark[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { data: pages } = usePages(guideId, versionId);
  const box = React.useRef<HTMLDivElement>(null);
  const width = useWidth(box);
  return (
    <div ref={box} className="flex flex-col gap-4">
      {!pages || !width
        ? Array.from({ length: 2 }).map((_, i) => <Skeleton key={i} className="aspect-[0.77] w-full" />)
        : pages.map((p) => {
            const scale = width / p.width;
            const here = marks.filter((m) => m.cite.page === p.page && m.cite.bbox);
            return (
              <div
                key={p.page}
                className="relative overflow-hidden rounded-sm bg-white shadow-md ring-1 ring-border"
                style={{ width, height: p.height * scale }}
              >
                {p.image_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={api.assetUrl(p.image_url)} alt={`Page ${p.page}`} loading="lazy" width={width} className="block select-none" draggable={false} />
                )}
                <span className="absolute right-1.5 top-1.5 rounded bg-black/50 px-1 font-mono text-[10px] text-white">{p.page}</span>
                {here.map((m, i) => {
                  const [x0 = 0, y0 = 0, x1 = 0, y1 = 0] = m.cite.bbox!;
                  const active = m.finding.id === selectedId;
                  const color = STATUS_META[m.finding.status as StatusKey]?.color ?? "var(--info)";
                  return (
                    <Tooltip key={`${m.finding.id}-${i}`} content={m.finding.summary}>
                      <button
                        data-active={active || undefined}
                        aria-label={`Finding: ${m.finding.summary}`}
                        onClick={() => onSelect(m.finding.id)}
                        className={cn(
                          "absolute rounded-[3px] transition-all duration-200",
                          active ? "z-10 ring-2" : "opacity-60 hover:opacity-100",
                        )}
                        style={{
                          left: x0 * scale - 3,
                          top: y0 * scale - 3,
                          width: (x1 - x0) * scale + 6,
                          height: (y1 - y0) * scale + 6,
                          background: `color-mix(in oklch, ${color} ${active ? 18 : 9}%, transparent)`,
                          boxShadow: active ? `0 0 0 2px ${color}, 0 0 0 6px color-mix(in oklch, ${color} 22%, transparent)` : `inset 3px 0 0 ${color}`,
                        }}
                      />
                    </Tooltip>
                  );
                })}
              </div>
            );
          })}
    </div>
  );
}

function TextDoc({
  guideId,
  versionId,
  marks,
  selectedId,
  onSelect,
}: {
  guideId: string;
  versionId: string;
  marks: Mark[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { data: elements } = useElements(guideId, true, versionId);
  const byEl = React.useMemo(() => {
    const m = new Map<string, Mark[]>();
    for (const mk of marks) if (mk.cite.element_id) m.set(mk.cite.element_id, [...(m.get(mk.cite.element_id) ?? []), mk]);
    return m;
  }, [marks]);
  if (!elements) return <Skeleton className="h-96 w-full" />;
  return (
    <article className="rounded-md bg-surface p-5 text-[13.5px] leading-relaxed shadow-md ring-1 ring-border">
      {elements
        .filter((e) => e.type !== "swatch" && e.type !== "image")
        .map((e) => {
          const ms = byEl.get(e.id) ?? [];
          const active = ms.some((m) => m.finding.id === selectedId);
          const color = ms[0] ? STATUS_META[ms[0].finding.status as StatusKey]?.color : undefined;
          const Tag = e.type === "heading" ? "h3" : "p";
          return (
            <Tag
              key={e.id}
              data-active={active || undefined}
              onClick={() => ms[0] && onSelect(ms[0].finding.id)}
              className={cn(
                "-mx-2 my-1 rounded px-2 transition-colors",
                e.type === "heading" && "mt-4 font-semibold",
                e.type === "list_item" && "pl-5",
                ms.length > 0 && "cursor-pointer",
                active && "ring-2",
              )}
              style={
                ms.length
                  ? {
                      background: `color-mix(in oklch, ${color} ${active ? 16 : 7}%, transparent)`,
                      boxShadow: active ? `0 0 0 2px ${color}` : `inset 3px 0 0 ${color}`,
                    }
                  : undefined
              }
            >
              {e.type === "list_item" ? `• ${e.text}` : e.text}
            </Tag>
          );
        })}
    </article>
  );
}

export function SideBySide({
  comparison,
  findings,
  selectedId,
  onSelect,
}: {
  comparison: Comparison;
  findings: FindingT[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const refBox = React.useRef<HTMLDivElement>(null);
  const candBox = React.useRef<HTMLDivElement>(null);
  const [sync, setSync] = React.useState(true);
  const suppress = React.useRef(0);

  const onScroll = (from: React.RefObject<HTMLDivElement | null>, to: React.RefObject<HTMLDivElement | null>) => () => {
    if (!sync || Date.now() < suppress.current) return;
    const a = from.current;
    const b = to.current;
    if (!a || !b) return;
    const ratio = a.scrollTop / Math.max(a.scrollHeight - a.clientHeight, 1);
    suppress.current = Date.now() + 60;
    b.scrollTop = ratio * (b.scrollHeight - b.clientHeight);
  };

  // Bring the selected finding's regions into view on both sides
  React.useEffect(() => {
    if (!selectedId) return;
    suppress.current = Date.now() + 900;
    let tries = 0;
    const go = () => {
      let found = 0;
      for (const box of [refBox.current, candBox.current]) {
        const el = box?.querySelector<HTMLElement>("[data-active]");
        if (el && box) {
          found++;
          const top = el.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop;
          box.scrollTo({ top: Math.max(top - box.clientHeight / 3, 0), behavior: "smooth" });
        }
      }
      if (found < 2 && tries++ < 20) setTimeout(go, 120);
    };
    go();
  }, [selectedId]);

  const columns: { side: Side; box: React.RefObject<HTMLDivElement | null>; other: React.RefObject<HTMLDivElement | null> }[] = [
    { side: "reference", box: refBox, other: candBox },
    { side: "candidate", box: candBox, other: refBox },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex h-10 shrink-0 items-center justify-end gap-2 px-4">
        <Tooltip content={sync ? "Scrolling is linked" : "Scrolling independently"}>
          <button
            onClick={() => setSync((s) => !s)}
            aria-pressed={sync}
            className="flex h-7 items-center gap-1.5 rounded-md px-2 text-[12px] text-fg-muted hover:bg-surface-sunken hover:text-fg"
          >
            {sync ? <Link2 className="size-3.5" /> : <Link2Off className="size-3.5" />}
            {sync ? "Synced scroll" : "Free scroll"}
          </button>
        </Tooltip>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-2 gap-px bg-border">
        {columns.map(({ side, box, other }) => {
          const doc = side === "reference" ? comparison.reference : comparison.candidate;
          const paged = ["pdf", "image", "svg"].includes(doc.format);
          const marks = marksFor(findings, side);
          return (
            <div key={side} className="flex min-h-0 flex-col bg-bg-subtle">
              <div className="flex h-9 shrink-0 items-center gap-2 border-b border-border bg-bg px-4 text-[12px]">
                <span className={cn("rounded px-1.5 py-0.5 font-medium", side === "reference" ? "bg-accent-soft text-accent-soft-fg" : "bg-surface-sunken text-fg-muted")}>
                  {side === "reference" ? "Reference" : "Candidate"}
                </span>
                <span className="min-w-0 truncate font-medium">{doc.name}</span>
                <span className="ml-auto text-fg-subtle">{marks.length} marks</span>
              </div>
              <div ref={box} onScroll={onScroll(box, other)} className="min-h-0 flex-1 overflow-y-auto p-5">
                {paged ? (
                  <PagedDoc guideId={doc.id} versionId={doc.version_id} marks={marks} selectedId={selectedId} onSelect={onSelect} />
                ) : (
                  <TextDoc guideId={doc.id} versionId={doc.version_id} marks={marks} selectedId={selectedId} onSelect={onSelect} />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
