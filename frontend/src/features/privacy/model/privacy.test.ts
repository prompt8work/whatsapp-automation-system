import { describe, expect, it } from "vitest";

import { describeCounts, patientNames, ruleLabel, sortRequests, type DeletionRequest } from "./privacy";

function request(over: Partial<DeletionRequest>): DeletionRequest {
  return {
    id: "r",
    contact_id: "c",
    patients: [{ id: "p", name: "Rahul Verma" }],
    status: "pending",
    requested_at: "2026-10-01T10:00:00Z",
    answer_by: "2026-10-08T10:00:00Z",
    decided_at: null,
    rejection_reason: "",
    deleted_counts: {},
    ...over,
  };
}

describe("privacy model", () => {
  it("describes counts in words, singular and plural, without zeros", () => {
    expect(describeCounts({ cases: 1, appointments: 3, history_events: 0, patients: 1 })).toBe(
      "1 case, 3 appointments, 1 patient",
    );
  });

  it("names the rules in plain language", () => {
    expect(ruleLabel("RT-1")).toBe("Closed case");
    expect(ruleLabel("XYZ")).toBe("XYZ");
  });

  it("puts pending requests first, oldest first", () => {
    const sorted = sortRequests([
      request({ id: "done", status: "completed", requested_at: "2026-10-05T00:00:00Z" }),
      request({ id: "new", requested_at: "2026-10-03T00:00:00Z" }),
      request({ id: "old", requested_at: "2026-10-01T00:00:00Z" }),
    ]);
    expect(sorted.map((r) => r.id)).toEqual(["old", "new", "done"]);
  });

  it("shows deleted patients without a name", () => {
    expect(patientNames(request({ patients: [{ id: "p", name: null }] }))).toBe("(deleted)");
  });
});
