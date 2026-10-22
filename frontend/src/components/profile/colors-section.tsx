"use client";

import { Ban, Copy } from "lucide-react";
import { motion } from "motion/react";
import * as React from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { contrast, onColor, rgbString, wcag } from "@/lib/color";
import type { ColorItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { EmptyNote, ProfileSection } from "./section";
import { SourceChip } from "./source-chip";

async function copy(value: string, what: string) {
  try {
    await navigator.clipboard.writeText(value);
    toast.success(`Copied ${what}`, { description: value, duration: 1600 });
  } catch {
    toast.error("Clipboard unavailable");
  }
}

function SpecRow({ label, value }: { label: string; value: string }) {
  return (
    <button
      onClick={() => copy(value, label)}
      className="group/spec flex w-full items-center justify-between gap-2 rounded px-1.5 py-0.5 -mx-1.5 text-left transition-colors hover:bg-surface-sunken"
      aria-label={`Copy ${label} ${value}`}
    >
      <span className="w-14 shrink-0 text-[10.5px] font-medium uppercase tracking-wider text-fg-subtle">{label}</span>
      <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-fg">{value}</span>
      <Copy className="size-3 shrink-0 text-fg-subtle opacity-0 transition-opacity group-hover/spec:opacity-100" />
    </button>
  );
}

function Swatch({ c, guideId, index }: { c: ColorItem; guideId: string; index: number }) {
  const fg = onColor(c.hex);
  const prohibited = c.status === "prohibited";
  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.03, 0.3) }}
      className="group overflow-hidden rounded-xl border border-border bg-surface shadow-sm transition-shadow hover:shadow-md"
    >
      <button
        onClick={() => copy(c.hex, "HEX")}
        className="relative block h-28 w-full text-left transition-[filter] hover:brightness-[1.03]"
        style={{ background: c.hex, color: fg }}
        aria-label={`${c.name ?? c.hex}: copy ${c.hex}`}
      >
        {prohibited && (
          <span
            aria-hidden
            className="absolute inset-0"
            style={{ background: `repeating-linear-gradient(135deg, transparent 0 10px, ${fg}22 10px 12px)` }}
          />
        )}
        <span className="absolute bottom-2.5 left-3 font-mono text-[12px] opacity-80">{c.hex}</span>
        <span className="absolute right-2.5 top-2.5 flex gap-1">
          {c.role && (
            <span className="rounded-full px-2 py-0.5 text-[10.5px] font-medium backdrop-blur" style={{ background: `${fg}1f` }}>
              {c.role}
            </span>
          )}
        </span>
      </button>
      <div className="p-3">
        <div className="flex items-center gap-2">
          <h3 className="min-w-0 flex-1 truncate text-sm font-medium">{c.name ?? "Unnamed color"}</h3>
          {prohibited ? (
            <Badge tone="bad">
              <Ban className="size-3" /> Prohibited
            </Badge>
          ) : (
            <Badge tone={c.normative_level === "must" ? "accent" : "neutral"}>{c.normative_level}</Badge>
          )}
        </div>
        <div className="mt-2 flex flex-col">
          <SpecRow label="HEX" value={c.hex} />
          <SpecRow label="RGB" value={c.rgb ?? rgbString(c.hex)} />
          {c.cmyk && <SpecRow label="CMYK" value={c.cmyk} />}
          {c.pantone && <SpecRow label="Pantone" value={c.pantone} />}
          {c.hsl && <SpecRow label="HSL" value={c.hsl} />}
        </div>
        {c.usage.length > 0 && (
          <p className="mt-2 line-clamp-2 text-[12px] leading-snug text-fg-muted" title={c.usage.join("\n")}>
            {c.usage.find((u) => !u.startsWith("HEX") && !u.startsWith("|") && u !== c.name) ?? ""}
          </p>
        )}
        <div className="mt-2.5 flex items-center justify-between">
          <span className="text-[10.5px] text-fg-subtle">{(c.origin ?? []).join(" · ")}</span>
          <SourceChip guideId={guideId} refs={c.source_refs} label={c.name ?? c.hex} />
        </div>
      </div>
    </motion.article>
  );
}

function ContrastPairs({ colors }: { colors: ColorItem[] }) {
  const approved = colors.filter((c) => c.status === "approved");
  const pairs = React.useMemo(() => {
    const out: { fg: ColorItem; bg: ColorItem; ratio: number }[] = [];
    for (const fg of approved)
      for (const bg of approved) if (fg.hex !== bg.hex) out.push({ fg, bg, ratio: contrast(fg.hex, bg.hex) });
    // one direction per pair, best-first
    const seen = new Set<string>();
    return out
      .sort((a, b) => b.ratio - a.ratio || a.fg.hex.localeCompare(b.fg.hex))
      .filter((p) => {
        const k = [p.fg.hex, p.bg.hex].sort().join();
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      });
  }, [approved]);
  const [showAll, setShowAll] = React.useState(false);
  if (pairs.length === 0) return null;
  const visible = showAll ? pairs : pairs.slice(0, 8);
  return (
    <div className="mt-8">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-medium">Contrast pairs</h3>
        <span className="text-[12px] text-fg-subtle">WCAG 2.2 · normal text needs 4.5:1</span>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {visible.map(({ fg, bg, ratio }) => {
          const level = wcag(ratio);
          return (
            <Tooltip key={`${fg.hex}${bg.hex}`} content={`${fg.name ?? fg.hex} on ${bg.name ?? bg.hex}`}>
              <div className="overflow-hidden rounded-lg border border-border">
                <div className="flex h-16 items-center justify-center text-xl font-semibold" style={{ background: bg.hex, color: fg.hex }}>
                  Aa
                </div>
                <div className="flex items-center justify-between bg-surface px-2.5 py-1.5">
                  <span className="font-mono text-[12px] tabular-nums">{ratio.toFixed(2)}:1</span>
                  <Badge tone={level === "Fail" ? "bad" : level === "AA Large" ? "warn" : "ok"}>{level}</Badge>
                </div>
              </div>
            </Tooltip>
          );
        })}
      </div>
      {pairs.length > 8 && (
        <button onClick={() => setShowAll((s) => !s)} className="mt-2 text-[12px] font-medium text-accent hover:underline">
          {showAll ? "Show fewer" : `Show all ${pairs.length} pairs`}
        </button>
      )}
    </div>
  );
}

export function ColorsSection({ colors, guideId }: { colors: ColorItem[]; guideId: string }) {
  const approved = colors.filter((c) => c.status !== "prohibited");
  const prohibited = colors.filter((c) => c.status === "prohibited");
  return (
    <ProfileSection
      id="colors"
      title="Color"
      count={approved.length}
      description="Click any value to copy it. Swatches link to where the guide defines them."
    >
      {colors.length === 0 ? (
        <EmptyNote>No colors were found in this document.</EmptyNote>
      ) : (
        <>
          <div className={cn("grid gap-3", "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4")}>
            {approved.map((c, i) => (
              <Swatch key={c.id} c={c} guideId={guideId} index={i} />
            ))}
          </div>
          {prohibited.length > 0 && (
            <div className="mt-6">
              <h3 className="mb-3 text-sm font-medium">Prohibited</h3>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {prohibited.map((c, i) => (
                  <Swatch key={c.id} c={c} guideId={guideId} index={i} />
                ))}
              </div>
            </div>
          )}
          <ContrastPairs colors={colors} />
        </>
      )}
    </ProfileSection>
  );
}
