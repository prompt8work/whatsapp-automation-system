import type { FormEvent } from "react";

import { Button } from "@/shared/ui/Button";
import { Field, Input } from "@/shared/ui/Field";

import type { TemplateSlot } from "../model/settings";

type Props = {
  slots: TemplateSlot[];
  busy: boolean;
  onSave: (slot: string, templateName: string, language: string) => void;
};

/** WhatsApp only allows approved templates 24 h after the patient's last message (PRD PL-4.2).
 * Create each template in WhatsApp Manager (the example shows the variables and buttons in
 * order), wait for approval, then enter its name here. Without one, such messages are skipped. */
export function TemplatesPanel({ slots, busy, onSave }: Props) {
  function save(slot: string) {
    return (e: FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      const f = new FormData(e.currentTarget);
      onSave(slot, String(f.get("template_name") ?? "").trim(), String(f.get("language") ?? "en").trim());
    };
  }
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">
        Messages sent more than 24 hours after a patient's last message must use a template approved by Meta. Create
        each one in WhatsApp Manager with the variables and quick-reply buttons in the order shown, then enter its name
        here. Leave the name empty to stop using a template.
      </p>
      {slots.map((s) => (
        <form key={s.slot} onSubmit={save(s.slot)} className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="font-medium">{s.description}</h3>
            <span className={`text-xs ${s.template_name ? "text-emerald-700" : "text-amber-700"}`}>
              {s.template_name ? `Using ${s.template_name} (${s.language})` : "No template - skipped outside 24 h"}
            </span>
          </div>
          {s.example && <p className="text-sm text-slate-600">Example: “{s.example}”</p>}
          <p className="text-xs text-slate-500">
            Variables: {s.params.map((p, i) => `{{${i + 1}}} ${p}`).join(", ") || "none"}
            {s.buttons.length > 0 && ` · Quick-reply buttons: ${s.buttons.join(", ")}`}
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Template name">
              <Input name="template_name" defaultValue={s.template_name ?? ""} placeholder="visit_reminder" className="w-64" />
            </Field>
            <Field label="Language">
              <Input name="language" defaultValue={s.language ?? "en"} className="w-24" />
            </Field>
            <Button type="submit" disabled={busy}>
              Save
            </Button>
          </div>
        </form>
      ))}
    </div>
  );
}
