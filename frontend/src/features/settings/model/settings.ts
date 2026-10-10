import type { Schemas } from "@/shared/api/types";

export type Location = Schemas["LocationResponse"];
export type BookingRules = Schemas["AppointmentSettings"];
export type Member = Schemas["MemberResponse"];
export type WorkingHours = Schemas["WorkingHoursSchema"];

export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

/** One editable row per weekday (one block per day keeps the form simple). */
export type DayForm = { on: boolean; start: string; end: string };

const hhmm = (t: string) => t.slice(0, 5);

export function toWeekForm(hours: WorkingHours[]): DayForm[] {
  return WEEKDAYS.map((_, weekday) => {
    const block = hours.find((h) => h.weekday === weekday);
    return block ? { on: true, start: hhmm(block.start), end: hhmm(block.end) } : { on: false, start: "09:00", end: "17:00" };
  });
}

export function fromWeekForm(form: DayForm[]): WorkingHours[] {
  return form.flatMap((d, weekday) => (d.on ? [{ weekday, start: d.start, end: d.end }] : []));
}

/** Problems the backend would reject anyway - shown before saving. */
export function weekFormErrors(form: DayForm[]): string[] {
  return form.flatMap((d, i) => (d.on && d.end <= d.start ? [`${WEEKDAYS[i]}: end must be after start`] : []));
}
