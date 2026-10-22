"use client";

import { ArrowRight, Download, FileJson, MessageSquareText, Trash2 } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";
import { DEFAULT_FILTERS, FindingsPanel, applyFilters, type FindingFilters } from "@/components/compare/findings-panel";
import { SideBySide } from "@/components/compare/side-by-side";
import { categoryLabel, ScoreRing, SeverityPill, STATUS_META, StatusBadge } from "@/components/compare/status";
import { StageProgress } from "@/components/guide/ingestion-progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip } from "@/components/ui/tooltip";
import { API_BASE } from "@/lib/api";
import { useChat } from "@/lib/chat";
import { useComparison, useComparisonStream, useDeleteComparison } from "@/lib/comparison-queries";
import { COMPARE_STAGES, FINDING_STATUSES, type CitationRefT, type Comparison, type FindingT } from "@/lib/types";
import { useUIState } from "@/lib/ui-state";
import { cn } from "@/lib/utils";

const STAGE_LABELS = {
  aligning: "Aligning",
  deterministic_checks: "Exact checks",
  judging: "Judging",
  scoring: "Scoring",
};

interface CategorySummary {
  score: number;
  counts: Record<string, number>;
  total: number;
}

function Report({
  c,
  onSelect,
  onCategory,
}: {
  c: Comparison;
  onSelect: (f: FindingT) => void;
  onCategory: (cat: string) => void;
}) {
  const summary = c.summary as {
    categories?: Record<string, CategorySummary>;
    by_status?: Record<string, number>;
    by_severity?: Record<string, number>;
    mode?: string;
    candidate_kind?: string;
  };
  const issues = c.findings.filter((f) => f.status !== "compliant");
  const top = issues.filter((f) => f.severity === "critical" || f.severity === "major").slice(0, 6);
  const cats = Object.entries(summary.categories ?? {}).sort((a, b) => a[1].score - b[1].score);
  return (
    <div className="@container mx-auto max-w-4xl space-y-10 px-6 py-8">
      <section className="flex flex-col items-start gap-8 @2xl:flex-row @2xl:items-center">
        <ScoreRing score={c.score ?? 0} />
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-[34px] leading-tight tracking-tight">
            {issues.length === 0 ? "Fully compliant" : `${issues.length} finding${issues.length === 1 ? "" : "s"} need attention`}
          </h2>
          <p className="mt-1.5 text-[14px] text-fg-muted">
            {c.candidate.name} checked against {c.reference.name}
            {summary.candidate_kind ? ` · treated as ${summary.candidate_kind === "asset" ? "an asset" : "a style guide"}` : ""}
            {summary.mode === "offline" ? " · offline judgment (no LLM)" : ""}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {FINDING_STATUSES.map((s) =>
              summary.by_status?.[s] ? (
                <span key={s} className="flex items-center gap-1.5 rounded-full bg-surface px-2.5 py-1 text-[12.5px] shadow-sm ring-1 ring-border">
                  <span className="size-2 rounded-full" style={{ background: STATUS_META[s].color }} />
                  <span className="font-medium tabular-nums">{summary.by_status[s]}</span>
                  <span className="text-fg-subtle">{STATUS_META[s].label.toLowerCase()}</span>
                </span>
              ) : null,
            )}
          </div>
        </div>
      </section>

      {cats.length > 0 && (
        <section aria-labelledby="by-cat">
          <h3 id="by-cat" className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-subtle">
            By area
          </h3>
          <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
            {cats.map(([cat, d], i) => (
              <button
                key={cat}
                onClick={() => onCategory(cat)}
                className="grid w-full grid-cols-[140px_1fr_48px] items-center gap-4 px-4 py-3 text-left transition-colors hover:bg-bg-subtle"
              >
                <span className="text-[13.5px] font-medium">{categoryLabel(cat)}</span>
                <span className="flex h-2 overflow-hidden rounded-full bg-surface-sunken">
                  <motion.span
                    className="h-full rounded-full"
                    style={{ background: d.score >= 85 ? "var(--ok)" : d.score >= 60 ? "var(--warn)" : "var(--bad)" }}
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.max(d.score, 2)}%` }}
                    transition={{ delay: 0.05 * i, duration: 0.6, ease: [0.32, 0.72, 0, 1] }}
                  />
                </span>
                <span className="text-right font-mono text-[13px] tabular-nums">{Math.round(d.score)}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {top.length > 0 && (
        <section aria-labelledby="top">
          <h3 id="top" className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-subtle">
            Most important
          </h3>
          <div className="grid gap-2 @2xl:grid-cols-2">
            {top.map((f) => (
              <button
                key={f.id}
                onClick={() => onSelect(f)}
                className="group flex flex-col gap-2 rounded-xl border border-border bg-surface p-4 text-left shadow-sm transition-all hover:-translate-y-px hover:shadow-md"
              >
                <span className="flex items-center gap-2">
                  <StatusBadge status={f.status} />
                  <SeverityPill severity={f.severity} />
                  <span className="ml-auto text-[11px] text-fg-subtle">{categoryLabel(f.category)}</span>
                </span>
                <span className="text-[13.5px] leading-snug">{f.summary}</span>
                <span className="mt-auto flex items-center gap-1 text-[12px] font-medium text-accent opacity-0 transition-opacity group-hover:opacity-100">
                  Show in documents <ArrowRight className="size-3.5" />
                </span>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export default function ComparisonPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const ui = useUIState();
  const chat = useChat();
  const { data: c, isLoading, error, refetch } = useComparison(id);
  const snapshot = useComparisonStream(c);
  const del = useDeleteComparison();
  const [tab, setTab] = React.useState("report");
  const [selected, setSelected] = React.useState<string | null>(null);
  const [filters, setFilters] = React.useState<FindingFilters>(DEFAULT_FILTERS);

  React.useEffect(() => {
    if (snapshot?.status === "ready" && c?.status !== "ready") void refetch();
  }, [snapshot?.status, c?.status, refetch]);

  React.useEffect(() => {
    if (!c) return;
    ui.setChatComparisonId(c.id);
    ui.setChatGuideId(c.reference.id);
    return () => ui.setChatComparisonId(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [c?.id]);

  if (error) {
    return (
      <div className="grid h-full place-items-center text-center">
        <div>
          <p className="font-display text-3xl">Comparison not found</p>
          <Button className="mt-4" onClick={() => router.push("/compare")}>
            New comparison
          </Button>
        </div>
      </div>
    );
  }

  const ready = c?.status === "ready";
  const visible = c ? applyFilters(c.findings, filters) : [];
  const openCitation = (side: "reference" | "candidate", cite: CitationRefT) => {
    if (!c) return;
    ui.openSource({
      guideId: side === "reference" ? c.reference.id : c.candidate.id,
      page: cite.page,
      bbox: cite.bbox,
      elementId: cite.element_id ?? undefined,
      chunkId: cite.chunk_id,
      label: side === "reference" ? `Reference · ${c.reference.name}` : `Candidate · ${c.candidate.name}`,
      quote: cite.quote,
    });
  };
  const ask = (f: FindingT) => {
    if (!c) return;
    ui.setChatOpen(true);
    void chat.send(c.reference.id, `Why was this flagged: “${f.summary}”?`, c.id);
  };

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border px-5">
          {isLoading || !c ? (
            <Skeleton className="h-5 w-72" />
          ) : (
            <>
              <h1 className="flex min-w-0 items-center gap-2 text-[15px] font-semibold">
                <Link href={`/guides/${c.candidate.id}`} className="truncate hover:underline">
                  {c.candidate.name}
                </Link>
                <span className="font-normal text-fg-subtle">vs</span>
                <Link href={`/guides/${c.reference.id}`} className="truncate hover:underline">
                  {c.reference.name}
                </Link>
              </h1>
              {ready && c.score != null && <Badge tone={c.score >= 85 ? "ok" : c.score >= 60 ? "warn" : "bad"}>{Math.round(c.score)} / 100</Badge>}
              <div className="ml-auto flex items-center gap-1">
                {ready && (
                  <>
                    <Tooltip content="Ask about this comparison">
                      <Button variant="ghost" size="icon-sm" aria-label="Ask about this comparison" onClick={() => (ui.setChatOpen(true), ui.focusChat())}>
                        <MessageSquareText />
                      </Button>
                    </Tooltip>
                    <Button variant="secondary" size="sm" asChild>
                      <a href={`${API_BASE}/comparisons/${c.id}/export?format=pdf`}>
                        <Download /> PDF
                      </a>
                    </Button>
                    <Button variant="ghost" size="sm" asChild>
                      <a href={`${API_BASE}/comparisons/${c.id}/export?format=json`}>
                        <FileJson /> JSON
                      </a>
                    </Button>
                  </>
                )}
                <Tooltip content="Delete comparison">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Delete comparison"
                    onClick={() => {
                      if (confirm("Delete this comparison?")) {
                        del.mutate(c.id);
                        router.push("/compare");
                      }
                    }}
                  >
                    <Trash2 />
                  </Button>
                </Tooltip>
              </div>
            </>
          )}
        </header>

        {!c || !ready ? (
          <div className="mx-auto w-full max-w-3xl px-6 py-10">
            {snapshot ? (
              <StageProgress snapshot={snapshot} stages={COMPARE_STAGES} labels={STAGE_LABELS} title="Comparing documents" />
            ) : (
              <Skeleton className="h-40" />
            )}
          </div>
        ) : (
          <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col">
            <div className="flex h-11 shrink-0 items-center border-b border-border px-5">
              <TabsList>
                <TabsTrigger value="report">Report</TabsTrigger>
                <TabsTrigger value="side">Side by side</TabsTrigger>
              </TabsList>
            </div>
            <TabsContent value="report" className="min-h-0 flex-1 overflow-y-auto">
              <Report
                c={c}
                onSelect={(f) => {
                  setSelected(f.id);
                  setTab("side");
                }}
                onCategory={(cat) => setFilters({ ...filters, category: cat, statuses: new Set(FINDING_STATUSES) })}
              />
            </TabsContent>
            <TabsContent value="side" className="min-h-0 flex-1">
              <SideBySide comparison={c} findings={visible} selectedId={selected} onSelect={setSelected} />
            </TabsContent>
          </Tabs>
        )}
      </div>

      {c && ready && (
        <aside aria-label="Findings" className={cn("hidden w-[380px] shrink-0 border-l border-border bg-bg-subtle lg:block")}>
          <FindingsPanel
            comparison={c}
            filters={filters}
            setFilters={setFilters}
            selectedId={selected}
            onSelect={setSelected}
            onOpenCitation={openCitation}
            onAsk={ask}
            onShowSideBySide={(f) => {
              setSelected(f.id);
              setTab("side");
            }}
          />
        </aside>
      )}
    </div>
  );
}

