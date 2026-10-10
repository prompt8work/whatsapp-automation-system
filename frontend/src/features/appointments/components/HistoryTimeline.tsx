import { formatWhen } from "@/shared/lib/time";

import { actorLabel, eventLabel, type HistoryEntry } from "../model/appointments";

/** Every change to the appointment, oldest first (PRD AP-7.4). */
export function HistoryTimeline({ entries, timeZone }: { entries: HistoryEntry[]; timeZone: string }) {
  return (
    <ol className="space-y-3 border-l-2 border-slate-200 pl-4">
      {entries.map((e, i) => (
        <li key={i} className="relative">
          <span className="absolute -left-[1.4rem] top-1.5 size-2.5 rounded-full bg-brand" />
          <p className="text-sm font-medium">{eventLabel(e)}</p>
          <p className="text-xs text-slate-500">
            {formatWhen(e.occurred_at, timeZone)} · {actorLabel(e)}
          </p>
          {typeof e.data.old_start === "string" && typeof e.data.new_start === "string" && (
            <p className="text-xs text-slate-600">
              {formatWhen(e.data.old_start, timeZone)} → {formatWhen(e.data.new_start, timeZone)}
            </p>
          )}
          {typeof e.data.requested_start === "string" && (
            <p className="text-xs text-slate-600">to {formatWhen(e.data.requested_start, timeZone)}</p>
          )}
          {typeof e.data.reason === "string" && e.data.reason && (
            <p className="text-xs text-slate-600">“{e.data.reason}”</p>
          )}
        </li>
      ))}
    </ol>
  );
}
