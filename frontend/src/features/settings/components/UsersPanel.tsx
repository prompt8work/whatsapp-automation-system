import type { FormEvent } from "react";

import { Badge } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { Field, Input, Select } from "@/shared/ui/Field";

import type { Member } from "../model/settings";

type NewMember = { email: string; full_name: string; role: "admin" | "staff" | "doctor"; initial_password: string };
type Props = { members: Member[]; busy: boolean; onAdd: (m: NewMember) => void };

export function UsersPanel({ members, busy, onAdd }: Props) {
  function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    onAdd({
      email: String(f.get("email")),
      full_name: String(f.get("full_name")),
      role: String(f.get("role")) as NewMember["role"],
      initial_password: String(f.get("password")),
    });
    e.currentTarget.reset();
  }
  return (
    <div className="space-y-4">
      <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
        {members.map((m) => (
          <li key={m.user_id} className="flex items-center justify-between p-3 text-sm">
            <span>
              <span className="font-medium">{m.full_name}</span> <span className="text-slate-500">{m.email}</span>
            </span>
            <Badge tone={m.role === "admin" ? "info" : "neutral"}>{m.role}</Badge>
          </li>
        ))}
      </ul>
      <form onSubmit={add} className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 md:grid-cols-5">
        <Field label="Name">
          <Input name="full_name" required />
        </Field>
        <Field label="Email">
          <Input name="email" type="email" required />
        </Field>
        <Field label="Role">
          <Select name="role" defaultValue="staff">
            <option value="staff">Staff</option>
            <option value="doctor">Doctor</option>
            <option value="admin">Admin</option>
          </Select>
        </Field>
        <Field label="Initial password">
          <Input name="password" type="password" minLength={10} required />
        </Field>
        <div className="flex items-end">
          <Button type="submit" disabled={busy}>
            Add user
          </Button>
        </div>
      </form>
    </div>
  );
}
