import { useState, type FormEvent } from "react";

import type { Doctor } from "@/features/appointments";
import { Badge } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { Field, Input, Select } from "@/shared/ui/Field";

import type { Location, WorkingHours } from "../model/settings";
import { HoursEditor } from "./HoursEditor";

type Props = {
  doctors: Doctor[];
  locations: Location[];
  busy: boolean;
  onAdd: (d: { name: string; specialty: string; slot_minutes: number; location_id: string }) => void;
  onSaveHours: (id: string, hours: WorkingHours[]) => void;
  onToggleActive: (id: string, active: boolean) => void;
};

const SLOT_LENGTHS = [10, 15, 20, 30, 45, 60];

export function DoctorsPanel({ doctors, locations, busy, onAdd, onSaveHours, onToggleActive }: Props) {
  const [open, setOpen] = useState<string | null>(null);

  function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    onAdd({
      name: String(f.get("name")),
      specialty: String(f.get("specialty")),
      slot_minutes: Number(f.get("slot")),
      location_id: String(f.get("location")),
    });
    e.currentTarget.reset();
  }

  return (
    <div className="space-y-4">
      <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
        {doctors.map((d) => (
          <li key={d.id} className="p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <span className="font-medium">{d.name}</span> <span className="text-sm text-slate-500">{d.specialty}</span>{" "}
                <span className="text-xs text-slate-400">· {d.slot_minutes} min slots</span>{" "}
                {!d.is_active && <Badge tone="neutral">Inactive</Badge>}
                {d.working_hours.length === 0 && <Badge tone="warn">No hours set</Badge>}
              </div>
              <div className="flex gap-2">
                <Button variant="ghost" onClick={() => setOpen(open === d.id ? null : d.id)}>
                  {open === d.id ? "Close" : "Working hours"}
                </Button>
                <Button variant="ghost" disabled={busy} onClick={() => onToggleActive(d.id, !d.is_active)}>
                  {d.is_active ? "Deactivate" : "Activate"}
                </Button>
              </div>
            </div>
            {open === d.id && (
              <div className="mt-3">
                <HoursEditor hours={d.working_hours} busy={busy} onSave={(hours) => onSaveHours(d.id, hours)} />
              </div>
            )}
          </li>
        ))}
      </ul>

      <form onSubmit={add} className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 md:grid-cols-5">
        <Field label="Name">
          <Input name="name" required placeholder="Dr. Amit Sharma" />
        </Field>
        <Field label="Specialty">
          <Input name="specialty" placeholder="General" />
        </Field>
        <Field label="Slot length">
          <Select name="slot" defaultValue={15}>
            {SLOT_LENGTHS.map((m) => (
              <option key={m} value={m}>
                {m} min
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Location">
          <Select name="location" required>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </Select>
        </Field>
        <div className="flex items-end">
          <Button type="submit" disabled={busy || locations.length === 0}>
            Add doctor
          </Button>
        </div>
      </form>
      {locations.length === 0 && <p className="text-sm text-amber-700">Add a location first.</p>}
    </div>
  );
}
