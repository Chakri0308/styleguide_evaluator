"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowLeftRight, MessageSquareText, Search } from "lucide-react";
import * as React from "react";
import { Button } from "@/components/ui/button";
import type { CitationRefT, Comparison, FindingT } from "@/lib/types";
import { FINDING_STATUSES } from "@/lib/types";
import { cn } from "@/lib/utils";
import { categoryLabel, SeverityPill, STATUS_META, StatusBadge, type StatusKey } from "./status";
import { visualData, VisualEvidence } from "./visual-evidence";

export interface FindingFilters {
  statuses: Set<string>;
  severity: string;
  category: string;
  query: string;
}

export const DEFAULT_FILTERS: FindingFilters = {
  statuses: new Set(["conflict", "deviation", "missing", "new"]),
  severity: "all",
  category: "all",
  query: "",
};

export function applyFilters(findings: FindingT[], f: FindingFilters) {
  const q = f.query.trim().toLowerCase();
  return findings.filter(
    (x) =>
      f.statuses.has(x.status) &&
      (f.severity === "all" || x.severity === f.severity) &&
      (f.category === "all" || x.category === f.category) &&
      (!q || `${x.summary} ${x.reasoning} ${visualData(x)?.rule.statement ?? ""}`.toLowerCase().includes(q)),
  );
}

function CitationBlock({
  label,
  cite,
  onOpen,
}: {
  label: string;
  cite: CitationRefT;
  onOpen: () => void;
}) {
  return (
    <button
      onClick={onOpen}
      className="group block w-full rounded-md border border-border bg-surface px-2.5 py-2 text-left transition-colors hover:border-accent/40 hover:bg-accent-soft/40"
    >
      <span className="flex items-center justify-between text-[10.5px] font-medium uppercase tracking-wider text-fg-subtle">
        {label}
        <span className="font-mono normal-case tracking-normal">p. {cite.page}</span>
      </span>
      <span className="mt-1 line-clamp-3 block text-[12.5px] leading-snug text-fg-muted group-hover:text-fg">“{cite.quote}”</span>
    </button>
  );
}

