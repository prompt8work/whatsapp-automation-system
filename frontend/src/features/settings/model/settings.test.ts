import { fromWeekForm, parseHours, toWeekForm, weekFormErrors } from "./settings";

describe("weekly hours form", () => {
  it("round-trips the backend format (one block per day)", () => {
    const hours = [
      { weekday: 0, start: "09:00:00", end: "13:00:00" },
      { weekday: 5, start: "10:00:00", end: "12:30:00" },
    ];
    const form = toWeekForm(hours);
    expect(form[0]).toEqual({ on: true, start: "09:00", end: "13:00" });
    expect(form[1]?.on).toBe(false);
    expect(fromWeekForm(form)).toEqual([
      { weekday: 0, start: "09:00", end: "13:00" },
      { weekday: 5, start: "10:00", end: "12:30" },
    ]);
  });

  it("flags days that end before they start", () => {
    const form = toWeekForm([{ weekday: 2, start: "18:00:00", end: "09:00:00" }]);
    expect(weekFormErrors(form)).toEqual(["Wed: end must be after start"]);
  });
});

describe("reminder hours", () => {
  it("reads a comma-separated list and drops junk", () => {
    expect(parseHours("24, 2")).toEqual([24, 2]);
    expect(parseHours("")).toEqual([]);
    expect(parseHours("x, 0, 1.5")).toEqual([1.5]);
  });
});
