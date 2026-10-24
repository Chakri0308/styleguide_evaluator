"use client";

import { Eye, Ruler, ShieldCheck } from "lucide-react";
import { NormativeBadge } from "@/components/profile/rules-section";
import { api } from "@/lib/api";
import type { CitationRefT, FindingT } from "@/lib/types";

export interface VisualData {
  engine: "vision";
  model?: string;
  rule: {
    id: string;
    label: string;
    statement: string;
    value: string | null;
    check: string | null;
    normative_level: "must" | "should" | "may";
    polarity: "do" | "dont";
    from_figure: boolean;
  };
  observation: string;
  measurement: string | null;
  verification: { status: string; measurement: string | null; reasoning: string; confidence: number } | null;
  reference_figure: { page: number; bbox: number[] | null; image_url: string | null } | null;
  candidate_region: { page: number; bbox: number[] | null; image_url: string | null };
}

export function visualData(f: FindingT): VisualData | null {
  const d = f.data as Partial<VisualData> | undefined;
  return d?.engine === "vision" && d.rule ? (d as VisualData) : null;
}

function Figure({
  src,
  caption,
  onOpen,
}: {
  src: string | null | undefined;
  caption: string;
  onOpen?: () => void;
}) {
  if (!src) return null;
  return (
    <button
      onClick={onOpen}
      className="group flex min-w-0 flex-1 flex-col overflow-hidden rounded-md border border-border bg-surface text-left transition-colors hover:border-accent/40"
    >
      <span className="grid aspect-[4/3] place-items-center bg-[repeating-conic-gradient(var(--surface-sunken)_0_25%,transparent_0_50%)] bg-[length:12px_12px]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={api.assetUrl(src)} alt={caption} loading="lazy" className="max-h-full max-w-full object-contain" />
      </span>
      <span className="border-t border-border px-2 py-1 text-[10.5px] font-medium uppercase tracking-wider text-fg-subtle group-hover:text-fg">
        {caption}
      </span>
    </button>
  );
}

/** The "why": the guide's rule, its figure next to the flagged region, what was measured, and the second look. */
export function VisualEvidence({
  f,
  onOpenCitation,
}: {
  f: FindingT;
  onOpenCitation: (side: "reference" | "candidate", c: CitationRefT) => void;
}) {
  const v = visualData(f);
  if (!v) return null;
  const ref = f.reference_citations[0];
  const cand = f.candidate_citations[0];
  return (
    <div className="space-y-2.5">
      <div className="rounded-md border border-border bg-surface px-2.5 py-2">
        <div className="flex items-center gap-1.5 text-[10.5px] font-medium uppercase tracking-wider text-fg-subtle">
          <Eye className="size-3" /> Guide rule{v.reference_figure ? ` · p. ${v.reference_figure.page}` : ref ? ` · p. ${ref.page}` : ""}
          <span className="ml-auto normal-case tracking-normal">
            <NormativeBadge level={v.rule.normative_level} />
          </span>
        </div>
        <p className="mt-1 text-[13px] leading-snug text-fg">
          {v.rule.polarity === "dont" && <span className="font-semibold text-bad">Don’t: </span>}
          {v.rule.statement}
          {v.rule.value && (
            <span className="ml-1.5 inline-block rounded bg-surface-sunken px-1.5 py-px align-[1px] font-mono text-[11px] text-fg-muted">
              {v.rule.value}
            </span>
          )}
        </p>
        {v.rule.check && <p className="mt-1 text-[11.5px] leading-snug text-fg-subtle">How it’s checked: {v.rule.check}</p>}
      </div>

      <div className="flex gap-2">
        <Figure
          src={v.reference_figure?.image_url}
          caption={`Guide figure · p. ${v.reference_figure?.page ?? ""}`}
          onOpen={ref ? () => onOpenCitation("reference", ref) : undefined}
        />
        <Figure
          src={v.candidate_region.image_url}
          caption={`${f.status === "compliant" ? "Checked" : "Flagged"} · p. ${v.candidate_region.page}`}
          onOpen={cand ? () => onOpenCitation("candidate", cand) : undefined}
        />
      </div>

      <dl className="space-y-1.5 text-[12.5px] leading-snug">
        <div>
          <dt className="text-[10.5px] font-medium uppercase tracking-wider text-fg-subtle">What we saw</dt>
          <dd className="text-fg-muted">{v.observation}</dd>
        </div>
        {v.measurement && (
          <div className="flex items-start gap-1.5 rounded-md bg-surface-sunken px-2 py-1.5 font-mono text-[11.5px] text-fg">
            <Ruler className="mt-px size-3.5 shrink-0 text-fg-subtle" />
            {v.measurement}
          </div>
        )}
        {v.verification && (
          <div className="flex items-start gap-1.5 text-[12px] text-fg-muted">
            <ShieldCheck className="mt-px size-3.5 shrink-0 text-ok" />
            <span>
              Confirmed by an independent second look ({Math.round(v.verification.confidence * 100)}%)
              {v.verification.measurement ? `: ${v.verification.measurement}` : ""}
            </span>
          </div>
        )}
      </dl>
    </div>
  );
}
