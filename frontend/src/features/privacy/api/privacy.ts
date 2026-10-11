import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/shared/api/client";
import { unwrap } from "@/shared/api/call";

export const privacyKeys = {
  all: ["privacy"] as const,
  requests: ["privacy", "requests"] as const,
  upcoming: ["privacy", "upcoming"] as const,
  records: ["privacy", "records"] as const,
};

/** Patients' "delete my data" requests (PRD AP-10.10). Needs case.manage. */
export function useDeletionRequests(enabled = true) {
  return useQuery({
    queryKey: privacyKeys.requests,
    queryFn: () => unwrap(api.GET("/api/deletion-requests")),
    refetchInterval: 60_000,
    enabled,
  });
}

type Decision = { kind: "approve"; id: string } | { kind: "reject"; id: string; reason: string };

export function useDeletionDecision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (d: Decision) => {
      const path = { params: { path: { request_id: d.id } } };
      return d.kind === "approve"
        ? unwrap(api.POST("/api/deletion-requests/{request_id}/approve", path))
        : unwrap(api.POST("/api/deletion-requests/{request_id}/reject", { ...path, body: { reason: d.reason } }));
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: privacyKeys.all });
      void queryClient.invalidateQueries({ queryKey: ["appointments"] });
    },
  });
}

/** What retention will delete in the next 7 days (AP-10.6). */
export function useUpcomingDeletions() {
  return useQuery({ queryKey: privacyKeys.upcoming, queryFn: () => unwrap(api.GET("/api/retention/upcoming")) });
}

/** Proof of what was deleted - counts only, no personal data (AP-10.5). */
export function useDeletionRecords() {
  return useQuery({ queryKey: privacyKeys.records, queryFn: () => unwrap(api.GET("/api/retention/records")) });
}
