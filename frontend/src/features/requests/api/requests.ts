import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/shared/api/client";
import { unwrap } from "@/shared/api/call";

export const requestKeys = { all: ["appointments", "requests"] as const };

export function useRequests() {
  return useQuery({
    queryKey: requestKeys.all,
    queryFn: () => unwrap(api.GET("/api/appointments/requests")),
    refetchInterval: 60_000, // live updates refresh it at once; polling is the fallback
  });
}

type Decision =
  | { kind: "approve"; id: string }
  | { kind: "decline"; id: string; reason: string }
  | { kind: "approve-reschedule"; id: string }
  | { kind: "decline-reschedule"; id: string; reason: string };

export function useDecision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (d: Decision) => {
      const path = { params: { path: { appointment_id: d.id } } };
      switch (d.kind) {
        case "approve":
          return unwrap(api.POST("/api/appointments/{appointment_id}/approve", path));
        case "decline":
          return unwrap(
            api.POST("/api/appointments/{appointment_id}/decline", { ...path, body: { reason: d.reason } }),
          );
        case "approve-reschedule":
          return unwrap(api.POST("/api/appointments/{appointment_id}/reschedule/approve", path));
        case "decline-reschedule":
          return unwrap(
            api.POST("/api/appointments/{appointment_id}/reschedule/decline", {
              ...path,
              body: { reason: d.reason },
            }),
          );
      }
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["appointments"] }),
  });
}
