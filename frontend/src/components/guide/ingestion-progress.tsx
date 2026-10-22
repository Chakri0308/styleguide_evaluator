"use client";

import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Loader2 } from "lucide-react";
import { motion } from "motion/react";
import * as React from "react";
import { toast } from "sonner";
import { API_BASE } from "@/lib/api";
import { keys } from "@/lib/queries";
import { INGEST_STAGES, type Guide, type Stage } from "@/lib/types";
import { cn } from "@/lib/utils";

const LABELS: Record<string, string> = {
  parsing: "Parsing",
  extracting: "Extracting",
  chunking: "Chunking",
  embedding: "Embedding",
  indexing: "Indexing",
};

export interface Snapshot {
  status: string;
  stages: Record<string, Pick<Stage, "status" | "progress" | "message">>;
  error?: string | null;
}

/** Subscribes to the ingestion SSE stream and returns the latest stage snapshot. */
export function useIngestionStream(guide: Guide | undefined) {
  const qc = useQueryClient();
  const [snap, setSnap] = React.useState<Snapshot | null>(null);
  const active = guide?.status === "processing" || guide?.status === "uploaded";
  const versionId = guide?.current_version_id;

  React.useEffect(() => {
    if (!guide || !active) return;
    const es = new EventSource(`${API_BASE}/guides/${guide.id}/events`);
    const handle = (e: MessageEvent) => {
      const data = JSON.parse(e.data) as Snapshot;
      setSnap(data);
      if (data.status === "ready" || data.status === "failed") {
        es.close();
        qc.invalidateQueries({ queryKey: keys.guides });
        qc.invalidateQueries({ queryKey: keys.guide(guide.id) });
        if (data.status === "ready") toast.success(`${guide.name} is ready`, { description: "Profile and index built." });
        else toast.error(`Ingestion failed for ${guide.name}`, { description: data.error ?? undefined });
      }
    };
    es.addEventListener("snapshot", handle);
    es.addEventListener("progress", handle);
    es.onerror = () => {
      // Fall back to a refetch; EventSource reconnects automatically.
      qc.invalidateQueries({ queryKey: keys.guide(guide.id) });
    };
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guide?.id, versionId, active]);

  return snap ?? (guide?.current_version ? { status: guide.current_version.status, stages: guide.current_version.stages, error: guide.current_version.error } : null);
}

export function IngestionProgress({ snapshot }: { snapshot: Snapshot }) {
  return <StageProgress snapshot={snapshot} stages={INGEST_STAGES} labels={LABELS} title="Analyzing document" />;
}

export function StageProgress({
  snapshot,
  stages,
  labels,
  title,
}: {
  snapshot: Snapshot;
  stages: readonly string[];
  labels: Record<string, string>;
  title: string;
}) {
  const overall = stages.reduce((acc, s) => acc + (snapshot.stages[s]?.progress ?? 0), 0) / stages.length;

  return (
    <div className="rounded-xl border border-border bg-surface p-5 shadow-sm" aria-live="polite">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-medium">
          {snapshot.status === "failed" ? "Something went wrong" : title}
        </h2>
        <span className="font-mono text-xs tabular-nums text-fg-subtle">{Math.round(overall * 100)}%</span>
      </div>
      <div className="mt-3 h-1 overflow-hidden rounded-full bg-surface-sunken">
        <motion.div
          className={cn("h-full rounded-full", snapshot.status === "failed" ? "bg-bad" : "bg-accent")}
          initial={false}
          animate={{ width: `${Math.max(overall * 100, 2)}%` }}
        />
      </div>
      <ol className="mt-5 grid gap-2" style={{ gridTemplateColumns: `repeat(${stages.length}, minmax(0, 1fr))` }}>
        {stages.map((name) => {
          const st = snapshot.stages[name] ?? { status: "pending", progress: 0, message: "" };
          return (
            <li key={name} className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span
                  className={cn(
                    "grid size-5 shrink-0 place-items-center rounded-full ring-1 transition-colors duration-300",
                    st.status === "done" && "bg-accent text-accent-fg ring-accent",
                    st.status === "running" && "bg-accent-soft text-accent ring-accent/40",
                    st.status === "failed" && "bg-bad-soft text-bad ring-bad/40",
                    (st.status === "pending" || st.status === "skipped") && "bg-surface-sunken text-fg-subtle ring-border",
                  )}
                >
                  {st.status === "done" ? (
                    <Check className="size-3" strokeWidth={3} />
                  ) : st.status === "running" ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : st.status === "failed" ? (
                    <AlertTriangle className="size-3" />
                  ) : (
                    <span className="size-1 rounded-full bg-current" />
                  )}
                </span>
                <span className={cn("truncate text-[13px]", st.status === "pending" ? "text-fg-subtle" : "text-fg")}>
                  {labels[name] ?? name}
                </span>
              </div>
              <p className="mt-1 line-clamp-2 min-h-8 pl-[26px] text-[11px] leading-4 text-fg-subtle">
                {st.message || (st.status === "running" ? `${Math.round(st.progress * 100)}%` : "")}
              </p>
            </li>
          );
        })}
      </ol>
      {snapshot.error && (
        <p className="mt-3 rounded-md bg-bad-soft px-3 py-2 font-mono text-xs text-bad">{snapshot.error}</p>
      )}
    </div>
  );
}
