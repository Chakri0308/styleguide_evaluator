"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";
import { API_BASE, ApiError } from "./api";
import type { Comparison, ComparisonListItem } from "./types";

export type { ComparisonListItem };

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      msg = (await res.json()).detail ?? msg;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, msg);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export function useComparisons() {
  return useQuery({
    queryKey: ["comparisons"],
    queryFn: () => req<ComparisonListItem[]>("/comparisons"),
    refetchInterval: (q) => (q.state.data?.some((c) => c.status !== "ready" && c.status !== "failed") ? 3000 : false),
  });
}

export function useComparison(id: string) {
  return useQuery({ queryKey: ["comparisons", id], queryFn: () => req<Comparison>(`/comparisons/${id}`) });
}

export function useCreateComparison() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { reference_id: string; candidate_id: string }) =>
      req<Comparison>("/comparisons", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    onSuccess: (c) => {
      qc.setQueryData(["comparisons", c.id], c);
      qc.invalidateQueries({ queryKey: ["comparisons"] });
    },
    onError: (err) => toast.error("Couldn't start the comparison", { description: String((err as Error).message) }),
  });
}

export function useDeleteComparison() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => req<void>(`/comparisons/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["comparisons"] }),
  });
}

interface Snapshot {
  status: string;
  stages: Record<string, { status: string; progress: number; message: string }>;
  error?: string | null;
}

/** Live comparison progress over SSE; refetches the full comparison when it finishes. */
export function useComparisonStream(c: Comparison | undefined) {
  const qc = useQueryClient();
  const [snap, setSnap] = React.useState<Snapshot | null>(null);
  const active = !!c && c.status !== "ready" && c.status !== "failed";
  React.useEffect(() => {
    if (!c || !active) return;
    const es = new EventSource(`${API_BASE}/comparisons/${c.id}/events`);
    const handle = (e: MessageEvent) => {
      const d = JSON.parse(e.data) as Snapshot;
      setSnap(d);
      if (d.status === "ready" || d.status === "failed") {
        es.close();
        qc.invalidateQueries({ queryKey: ["comparisons"] });
        if (d.status === "ready") toast.success("Comparison ready");
        else toast.error("Comparison failed", { description: d.error ?? undefined });
      }
    };
    es.addEventListener("snapshot", handle);
    es.addEventListener("progress", handle);
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [c?.id, active]);
  return snap ?? (c ? { status: c.status, stages: c.stages as Snapshot["stages"], error: c.error } : null);
}
