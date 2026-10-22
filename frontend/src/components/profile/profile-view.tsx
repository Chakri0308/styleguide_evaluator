"use client";

import { AlertTriangle, Sparkles } from "lucide-react";
import * as React from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import type { StyleProfile } from "@/lib/types";
import { ColorsSection } from "./colors-section";
import { ImagesSection } from "./images-section";
import { RulesSection } from "./rules-section";
import { TypographySection } from "./typography-section";

export const PROFILE_SECTIONS = [
  ["colors", "Color"],
  ["typography", "Typography"],
  ["rules", "Rules"],
  ["imagery", "Logo & imagery"],
] as const;

export function ProfileSkeleton() {
  return (
    <div className="flex flex-col gap-10">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-60 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-64 rounded-xl" />
      <div className="flex flex-col gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-9" />
        ))}
      </div>
    </div>
  );
}

export function ProfileView({ profile, guideId }: { profile: StyleProfile; guideId: string }) {
  const s = profile.stats;
  return (
    <div className="@container flex flex-col gap-14">
      <div className="flex flex-col gap-3">
        {profile.title && <h2 className="font-display text-4xl leading-tight tracking-tight text-balance">{profile.title}</h2>}
        {profile.summary && <p className="max-w-3xl text-[15px] leading-relaxed text-fg-muted">{profile.summary}</p>}
        <dl className="mt-1 flex flex-wrap gap-x-6 gap-y-2 text-[13px]">
          {(
            [
              ["Pages", s.pages],
              ["Colors", s.colors],
              ["Rules", s.rules],
              ["Images", s.images],
            ] as const
          ).map(([k, v]) => (
            <div key={k} className="flex items-baseline gap-1.5">
              <dt className="text-fg-subtle">{k}</dt>
              <dd className="font-mono tabular-nums text-fg">{v}</dd>
            </div>
          ))}
          <div className="flex items-center gap-1.5 text-fg-subtle">
            <Sparkles className="size-3.5" />
            {s.llm_used ? `Extracted with ${s.extraction_model?.split(":")[1] ?? "LLM"}` : "Heuristic extraction"}
          </div>
          {s.warnings.length > 0 && (
            <Tooltip content={<ul className="list-disc pl-3">{s.warnings.slice(0, 6).map((w) => <li key={w}>{w}</li>)}</ul>}>
              <span className="flex items-center gap-1.5 text-warn">
                <AlertTriangle className="size-3.5" />
                {s.warnings.length} note{s.warnings.length === 1 ? "" : "s"}
              </span>
            </Tooltip>
          )}
        </dl>
      </div>
      <ColorsSection colors={profile.colors} guideId={guideId} />
      <TypographySection items={profile.typography} fonts={profile.fonts_detected} guideId={guideId} />
      <RulesSection profile={profile} guideId={guideId} />
      <ImagesSection images={profile.images} guideId={guideId} />
    </div>
  );
}

/** Highlights the section currently in view. */
export function useScrollSpy(ids: readonly string[], root: React.RefObject<HTMLElement | null>) {
  const [active, setActive] = React.useState<string>(ids[0] ?? "");
  React.useEffect(() => {
    const el = root.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { root: el, rootMargin: "-120px 0px -60% 0px" },
    );
    ids.forEach((id) => {
      const s = document.getElementById(id);
      if (s) obs.observe(s);
    });
    return () => obs.disconnect();
  });
  return active;
}
