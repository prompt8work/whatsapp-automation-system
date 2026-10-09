/**
 * api/: the ONLY place in a feature that talks to the backend.
 * Each hook wraps one endpoint with TanStack Query; components never call fetch.
 */
import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "@/shared/api/client";

import type { Health } from "../model/health";

export const healthKeys = {
  readiness: ["system", "health", "readiness"] as const,
};

export function useHealthQuery() {
  return useQuery({
    queryKey: healthKeys.readiness,
    queryFn: async (): Promise<Health> => {
      const { data, error, response } = await api.GET("/api/health/ready");
      if (data) return data;
      // 503 still carries a HealthResponse body ("unavailable") - that is data, not a failure.
      if (response.status === 503 && error) return error;
      throw new ApiError(response.status, "health.unexpected", "Health check failed");
    },
    refetchInterval: 10_000, // ADR-007: "live" = polling for v1
  });
}
