"use client";

import { ArrowRight, BookMarked, FileCheck2, GitCompareArrows, Loader2, Plus } from "lucide-react";
import { motion } from "motion/react";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCreateComparison } from "@/lib/comparison-queries";
import { useGuides } from "@/lib/queries";
import type { Guide } from "@/lib/types";
import { useUIState } from "@/lib/ui-state";
import { cn, formatBytes, relativeTime } from "@/lib/utils";

function Picker({
  title,
  hint,
  guides,
  value,
  onChange,
  icon: Icon,
  onUpload,
  loading,
}: {
  title: string;
  hint: string;
  guides: Guide[];
  value: string | null;
  onChange: (id: string) => void;
  icon: React.ElementType;
  onUpload: () => void;
  loading: boolean;
}) {
  return (
    <section className="flex min-w-0 flex-col rounded-xl border border-border bg-surface shadow-sm">
      <header className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Icon className="size-4 text-accent" />
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-medium">{title}</h2>
          <p className="text-[12px] text-fg-subtle">{hint}</p>
        </div>
        <Button size="sm" variant="ghost" onClick={onUpload}>
          <Plus /> Upload
        </Button>
      </header>
      <div role="radiogroup" aria-label={title} className="flex max-h-[360px] flex-col gap-1 overflow-y-auto p-2">
        {loading ? (
          <>
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </>
        ) : guides.length === 0 ? (
          <p className="px-3 py-8 text-center text-[13px] text-fg-subtle">Nothing here yet — upload a document.</p>
        ) : (
          guides.map((g) => {
            const ready = g.status === "ready";
            return (
              <button
                key={g.id}
                role="radio"
                aria-checked={value === g.id}
                disabled={!ready}
                onClick={() => onChange(g.id)}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-all",
                  value === g.id ? "bg-accent-soft ring-1 ring-accent" : "hover:bg-surface-sunken",
                  !ready && "opacity-50",
                )}
              >
                <span
                  className={cn(
                    "grid size-4 shrink-0 place-items-center rounded-full ring-1",
                    value === g.id ? "bg-accent ring-accent" : "ring-border-strong",
                  )}
                >
                  {value === g.id && <span className="size-1.5 rounded-full bg-accent-fg" />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13.5px] font-medium">{g.name}</span>
                  <span className="block text-[11.5px] text-fg-subtle">
                    {g.format.toUpperCase()} · {formatBytes(g.size_bytes)} · {relativeTime(g.created_at)}
                  </span>
                </span>
                {!ready && <Loader2 className="size-3.5 animate-spin text-fg-subtle" />}
                {g.role === "reference" && title.startsWith("Document") && <Badge>reference</Badge>}
              </button>
            );
          })
        )}
      </div>
    </section>
  );
}

function ComparePageInner() {
  const router = useRouter();
  const params = useSearchParams();
  const ui = useUIState();
  const { data: guides, isLoading } = useGuides();
  const create = useCreateComparison();
  const refs = (guides ?? []).filter((g) => g.role === "reference");
  const others = (guides ?? []).filter((g) => g.role === "candidate").concat(refs);
  const [ref, setRef] = React.useState<string | null>(params.get("reference"));
  const [cand, setCand] = React.useState<string | null>(params.get("candidate"));
  // This subtree hydrates after the guides query may already have resolved; render lists only once
  // mounted so server and client markup match.
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);

  React.useEffect(() => {
    const lastViewed = refs.find((g) => g.id === ui.chatGuideId && g.status === "ready");
    if (!ref && (lastViewed ?? refs[0])?.status === "ready") setRef((lastViewed ?? refs[0])!.id);
    const firstCand = others.find((g) => g.role === "candidate" && g.status === "ready");
    if (!cand && firstCand) setCand(firstCand.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guides]);

  const canStart = ref && cand && ref !== cand && !create.isPending;
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-6 pb-24 pt-14">
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
          <p className="text-[13px] font-medium text-accent">New comparison</p>
          <h1 className="mt-1.5 font-display text-5xl leading-tight tracking-tight">Check a document against a guide</h1>
          <p className="mt-3 max-w-2xl text-[15px] text-fg-muted">
            StyleLens aligns every rule and passage semantically, runs exact checks on color, contrast and type, and
            returns a cited compliance report.
          </p>
        </motion.div>
        <div className="mt-10 grid items-start gap-4 md:grid-cols-[1fr_auto_1fr]">
          <Picker
            title="Reference guide"
            hint="The source of truth"
            icon={BookMarked}
            guides={refs}
            value={ref}
            onChange={setRef}
            loading={isLoading || !mounted}
            onUpload={() => ui.openUpload("reference")}
          />
          <div className="hidden h-full items-center md:flex">
            <span className="grid size-9 place-items-center rounded-full border border-border bg-surface shadow-sm">
              <GitCompareArrows className="size-4 text-fg-subtle" />
            </span>
          </div>
          <Picker
            title="Document to check"
            hint="A candidate guide, asset or copy"
            icon={FileCheck2}
            guides={others.filter((g) => g.id !== ref)}
            value={cand}
            onChange={setCand}
            loading={isLoading || !mounted}
            onUpload={() => ui.openUpload("candidate")}
          />
        </div>
        <div className="mt-6 flex justify-end">
          <Button
            size="lg"
            variant="primary"
            disabled={!canStart}
            onClick={async () => {
              const c = await create.mutateAsync({ reference_id: ref!, candidate_id: cand! });
              router.push(`/comparisons/${c.id}`);
            }}
          >
            {create.isPending ? <Loader2 className="animate-spin" /> : null}
            Run comparison <ArrowRight />
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function ComparePage() {
  return (
    <React.Suspense>
      <ComparePageInner />
    </React.Suspense>
  );
}
