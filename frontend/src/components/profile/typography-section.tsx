"use client";

import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { useSpecimenFont, weightNumber } from "@/lib/fonts";
import type { FontUsage, TypographyItem } from "@/lib/types";
import { EmptyNote, ProfileSection } from "./section";
import { SourceChip } from "./source-chip";

const ROLE_ORDER = ["display", "primary", "headline", "title", "h1", "h2", "h3", "h4", "h5", "h6", "heading", "subhead", "body", "secondary", "label", "button", "caption", "code"];
const SAMPLE: Record<string, string> = {
  body: "Good coffee is a small, daily ritual. We roast in small batches and tell you exactly where every bean comes from.",
  caption: "Caption — Roasted on March 4, 2025 · Portland, Oregon",
};

function px(size?: string | null): number | undefined {
  if (!size) return undefined;
  const m = size.match(/([\d.]+)\s*(px|pt|rem|em)?/i);
  if (!m) return undefined;
  const v = Number(m[1]);
  const unit = (m[2] ?? "px").toLowerCase();
  return unit === "pt" ? v * 1.333 : unit === "rem" || unit === "em" ? v * 16 : v;
}

function Specimen({ item, guideId }: { item: TypographyItem; guideId: string }) {
  const state = useSpecimenFont(item.family);
  const size = px(item.size);
  const isBody = ["body", "caption", "label", "secondary", "code", "button"].includes(item.role);
  const displaySize = size ? Math.min(Math.max(size, 13), 56) : isBody ? 16 : 36;
  const stack = [item.family, ...(item.fallbacks ?? [])].map((f) => `"${f}"`).join(", ");
  return (
    <article className="grid gap-4 border-b border-border py-5 last:border-0 md:grid-cols-[160px_1fr]">
      <div className="flex flex-col gap-1.5">
        <span className="font-mono text-[11px] uppercase tracking-wider text-fg-subtle">{item.role}</span>
        <span className="text-sm font-medium">{item.family}</span>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[12px] text-fg-muted">
          {item.weight && <span>{item.weight}</span>}
          {item.size && (
            <span className="font-mono">
              {item.size}
              {item.line_height ? ` / ${item.line_height}` : ""}
            </span>
          )}
          {item.letter_spacing && <span className="font-mono">ls {item.letter_spacing}</span>}
          {item.case && <span>{item.case}</span>}
        </div>
        {item.fallbacks.length > 0 && (
          <span className="text-[11px] text-fg-subtle">Fallback: {item.fallbacks.join(", ")}</span>
        )}
        <div className="mt-1 flex items-center gap-1.5">
          <SourceChip guideId={guideId} refs={item.source_refs} label={`${item.role}: ${item.value}`} />
          {state === "fallback" && (
            <Tooltip content={`${item.family} isn't available in this browser; showing the fallback stack.`}>
              <span>
                <Badge tone="warn">fallback</Badge>
              </span>
            </Tooltip>
          )}
        </div>
      </div>
      <p
        className="min-w-0 break-words text-fg transition-opacity duration-300"
        style={{
          fontFamily: `${stack}, var(--font-sans)`,
          fontWeight: weightNumber(item.weight),
          fontSize: displaySize,
          lineHeight: item.line_height && px(item.line_height) && size ? `${(px(item.line_height)! / size).toFixed(2)}` : isBody ? 1.5 : 1.15,
          letterSpacing: item.letter_spacing?.endsWith("%") ? `${parseFloat(item.letter_spacing) / 100}em` : undefined,
          textTransform: item.case === "uppercase" ? "uppercase" : undefined,
          opacity: state === "loading" ? 0.35 : 1,
        }}
      >
        {SAMPLE[item.role] ?? (isBody ? SAMPLE.body : "Every brand rule, in focus")}
      </p>
    </article>
  );
}

export function TypographySection({
  items,
  fonts,
  guideId,
}: {
  items: TypographyItem[];
  fonts: FontUsage[];
  guideId: string;
}) {
  const rank = (role: string) => (ROLE_ORDER.includes(role) ? ROLE_ORDER.indexOf(role) : ROLE_ORDER.length);
  const sorted = [...items].sort((a, b) => rank(a.role) - rank(b.role) || a.id.localeCompare(b.id));
  return (
    <ProfileSection
      id="typography"
      title="Typography"
      count={items.length}
      description="Live specimens rendered in the guide's typefaces where they're available."
    >
      {items.length === 0 ? (
        <EmptyNote>No type styles were specified in this document.</EmptyNote>
      ) : (
        <div className="rounded-xl border border-border bg-surface px-5 shadow-sm">
          {sorted.map((it) => (
            <Specimen key={it.id} item={it} guideId={guideId} />
          ))}
        </div>
      )}
      {fonts.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-2 text-[12px] font-medium text-fg-muted">Fonts used in the file itself</h3>
          <div className="flex flex-wrap gap-1.5">
            {fonts.slice(0, 12).map((f) => (
              <Tooltip key={f.family} content={`Sizes: ${f.sizes.slice(0, 8).join(", ")}pt${f.embedded ? " · embedded" : ""}`}>
                <span className="rounded-md bg-surface-sunken px-2 py-1 text-[12px] text-fg-muted">
                  {f.family}
                  <span className="ml-1.5 font-mono text-[10.5px] text-fg-subtle">{f.chars.toLocaleString()}</span>
                </span>
              </Tooltip>
            ))}
          </div>
        </div>
      )}
    </ProfileSection>
  );
}
