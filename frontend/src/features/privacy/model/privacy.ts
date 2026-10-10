import type { Schemas } from "@/shared/api/types";

export type DeletionRequest = Schemas["DeletionRequestResponse"];
export type UpcomingDeletion = Schemas["UpcomingDeletionResponse"];
export type DeletionRecord = Schemas["DeletionRecordResponse"];

/** Plain-language names of the retention rules (PRD §7.10). Periods are clinic settings, so
 * the labels don't name them. */
const RULES: Record<string, string> = {
  "RT-1": "Closed case",
  "RT-2": "Inactive open case",
  "RT-4": "Unused WhatsApp contact",
  "AP-10.11": "Patient's request",
};

export function ruleLabel(rule: string): string {
  return RULES[rule] ?? rule;
}

/** {"appointments": 3, "cases": 1} -> "3 appointments, 1 case" (zero counts left out). */
export function describeCounts(counts: Record<string, number>): string {
  return Object.entries(counts)
    .filter(([, n]) => n > 0)
    .map(([what, n]) => {
      const label = what.replaceAll("_", " ");
      return `${n} ${n === 1 ? label.replace(/s$/, "") : label}`;
    })
    .join(", ");
}

/** Pending first (oldest first - the 7-day answer deadline), then decided (newest first). */
export function sortRequests(items: DeletionRequest[]): DeletionRequest[] {
  const pending = items.filter((r) => r.status === "pending").sort((a, b) => a.requested_at.localeCompare(b.requested_at));
  const decided = items.filter((r) => r.status !== "pending").sort((a, b) => b.requested_at.localeCompare(a.requested_at));
  return [...pending, ...decided];
}

export function patientNames(r: DeletionRequest): string {
  return r.patients.map((p) => p.name ?? "(deleted)").join(", ");
}
