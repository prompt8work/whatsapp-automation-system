import { useState } from "react";

import { Button } from "@/shared/ui/Button";

import { WEEKDAYS, fromWeekForm, toWeekForm, weekFormErrors, type WorkingHours } from "../model/settings";

type Props = { hours: WorkingHours[]; busy: boolean; onSave: (hours: WorkingHours[]) => void };

/** Weekly working hours in the clinic's local time (one block per day). */
export function HoursEditor({ hours, busy, onSave }: Props) {
  const [form, setForm] = useState(() => toWeekForm(hours));
  const errors = weekFormErrors(form);
  const update = (i: number, patch: Partial<(typeof form)[number]>) =>
    setForm(form.map((d, j) => (j === i ? { ...d, ...patch } : d)));

  return (
    <div className="space-y-2">
      {form.map((d, i) => (
        <div key={WEEKDAYS[i]} className="flex items-center gap-2 text-sm">
          <label className="flex w-16 items-center gap-1">
            <input type="checkbox" checked={d.on} onChange={(e) => update(i, { on: e.target.checked })} />
            {WEEKDAYS[i]}
          </label>
          <input type="time" aria-label={`${WEEKDAYS[i]} start`} disabled={!d.on} value={d.start} onChange={(e) => update(i, { start: e.target.value })} className="rounded border border-slate-300 px-2 py-1" />
          <span>–</span>
          <input type="time" aria-label={`${WEEKDAYS[i]} end`} disabled={!d.on} value={d.end} onChange={(e) => update(i, { end: e.target.value })} className="rounded border border-slate-300 px-2 py-1" />
        </div>
      ))}
      {errors.map((e) => (
        <p key={e} role="alert" className="text-sm text-rose-600">
          {e}
        </p>
      ))}
      <Button disabled={busy || errors.length > 0} onClick={() => onSave(fromWeekForm(form))}>
        Save hours
      </Button>
    </div>
  );
}
