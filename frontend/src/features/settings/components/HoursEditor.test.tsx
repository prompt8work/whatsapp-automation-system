import { fireEvent, render, screen } from "@testing-library/react";

import { HoursEditor } from "./HoursEditor";

describe("HoursEditor", () => {
  it("saves only the days that are switched on", () => {
    const onSave = vi.fn();
    render(<HoursEditor hours={[{ weekday: 0, start: "09:00:00", end: "13:00:00" }]} busy={false} onSave={onSave} />);
    fireEvent.click(screen.getByLabelText("Tue"));
    fireEvent.click(screen.getByRole("button", { name: "Save hours" }));
    expect(onSave).toHaveBeenCalledWith([
      { weekday: 0, start: "09:00", end: "13:00" },
      { weekday: 1, start: "09:00", end: "17:00" },
    ]);
  });

  it("blocks saving impossible hours", () => {
    render(<HoursEditor hours={[]} busy={false} onSave={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Mon"));
    fireEvent.change(screen.getByLabelText("Mon end"), { target: { value: "08:00" } });
    expect(screen.getByRole("alert")).toHaveTextContent("Mon: end must be after start");
    expect(screen.getByRole("button", { name: "Save hours" })).toBeDisabled();
  });
});
