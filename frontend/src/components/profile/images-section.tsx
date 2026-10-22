"use client";

import { Check, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import type { ImageItem } from "@/lib/types";
import { useUIState } from "@/lib/ui-state";
import { EmptyNote, ProfileSection } from "./section";

export function ImagesSection({ images, guideId }: { images: ImageItem[]; guideId: string }) {
  const ui = useUIState();
  return (
    <ProfileSection id="imagery" title="Logo & imagery" count={images.length} description="Every image, described and classified.">
      {images.length === 0 ? (
        <EmptyNote>This document has no raster images.</EmptyNote>
      ) : (
        <div className="grid grid-cols-1 gap-3 @lg:grid-cols-2 @3xl:grid-cols-3">
          {images.map((img) => (
            <article key={img.id} className="group overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
              <button
                className="relative block aspect-[16/10] w-full overflow-hidden bg-[repeating-conic-gradient(var(--surface-sunken)_0_25%,var(--surface)_0_50%)] bg-[length:16px_16px]"
                onClick={() =>
                  ui.openSource({ guideId, page: img.page, bbox: img.bbox, elementId: img.element_id, label: img.caption ?? img.description })
                }
                aria-label={`Show image in context: ${img.caption ?? img.description}`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={api.assetUrl(img.image_url)}
                  alt={img.description}
                  loading="lazy"
                  className="absolute inset-0 size-full object-contain p-3 transition-transform duration-300 group-hover:scale-[1.02]"
                />
                {img.example !== "neutral" && (
                  <span
                    className={
                      "absolute left-2.5 top-2.5 flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold shadow-sm " +
                      (img.example === "dont" ? "bg-bad text-white" : "bg-ok text-white")
                    }
                  >
                    {img.example === "dont" ? <X className="size-3" strokeWidth={3} /> : <Check className="size-3" strokeWidth={3} />}
                    {img.example === "dont" ? "Don't" : "Do"}
                  </span>
                )}
              </button>
              <div className="p-3">
                <div className="flex items-center gap-2">
                  <Badge>{img.kind}</Badge>
                  <span className="text-[11px] text-fg-subtle">p. {img.page}</span>
                  <div className="ml-auto flex -space-x-1">
                    {img.dominant_colors.slice(0, 5).map((c) => (
                      <Tooltip key={c} content={c}>
                        <span className="size-4 rounded-full ring-2 ring-surface" style={{ background: c }} />
                      </Tooltip>
                    ))}
                  </div>
                </div>
                <p className="mt-2 line-clamp-3 text-[13px] leading-snug text-fg-muted">{img.description}</p>
                {img.rules_depicted.length > 0 && (
                  <ul className="mt-2 list-disc pl-4 text-[12px] text-fg-muted">
                    {img.rules_depicted.slice(0, 3).map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </ProfileSection>
  );
}
