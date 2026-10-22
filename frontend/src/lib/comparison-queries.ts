"use client";

import { useQuery } from "@tanstack/react-query";
import { API_BASE } from "./api";

export interface ComparisonListItem {
  id: string;
  status: string;
  score: number | null;
  reference_name: string;
  candidate_name: string;
  created_at: string;
}

export function useComparisons() {
  return useQuery({
    queryKey: ["comparisons"],
    queryFn: async (): Promise<ComparisonListItem[]> => {
      const res = await fetch(`${API_BASE}/comparisons`);
      if (!res.ok) return [];
      return res.json();
    },
  });
}
