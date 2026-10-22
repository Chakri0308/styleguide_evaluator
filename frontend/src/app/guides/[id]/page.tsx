"use client";

import { MoreHorizontal, RefreshCw, Trash2 } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";
import { IngestionProgress, useIngestionStream } from "@/components/guide/ingestion-progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { useDeleteGuide, useGuide, useReingest } from "@/lib/queries";
import { useUIState } from "@/lib/ui-state";
import { formatBytes } from "@/lib/utils";

export default function GuidePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const ui = useUIState();
  const { data: guide, isLoading, error } = useGuide(id);
  const snapshot = useIngestionStream(guide);
  const reingest = useReingest();
  const del = useDeleteGuide();

  React.useEffect(() => {
    if (guide?.role === "reference") ui.setChatGuideId(guide.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guide?.id, guide?.role]);

  if (error) {
    return (
      <div className="grid h-full place-items-center p-10 text-center">
        <div>
          <p className="font-display text-3xl">Guide not found</p>
          <p className="mt-2 text-sm text-fg-muted">It may have been deleted.</p>
          <Button className="mt-4" onClick={() => router.push("/")}>Go home</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <header className="sticky top-0 z-10 border-b border-border bg-bg/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-6">
          {isLoading || !guide ? (
            <Skeleton className="h-5 w-56" />
          ) : (
            <>
              <h1 className="min-w-0 truncate text-[15px] font-semibold">{guide.name}</h1>
              <Badge tone={guide.role === "reference" ? "accent" : "neutral"}>{guide.role}</Badge>
              <span className="hidden text-xs text-fg-subtle sm:inline">
                {guide.format.toUpperCase()} · {formatBytes(guide.size_bytes)} · v{guide.current_version?.version}
              </span>
              <div className="ml-auto flex items-center gap-1">
                <Tooltip content="Re-ingest as a new index version">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Re-ingest"
                    disabled={guide.status === "processing"}
                    onClick={() => reingest.mutate(guide.id)}
                  >
                    <RefreshCw />
                  </Button>
                </Tooltip>
                <Tooltip content="Delete">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Delete guide"
                    onClick={() => {
                      if (confirm(`Delete "${guide.name}"? This cannot be undone.`)) {
                        del.mutate(guide.id);
                        router.push("/");
                      }
                    }}
                  >
                    <Trash2 />
                  </Button>
                </Tooltip>
                <Button variant="ghost" size="icon-sm" aria-label="More" className="hidden">
                  <MoreHorizontal />
                </Button>
              </div>
            </>
          )}
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-6 py-8">
        {snapshot && snapshot.status !== "ready" && <IngestionProgress snapshot={snapshot} />}
        {guide?.status === "ready" && (
          <p className="text-sm text-fg-muted">Guide profile arrives in milestone 3.</p>
        )}
      </div>
    </div>
  );
}
