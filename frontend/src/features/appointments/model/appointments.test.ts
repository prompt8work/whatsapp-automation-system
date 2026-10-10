import { actionsFor, actorLabel, eventLabel, statusOf, type Appointment, type HistoryEntry } from "./appointments";

const slot = (start: string) => ({ doctor_id: "d", start, end: start });
const base: Appointment = {
  id: "a",
  reference: "APT-7K3Q",
  status: "confirmed",
  case_id: "c",
  patient_id: "p",
  patient_name: "Rahul",
  doctor_name: "Dr. Amit",
  location_id: "l",
  slot: slot("2026-10-12T09:30:00Z"),
  original_slot: slot("2026-10-12T09:30:00Z"),
  was_rescheduled: false,
  pending_slot: null,
  reason: "Fever",
  fields: {},
  created_at: "2026-10-10T09:00:00Z",
};

describe("appointments model", () => {
  it("offers attendance only once a booked appointment has started", () => {
    expect(actionsFor(base, new Date("2026-10-12T09:00:00Z"))).toEqual({ reschedule: true, cancel: true, attendance: false });
    expect(actionsFor(base, new Date("2026-10-12T09:45:00Z")).attendance).toBe(true);
    expect(actionsFor({ ...base, status: "cancelled" }, new Date("2026-10-12T09:45:00Z"))).toEqual({
      reschedule: false,
      cancel: false,
      attendance: false,
    });
  });

  it("labels statuses and history entries for humans", () => {
    expect(statusOf("no_show")).toEqual({ label: "No-show", tone: "bad" });
    const entry: HistoryEntry = {
      event_type: "AppointmentConfirmed",
      occurred_at: "2026-10-10T09:00:00Z",
      actor: "system",
      channel: "whatsapp",
      data: { automatic: true },
    };
    expect(eventLabel(entry)).toBe("Confirmed automatically");
    expect(actorLabel({ ...entry, actor: "contact:x" })).toBe("Patient (WhatsApp)");
    expect(actorLabel({ ...entry, actor: "staff:y", channel: "dashboard" })).toBe("Staff");
  });
});
