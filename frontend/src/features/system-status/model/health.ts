/**
 * model/: types and PURE functions for this feature. No React, no fetching - easy to unit test.
 */
import type { components } from "@/shared/api/schema";
import type { Tone } from "@/shared/ui/StatusDot";

export type Health = components["schemas"]["HealthResponse"];

export function describeHealth(health: Health | undefined): { label: string; tone: Tone } {
  if (!health) return { label: "Checking…", tone: "unknown" };
  return health.status === "ok"
    ? { label: "All systems operational", tone: "good" }
    : { label: "Database unreachable", tone: "bad" };
}
