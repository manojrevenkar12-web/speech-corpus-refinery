import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";

export const useOverview = () => useQuery({ queryKey: ["overview"], queryFn: api.overview });
export const useSources = () => useQuery({ queryKey: ["sources"], queryFn: api.sources });
export const useItems = (p: { state?: string; reason?: string; source?: string; offset?: number }) =>
  useQuery({ queryKey: ["items", p], queryFn: () => api.items({ ...p, limit: 50 }) });
export const useItem = (id: number | null) => useQuery({ queryKey: ["item", id], queryFn: () => api.item(id ?? 0), enabled: id !== null });
export const useSpectrogram = (id: number | null, width: number) =>
  useQuery({ queryKey: ["spectrogram", id, width], queryFn: () => api.spectrogram(id ?? 0, width), enabled: id !== null });
export const useQueue = (kind: "held" | "kept" | "rejected") => useQuery({ queryKey: ["queue", kind], queryFn: () => api.queue(kind) });
export const useReviewSummary = () => useQuery({ queryKey: ["reviewSummary"], queryFn: api.reviewSummary });
export const useReleases = () => useQuery({ queryKey: ["releases"], queryFn: api.releases });
export const useTakedowns = () => useQuery({ queryKey: ["takedowns"], queryFn: api.takedowns });

export function useReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.review,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["reviewSummary"] });
      void qc.invalidateQueries({ queryKey: ["item"] });
    },
  });
}

export function useResolve() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision, note }: { id: number; decision: "keep" | "reject"; note?: string }) => api.resolve(id, decision, note),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["queue"] });
      void qc.invalidateQueries({ queryKey: ["overview"] });
      void qc.invalidateQueries({ queryKey: ["item"] });
    },
  });
}

export function useExecuteTakedown() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.executeTakedown,
    onSuccess: () => {
      void qc.invalidateQueries();
    },
  });
}
