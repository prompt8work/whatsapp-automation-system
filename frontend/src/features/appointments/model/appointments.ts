import type { Schemas } from "@/shared/api/types";
import type { BadgeTone } from "@/shared/ui/Badge";

export type Appointment = Schemas["AppointmentResponse"];
export type AppointmentDetail = Schemas["AppointmentDetailResponse"];
export type HistoryEntry = Schemas["HistoryEntryResponse"];
export type Doctor = Schemas["DoctorResponse"];

export const STATUSES: Record<string, { label: string; tone: BadgeTone }> = {
  requested: { label: "Requested", tone: "info" },
  confirmed: { label: "Confirmed", tone: "good" },
  rescheduled: { label: "Rescheduled", tone: "good" },
  declined: { label: "Declined", tone: "bad" },
  expired: { label: "Expired", tone: "neutral" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  completed: { label: "Completed", tone: "good" },
  no_show: { label: "No-show", tone: "bad" },
};

export function statusOf(status: string): { label: string; tone: BadgeTone } {
  return STATUSES[status] ?? { label: status, tone: "neutral" };
}

const ACTIVE = new Set(["requested", "confirmed", "rescheduled"]);
const BOOKED = new Set(["confirmed", "rescheduled"]);

/** Which actions the detail page offers (the backend re-checks every rule). */
export function actionsFor(a: Appointment, now: Date = new Date()) {
  const started = new Date(a.slot.start) <= now;
  return {
    reschedule: ACTIVE.has(a.status),
    cancel: ACTIVE.has(a.status),
    attendance: BOOKED.has(a.status) && started,
  };
}

const EVENT_LABELS: Record<string, string> = {
  AppointmentRequested: "Requested",
  AppointmentConfirmed: "Confirmed",
  AppointmentDeclined: "Declined",
  AppointmentExpired: "Expired (no answer in time)",
  AppointmentCancelled: "Cancelled",
  RescheduleRequested: "Reschedule requested",
  AppointmentRescheduled: "Rescheduled",
  RescheduleDeclined: "Reschedule declined",
  AppointmentCompleted: "Completed",
  AppointmentNoShow: "No-show",
  AppointmentDetailsUpdated: "Details updated",
};

export function eventLabel(entry: HistoryEntry): string {
  const label = EVENT_LABELS[entry.event_type] ?? entry.event_type;
  return entry.event_type === "AppointmentConfirmed" && entry.data.automatic ? `${label} automatically` : label;
}

/** "Staff", "Patient (WhatsApp)", "System". */
export function actorLabel(entry: HistoryEntry): string {
  const who = entry.actor.startsWith("staff")
    ? "Staff"
    : entry.actor.startsWith("contact")
      ? "Patient"
      : "System";
  return entry.channel === "whatsapp" ? `${who} (WhatsApp)` : who;
}
