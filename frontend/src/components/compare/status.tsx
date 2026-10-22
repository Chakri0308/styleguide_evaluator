"use client";

import { AlertOctagon, CheckCircle2, CircleDashed, CircleSlash, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import { Badge } from "@/components/ui/badge";
import { FINDING_CATEGORIES } from "@/lib/types";
import { cn } from "@/lib/utils";

export const STATUS_META = {
  conflict: { label: "Conflict", tone: "bad", icon: AlertOctagon, color: "var(--bad)" },
  deviation: { label: "Deviation", tone: "warn", icon: CircleSlash, color: "var(--warn)" },
  missing: { label: "Missing", tone: "new", icon: CircleDashed, color: "var(--new)" },
  new: { label: "New", tone: "info", icon: Sparkles, color: "var(--info)" },
  compliant: { label: "Compliant", tone: "ok", icon: CheckCircle2, color: "var(--ok)" },
} as const;

export type StatusKey = keyof typeof STATUS_META;

export function StatusBadge({ status }: { status: string }) {
  const m = STATUS_META[status as StatusKey] ?? STATUS_META.new;
  const Icon = m.icon;
  return (
    <Badge tone={m.tone}>
      <Icon className="size-3" />
      {m.label}
    </Badge>
  );
}

const SEV_CLASS: Record<string, string> = {
  critical: "bg-bad",
  major: "bg-warn",
  minor: "bg-info",
  info: "bg-border-strong",
};

export function SeverityPill({ severity }: { severity: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-medium capitalize text-fg-muted">
      <span className={cn("size-1.5 rounded-full", SEV_CLASS[severity] ?? "bg-border-strong")} />
      {severity}
    </span>
  );
}

export function categoryLabel(c: string) {
  return FINDING_CATEGORIES[c] ?? c;
}

export function ScoreRing({ score, size = 132 }: { score: number; size?: number }) {
  const r = (size - 14) / 2;
  const circ = 2 * Math.PI * r;
  const tone = score >= 85 ? "var(--ok)" : score >= 60 ? "var(--warn)" : "var(--bad)";
  return (
    <div className="relative" style={{ width: size, height: size }} role="img" aria-label={`Compliance score ${Math.round(score)} out of 100`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-sunken)" strokeWidth={10} />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={tone}
          strokeWidth={10}
          strokeLinecap="round"
          strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: circ * (1 - score / 100) }}
          transition={{ duration: 0.9, ease: [0.32, 0.72, 0, 1] }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className="font-display text-[42px] leading-none tabular-nums">{Math.round(score)}</div>
          <div className="mt-1 text-[11px] uppercase tracking-[0.08em] text-fg-subtle">of 100</div>
        </div>
      </div>
    </div>
  );
}
