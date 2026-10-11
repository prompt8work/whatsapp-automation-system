import type { FormEvent } from "react";

import { Button } from "@/shared/ui/Button";
import { Field, Input } from "@/shared/ui/Field";

import { parseHours, type BookingRules } from "../model/settings";

type Props = { rules: BookingRules; busy: boolean; onSave: (rules: BookingRules) => void };

/** The clinic's booking rules (PRD AP-7.7). Custom booking questions keep their current value. */
export function BookingRulesForm({ rules, busy, onSave }: Props) {
  function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    onSave({
      ...rules,
      approval_required: f.get("approval_required") === "on",
      reason_required: f.get("reason_required") === "on",
      ai_understanding: f.get("ai_understanding") === "on",
      request_expiry_hours: Number(f.get("request_expiry_hours")),
      change_cutoff_hours: Number(f.get("change_cutoff_hours")),
      min_notice_minutes: Number(f.get("min_notice_minutes")),
      horizon_days: Number(f.get("horizon_days")),
      retention_closed_days: Number(f.get("retention_closed_days")),
      retention_open_days: Number(f.get("retention_open_days")),
      consultation_fee: Number(f.get("consultation_fee")),
      reminder_hours: parseHours(String(f.get("reminder_hours") ?? "")),
    });
  }
  return (
    <form onSubmit={save} className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="approval_required" defaultChecked={rules.approval_required} />
        Staff approve every booking and reschedule request
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="reason_required" defaultChecked={rules.reason_required} />
        Ask patients for the reason for the visit
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" name="ai_understanding" defaultChecked={rules.ai_understanding} className="mt-1" />
        <span>
          Let AI read free-typed dates, times and requests the bot doesn't understand (e.g. "day after tomorrow
          evening", "I need to move my visit")
          <span className="block text-xs text-slate-500">
            Only that message's text is sent to Anthropic (Claude) - never names or phone numbers. Check this is
            allowed by your data-protection policy.
          </span>
        </span>
      </label>
      <div className="grid gap-3 md:grid-cols-4">
        <Field label="Unanswered requests expire after (hours)">
          <Input name="request_expiry_hours" type="number" min={1} max={168} step="0.5" defaultValue={rules.request_expiry_hours} />
        </Field>
        <Field label="Patients can't change within (hours)">
          <Input name="change_cutoff_hours" type="number" min={0} max={72} step="0.5" defaultValue={rules.change_cutoff_hours} />
        </Field>
        <Field label="Book at least (minutes) ahead">
          <Input name="min_notice_minutes" type="number" min={0} defaultValue={rules.min_notice_minutes} />
        </Field>
        <Field label="Book up to (days) ahead">
          <Input name="horizon_days" type="number" min={1} max={365} defaultValue={rules.horizon_days} />
        </Field>
      </div>
      <Field label="Send reminders this many hours before (comma-separated, e.g. 24, 2; empty = none)">
        <Input name="reminder_hours" defaultValue={(rules.reminder_hours ?? []).join(", ")} className="w-40" />
      </Field>
      <Field label="Consultation fee in ₹ (0 = patients aren't asked to pay; methods in Settings → Payments)">
        <Input name="consultation_fee" type="number" min={0} step="1" defaultValue={rules.consultation_fee} className="w-40" />
      </Field>
      <fieldset className="grid gap-3 md:grid-cols-2">
        <legend className="mb-2 text-sm font-medium text-slate-700">
          Data retention <span className="font-normal text-slate-500">(check the periods your law requires)</span>
        </legend>
        <Field label="Delete closed cases after (days)">
          <Input name="retention_closed_days" type="number" min={1} max={3650} defaultValue={rules.retention_closed_days} />
        </Field>
        <Field label="Delete inactive open cases after (days)">
          <Input name="retention_open_days" type="number" min={30} max={3650} defaultValue={rules.retention_open_days} />
        </Field>
      </fieldset>
      <Button type="submit" disabled={busy}>
        Save rules
      </Button>
    </form>
  );
}
