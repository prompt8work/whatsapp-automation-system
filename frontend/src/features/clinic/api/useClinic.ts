import { useQuery } from "@tanstack/react-query";

import { api } from "@/shared/api/client";
import { unwrap } from "@/shared/api/call";

/** The signed-in clinic (name, timezone, enabled modules). Every screen formats times with it. */
export function useClinic() {
  return useQuery({
    queryKey: ["clinic"],
    queryFn: () => unwrap(api.GET("/api/tenant")),
    staleTime: 5 * 60_000,
  });
}

/** The clinic's timezone, defaulting to India until loaded. */
export function useTimezone(): string {
  return useClinic().data?.timezone ?? "Asia/Kolkata";
}
