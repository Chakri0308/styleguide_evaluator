"use client";

import { Check, Eye, Search, X } from "lucide-react";
import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { RULE_CATEGORIES, type RuleCategory, type RuleItem, type StyleProfile } from "@/lib/types";
import { cn } from "@/lib/utils";
import { EmptyNote, ProfileSection } from "./section";
import { SourceChip } from "./source-chip";

const LEVEL_TONE = { must: "accent", should: "info", may: "neutral" } as const;

export function NormativeBadge({ level }: { level: "must" | "should" | "may" }) {
  return (
    <Badge tone={LEVEL_TONE[level]} outline={level !== "must"} className="uppercase tracking-[0.06em]">
      {level}
    </Badge>
  );
}

function RuleCard({ rule, guideId }: { rule: RuleItem; guideId: string }) {
  const dont = rule.polarity === "dont";
  return (
    <li
      className="group flex items-start gap-3 rounded-lg border border-transparent px-3 py-2.5 transition-colors hover:border-border hover:bg-surface"
      style={{ contentVisibility: "auto", containIntrinsicSize: "auto 56px" }}
    >
      <span
        className={cn(
          "mt-0.5 grid size-5 shrink-0 place-items-center rounded-full",
          dont ? "bg-bad-soft text-bad" : "bg-ok-soft text-ok",
        )}
        role="img"
        aria-label={dont ? "Don't" : "Do"}
      >
        {dont ? <X className="size-3" strokeWidth={3} /> : <Check className="size-3" strokeWidth={3} />}
      </span>
      <p className="min-w-0 flex-1 text-[14px] leading-snug text-fg">
        {rule.statement}
        {rule.value && (
          <span className="ml-1.5 inline-block rounded bg-surface-sunken px-1.5 py-px align-[1px] font-mono text-[11px] text-fg-muted">
            {rule.value}
          </span>
        )}
      </p>
      <div className="flex shrink-0 items-center gap-1.5">
        {rule.visual && (
          <Tooltip content={rule.check ? `Checked visually: ${rule.check}` : "Learned from a figure in the guide"}>
            <span>
              <Badge tone="info" outline>
                <Eye className="size-3" /> Visual
              </Badge>
            </span>
          </Tooltip>
        )}
        <NormativeBadge level={rule.normative_level} />
        <SourceChip guideId={guideId} refs={rule.source_refs} label={rule.statement.slice(0, 80)} />
      </div>
    </li>
  );
}

export function RulesSection({ profile, guideId }: { profile: StyleProfile; guideId: string }) {
  const [active, setActive] = React.useState<RuleCategory | "all">("all");
  const [level, setLevel] = React.useState<"all" | "must" | "should" | "may">("all");
  const [query, setQuery] = React.useState("");
  const groups = RULE_CATEGORIES.map(([key, label]) => ({ key, label, rules: profile[key] as RuleItem[] })).filter(
    (g) => g.rules.length > 0,
  );
  const total = groups.reduce((n, g) => n + g.rules.length, 0);
  const q = query.trim().toLowerCase();
  const filter = (r: RuleItem) => (level === "all" || r.normative_level === level) && (!q || r.statement.toLowerCase().includes(q));

  return (
    <ProfileSection id="rules" title="Rules" count={total} description="Atomic, checkable rules grouped by area.">
      {total === 0 ? (
        <EmptyNote>No rules were found.</EmptyNote>
      ) : (
        <>
          <div className="sticky top-[104px] z-[5] -mx-2 mb-3 flex flex-wrap items-center gap-2 bg-bg/85 px-2 py-2 backdrop-blur">
            <div role="tablist" aria-label="Rule category" className="flex flex-wrap gap-1">
              {[{ key: "all" as const, label: "All", rules: [] as RuleItem[] }, ...groups].map((g) => {
                const count = g.key === "all" ? total : g.rules.length;
                return (
                  <button
                    key={g.key}
                    role="tab"
                    aria-selected={active === g.key}
                    onClick={() => setActive(g.key)}
                    className={cn(
                      "h-7 rounded-full px-3 text-[12.5px] font-medium transition-colors",
                      active === g.key ? "bg-fg text-bg" : "bg-surface-sunken text-fg-muted hover:text-fg",
                    )}
                  >
                    {g.label} <span className="ml-0.5 opacity-60">{count}</span>
                  </button>
                );
              })}
            </div>
            <div className="ml-auto flex items-center gap-2">
              <select
                aria-label="Normative level"
                value={level}
                onChange={(e) => setLevel(e.target.value as typeof level)}
                className="h-7 rounded-md border border-border bg-surface px-2 text-[12.5px]"
              >
                <option value="all">All levels</option>
                <option value="must">Must</option>
                <option value="should">Should</option>
                <option value="may">May</option>
              </select>
              <label className="relative">
                <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-fg-subtle" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Filter rules"
                  aria-label="Filter rules"
                  className="h-7 w-44 rounded-md border border-border bg-surface pl-7 pr-2 text-[12.5px] outline-none focus:border-accent focus:ring-2 focus:ring-ring"
                />
              </label>
            </div>
          </div>
          <div className="flex flex-col gap-6">
            {groups
              .filter((g) => active === "all" || g.key === active)
              .map((g) => {
                const rules = g.rules.filter(filter);
                if (!rules.length) return null;
                return (
                  <div key={g.key}>
                    <h3 className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-subtle">
                      {g.label}
                    </h3>
                    <ul className="flex flex-col">
                      {rules.map((r) => (
                        <RuleCard key={r.id} rule={r} guideId={guideId} />
                      ))}
                    </ul>
                  </div>
                );
              })}
          </div>
        </>
      )}
    </ProfileSection>
  );
}