function FindingRow({
  f,
  selected,
  onSelect,
  onOpenCitation,
  onAsk,
  onShowSideBySide,
}: {
  f: FindingT;
  selected: boolean;
  onSelect: () => void;
  onOpenCitation: (side: "reference" | "candidate", c: CitationRefT) => void;
  onAsk: () => void;
  onShowSideBySide: () => void;
}) {
  const meta = STATUS_META[f.status as StatusKey];
  const visual = visualData(f);
  return (
    <div
      className={cn(
        "mx-2 my-1 rounded-lg border transition-colors",
        selected ? "border-accent/40 bg-surface shadow-sm" : "border-transparent hover:bg-surface-sunken/70",
      )}
    >
      <button onClick={onSelect} aria-expanded={selected} className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left">
        <span className="mt-1.5 size-2 shrink-0 rounded-full" style={{ background: meta?.color }} />
        <span className="min-w-0 flex-1">
          <span className={cn("block text-[13px] leading-snug text-fg", !selected && "line-clamp-2")}>{f.summary}</span>
          <span className="mt-1 flex items-center gap-2 text-[11px] text-fg-subtle">
            {categoryLabel(f.category)}
            <SeverityPill severity={f.severity} />
            {f.method !== "deterministic" && (
              <span className="rounded bg-surface-sunken px-1">{visual ? "vision" : f.method}</span>
            )}
          </span>
        </span>
      </button>
      {selected && (
        <div className="space-y-2.5 px-3 pb-3">
          <div className="flex items-center gap-2">
            <StatusBadge status={f.status} />
            <span className="text-[11px] text-fg-subtle">confidence {(f.confidence * 100).toFixed(0)}%</span>
          </div>
          {visual && <VisualEvidence f={f} onOpenCitation={onOpenCitation} />}
          {f.reasoning && (
            <div>
              {visual && <div className="text-[10.5px] font-medium uppercase tracking-wider text-fg-subtle">Why it’s flagged</div>}
              <p className="text-[12.5px] leading-relaxed text-fg-muted">{f.reasoning}</p>
            </div>
          )}
          {!visual && f.reference_citations.map((c, i) => (
            <CitationBlock key={`r${i}`} label="Reference" cite={c} onOpen={() => onOpenCitation("reference", c)} />
          ))}
          {!visual && f.candidate_citations.map((c, i) => (
            <CitationBlock key={`c${i}`} label="Candidate" cite={c} onOpen={() => onOpenCitation("candidate", c)} />
          ))}
          <div className="flex gap-1.5 pt-0.5">
            <Button size="sm" variant="secondary" onClick={onShowSideBySide}>
              <ArrowLeftRight /> Side by side
            </Button>
            <Button size="sm" variant="ghost" onClick={onAsk}>
              <MessageSquareText /> Ask why
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function FindingsPanel({
  comparison,
  filters,
  setFilters,
  selectedId,
  onSelect,
  onOpenCitation,
  onAsk,
  onShowSideBySide,
}: {
  comparison: Comparison;
  filters: FindingFilters;
  setFilters: (f: FindingFilters) => void;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onOpenCitation: (side: "reference" | "candidate", c: CitationRefT) => void;
  onAsk: (f: FindingT) => void;
  onShowSideBySide: (f: FindingT) => void;
}) {
  const findings = comparison.findings;
  const visible = React.useMemo(() => applyFilters(findings, filters), [findings, filters]);
  const counts = React.useMemo(() => {
    const c: Record<string, number> = {};
    for (const f of findings) c[f.status] = (c[f.status] ?? 0) + 1;
    return c;
  }, [findings]);
  const categories = React.useMemo(() => [...new Set(findings.map((f) => f.category))].sort(), [findings]);
  const parentRef = React.useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: visible.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 76,
    overscan: 8,
    getItemKey: (i) => visible[i]!.id,
  });

  React.useEffect(() => {
    if (!selectedId) return;
    const i = visible.findIndex((f) => f.id === selectedId);
    if (i >= 0) virtualizer.scrollToIndex(i, { align: "auto" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const toggle = (s: string) => {
    const next = new Set(filters.statuses);
    if (next.has(s)) next.delete(s);
    else next.add(s);
    setFilters({ ...filters, statuses: next });
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="space-y-2 border-b border-border p-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-semibold">Findings</h2>
          <span className="text-[12px] text-fg-subtle">
            {visible.length} of {findings.length}
          </span>
        </div>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by status">
          {FINDING_STATUSES.map((s) => {
            const on = filters.statuses.has(s);
            const meta = STATUS_META[s];
            return (
              <button
                key={s}
                onClick={() => toggle(s)}
                aria-pressed={on}
                className={cn(
                  "flex h-6 items-center gap-1.5 rounded-full px-2 text-[11.5px] font-medium transition-colors",
                  on ? "bg-fg text-bg" : "bg-surface-sunken text-fg-subtle hover:text-fg",
                )}
              >
                <span className="size-1.5 rounded-full" style={{ background: meta.color }} />
                {meta.label} <span className="opacity-60">{counts[s] ?? 0}</span>
              </button>
            );
          })}
        </div>
        <div className="flex gap-1.5">
          <label className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-fg-subtle" />
            <input
              value={filters.query}
              onChange={(e) => setFilters({ ...filters, query: e.target.value })}
              placeholder="Search findings"
              aria-label="Search findings"
              className="h-7 w-full rounded-md border border-border bg-surface pl-7 pr-2 text-[12.5px] outline-none focus:border-accent focus:ring-2 focus:ring-ring"
            />
          </label>
          <select
            aria-label="Severity"
            value={filters.severity}
            onChange={(e) => setFilters({ ...filters, severity: e.target.value })}
            className="h-7 rounded-md border border-border bg-surface px-1.5 text-[12px]"
          >
            <option value="all">Any severity</option>
            {["critical", "major", "minor", "info"].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            aria-label="Category"
            value={filters.category}
            onChange={(e) => setFilters({ ...filters, category: e.target.value })}
            className="h-7 max-w-28 rounded-md border border-border bg-surface px-1.5 text-[12px]"
          >
            <option value="all">All areas</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {categoryLabel(c)}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div ref={parentRef} className="min-h-0 flex-1 overflow-y-auto py-1" role="list" aria-label="Findings">
        {visible.length === 0 ? (
          <p className="px-6 py-10 text-center text-[13px] text-fg-subtle">No findings match these filters.</p>
        ) : (
          <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
            {virtualizer.getVirtualItems().map((v) => {
              const f = visible[v.index]!;
              return (
                <div
                  key={v.key}
                  role="listitem"
                  data-index={v.index}
                  ref={virtualizer.measureElement}
                  style={{ position: "absolute", top: 0, left: 0, right: 0, transform: `translateY(${v.start}px)` }}
                >
                  <FindingRow
                    f={f}
                    selected={selectedId === f.id}
                    onSelect={() => onSelect(selectedId === f.id ? null : f.id)}
                    onOpenCitation={onOpenCitation}
                    onAsk={() => onAsk(f)}
                    onShowSideBySide={() => onShowSideBySide(f)}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
