"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, profileApi } from "./api";
import type { Guide } from "./types";

export const keys = {
  guides: ["guides"] as const,
  guide: (id: string) => ["guides", id] as const,
};

const isActive = (g: Guide) => g.status === "processing" || g.status === "uploaded";

export function useGuides() {
  return useQuery({
    queryKey: keys.guides,
    queryFn: () => api.listGuides(),
    // Light polling while anything is ingesting so the library badges stay current.
    refetchInterval: (q) => (q.state.data?.some(isActive) ? 2500 : false),
  });
}

export function useGuide(id: string) {
  return useQuery({
    queryKey: keys.guide(id),
    queryFn: () => api.getGuide(id),
  });
}

export function useUploadGuide() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, role, name }: { file: File; role: "reference" | "candidate"; name?: string }) =>
      api.uploadGuide(file, role, name),
    onSuccess: (guide) => {
      qc.setQueryData<Guide[]>(keys.guides, (old) => [guide, ...(old ?? [])]);
      qc.setQueryData(keys.guide(guide.id), guide);
    },
  });
}

export function useDeleteGuide() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteGuide(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: keys.guides });
      const prev = qc.getQueryData<Guide[]>(keys.guides);
      qc.setQueryData<Guide[]>(keys.guides, (old) => old?.filter((g) => g.id !== id));
      return { prev };
    },
    onError: (err, _id, ctx) => {
      qc.setQueryData(keys.guides, ctx?.prev);
      toast.error("Couldn't delete guide", { description: String(err) });
    },
    onSettled: () => qc.invalidateQueries({ queryKey: keys.guides }),
  });
}

export function useReingest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.reingest(id),
    onSuccess: (guide) => {
      qc.setQueryData(keys.guide(guide.id), guide);
      qc.invalidateQueries({ queryKey: keys.guides });
      toast.success("Re-ingestion started", { description: `Building index version ${guide.current_version?.version}` });
    },
  });
}

export function useProfile(id: string, enabled: boolean) {
  return useQuery({
    queryKey: [...keys.guide(id), "profile"],
    queryFn: () => profileApi.profile(id),
    enabled,
    staleTime: 60_000,
  });
}

export function usePages(id: string | undefined) {
  return useQuery({
    queryKey: ["guides", id, "pages"],
    queryFn: () => profileApi.pages(id!),
    enabled: !!id,
    staleTime: 60_000,
  });
}

export function useElements(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["guides", id, "elements"],
    queryFn: () => profileApi.elements(id!),
    enabled: !!id && enabled,
    staleTime: 60_000,
  });
}
