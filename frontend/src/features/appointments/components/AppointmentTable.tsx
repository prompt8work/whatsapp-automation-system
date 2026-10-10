import { formatTime } from "@/shared/lib/time";
import { Badge } from "@/shared/ui/Badge";

import type { Appointment } from "../model/appointments";
import { StatusBadge } from "./StatusBadge";

type Props = { appointments: Appointment[]; timeZone: string; onOpen: (id: string) => void };

export function AppointmentTable({ appointments, timeZone, onOpen }: Props) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-3 py-2">Time</th>
            <th className="px-3 py-2">Patient</th>
            <th className="px-3 py-2">Doctor</th>
            <th className="px-3 py-2">Reason</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Ref</th>
          </tr>
        </thead>
        <tbody>
          {appointments.map((a) => (
            <tr
              key={a.id}
              onClick={() => onOpen(a.id)}
              className="cursor-pointer border-t border-slate-100 hover:bg-slate-50"
            >
              <td className="px-3 py-2 whitespace-nowrap">
                {formatTime(a.slot.start, timeZone)}
                {a.was_rescheduled && (
                  <span className="ml-2">
                    <Badge tone="warn">moved</Badge>
                  </span>
                )}
              </td>
              <td className="px-3 py-2">{a.patient_name}</td>
              <td className="px-3 py-2">{a.doctor_name}</td>
              <td className="max-w-64 truncate px-3 py-2 text-slate-500">{a.reason}</td>
              <td className="px-3 py-2">
                <StatusBadge status={a.status} />
              </td>
              <td className="px-3 py-2 font-mono text-xs">{a.reference}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
