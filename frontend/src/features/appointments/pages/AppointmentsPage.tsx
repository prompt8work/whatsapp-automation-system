import { useState } from "react";
import { useNavigate } from "react-router";

import { useTimezone } from "@/features/clinic";
import { addDays, localDate } from "@/shared/lib/time";
import { Button } from "@/shared/ui/Button";
import { Input, Select } from "@/shared/ui/Field";
import { Empty, ErrorText, Loading } from "@/shared/ui/Feedback";
import { PageHeader } from "@/shared/ui/PageHeader";

import { useAppointments } from "../api/appointments";
import { AppointmentTable } from "../components/AppointmentTable";
import { STATUSES } from "../model/appointments";

/** One day's appointments (PRD AP-7.2). Doctors automatically see only their own. */
export function AppointmentsPage() {
  const timeZone = useTimezone();
  const today = localDate(new Date(), timeZone);
  const [day, setDay] = useState(today);
  const [status, setStatus] = useState("");
  const appointments = useAppointments(day, status);
  const navigate = useNavigate();

  return (
    <div>
      <PageHeader title="Appointments">
        <Button variant="ghost" onClick={() => setDay(addDays(day, -1))} aria-label="Previous day">
          ←
        </Button>
        <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} aria-label="Day" className="w-40" />
        <Button variant="ghost" onClick={() => setDay(addDays(day, 1))} aria-label="Next day">
          →
        </Button>
        {day !== today && (
          <Button variant="ghost" onClick={() => setDay(today)}>
            Today
          </Button>
        )}
        <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status" className="w-40">
          <option value="">All statuses</option>
          {Object.entries(STATUSES).map(([value, { label }]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </PageHeader>
      <ErrorText error={appointments.error} />
      {appointments.isLoading && <Loading />}
      {appointments.data?.length === 0 && <Empty>No appointments on this day.</Empty>}
      {!!appointments.data?.length && (
        <AppointmentTable
          appointments={appointments.data}
          timeZone={timeZone}
          onOpen={(id) => navigate(`/appointments/${id}`)}
        />
      )}
      <p className="mt-2 text-xs text-slate-400">Times shown in {timeZone}.</p>
    </div>
  );
}
