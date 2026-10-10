import type { Schemas } from "@/shared/api/types";

export type Appointment = Schemas["AppointmentResponse"];

/** A new booking request, or a patient asking to move a confirmed appointment (AP-3.1). */
export function requestKind(a: Appointment): "new" | "reschedule" {
  return a.pending_slot ? "reschedule" : "new";
}

/** Oldest first: whoever has waited longest is handled first. */
export function sortQueue(items: Appointment[]): Appointment[] {
  return [...items].sort((x, y) => x.created_at.localeCompare(y.created_at));
}
