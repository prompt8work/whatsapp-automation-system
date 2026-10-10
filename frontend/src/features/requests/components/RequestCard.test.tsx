import { fireEvent, render, screen } from "@testing-library/react";

import type { Appointment } from "../model/requests";
import { RequestCard } from "./RequestCard";

const slot = (start: string) => ({ doctor_id: "d", start, end: start });
const request: Appointment = {
  id: "a",
  reference: "APT-7K3Q",
  status: "confirmed",
  case_id: "c",
  patient_id: "p",
  patient_name: "Rahul Verma",
  doctor_name: "Dr. Amit",
  location_id: "l",
  slot: slot("2026-10-16T09:30:00Z"),
  original_slot: slot("2026-10-16T09:30:00Z"),
  was_rescheduled: false,
  pending_slot: slot("2026-10-17T11:30:00Z"),
  reason: "Fever",
  fields: {},
  created_at: "2026-10-10T09:00:00Z",
};

describe("RequestCard", () => {
  it("shows a reschedule request as old -> new time in the clinic timezone", () => {
    render(<RequestCard appointment={request} timeZone="Asia/Kolkata" busy={false} onApprove={vi.fn()} onDecline={vi.fn()} />);
    expect(screen.getByText("Reschedule")).toBeInTheDocument();
    expect(screen.getByText(/Fri, 16 Oct, 3:00\s?pm/i)).toBeInTheDocument();
    expect(screen.getByText(/Sat, 17 Oct, 5:00\s?pm/i)).toBeInTheDocument();
  });

  it("asks for a reason before declining", () => {
    const onDecline = vi.fn();
    render(<RequestCard appointment={request} timeZone="Asia/Kolkata" busy={false} onApprove={vi.fn()} onDecline={onDecline} />);
    fireEvent.click(screen.getByRole("button", { name: "Decline…" }));
    fireEvent.change(screen.getByLabelText("Reason for declining"), { target: { value: "Doctor on leave" } });
    fireEvent.click(screen.getByRole("button", { name: "Send decline" }));
    expect(onDecline).toHaveBeenCalledWith("Doctor on leave");
  });
});
