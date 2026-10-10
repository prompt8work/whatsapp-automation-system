import type { FormEvent } from "react";

import { Button } from "@/shared/ui/Button";
import { Field, Input } from "@/shared/ui/Field";

import type { Location } from "../model/settings";

type Props = { locations: Location[]; busy: boolean; onAdd: (l: { name: string; address: string }) => void };

export function LocationsPanel({ locations, busy, onAdd }: Props) {
  function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    onAdd({ name: String(f.get("name")), address: String(f.get("address")) });
    e.currentTarget.reset();
  }
  return (
    <div className="space-y-4">
      <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
        {locations.map((l) => (
          <li key={l.id} className="p-3 text-sm">
            <span className="font-medium">{l.name}</span> <span className="text-slate-500">{l.address}</span>{" "}
            <span className="text-xs text-slate-400">· {l.timezone}</span>
          </li>
        ))}
      </ul>
      <form onSubmit={add} className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 md:grid-cols-3">
        <Field label="Name">
          <Input name="name" required placeholder="MG Road" />
        </Field>
        <Field label="Address">
          <Input name="address" placeholder="12 MG Road, Bengaluru" />
        </Field>
        <div className="flex items-end">
          <Button type="submit" disabled={busy}>
            Add location
          </Button>
        </div>
      </form>
    </div>
  );
}
