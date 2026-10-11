import { useState, type FormEvent } from "react";

import { Button } from "@/shared/ui/Button";
import { Field, Input } from "@/shared/ui/Field";

import { METHOD_LABEL, type PaymentMethod, type PaymentSettings } from "../model/payments";

type Props = {
  settings: PaymentSettings & { razorpay_secrets_saved: boolean; razorpay_webhook_path: string };
  busy: boolean;
  onSave: (settings: PaymentSettings) => void;
  onSaveSecrets: (secrets: { key_secret: string; webhook_secret: string }) => void;
};

const ORDER: PaymentMethod[] = ["whatsapp_pay", "razorpay_link", "at_clinic"];

/** Which payment methods the clinic offers (PRD PL-6.1, PL-6.2). Secrets are write-only. */
export function PaymentSettingsForm({ settings, busy, onSave, onSaveSecrets }: Props) {
  const [methods, setMethods] = useState<PaymentMethod[]>(settings.methods ?? []);
  const toggle = (m: PaymentMethod) => setMethods((now) => (now.includes(m) ? now.filter((x) => x !== m) : [...now, m]));

  function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    onSave({
      methods: ORDER.filter((m) => methods.includes(m)),
      whatsapp_pay_configuration: String(f.get("whatsapp_pay_configuration") ?? ""),
      razorpay_key_id: String(f.get("razorpay_key_id") ?? ""),
    });
  }

  function saveSecrets(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    onSaveSecrets({ key_secret: String(f.get("key_secret")), webhook_secret: String(f.get("webhook_secret")) });
    e.currentTarget.reset();
  }

  return (
    <div className="space-y-4">
      <form onSubmit={save} className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
        <p className="text-sm text-slate-600">
          Patients are asked to pay the consultation fee (Booking rules) once their appointment is confirmed. They are offered
          the first method switched on below; staff can always mark a payment as paid at the counter.
        </p>
        {ORDER.map((m) => (
          <label key={m} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={methods.includes(m)} onChange={() => toggle(m)} />
            {METHOD_LABEL[m]}
          </label>
        ))}
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="WhatsApp Payments configuration name (from WhatsApp Business Manager)">
            <Input name="whatsapp_pay_configuration" defaultValue={settings.whatsapp_pay_configuration} />
          </Field>
          <Field label="Razorpay key id">
            <Input name="razorpay_key_id" defaultValue={settings.razorpay_key_id} placeholder="rzp_live_…" />
          </Field>
        </div>
        <Button type="submit" disabled={busy}>
          Save payment settings
        </Button>
      </form>

      <form onSubmit={saveSecrets} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
        <p className="text-sm text-slate-600">
          Razorpay secrets {settings.razorpay_secrets_saved ? "are saved (enter new ones to replace them)" : "are not saved yet"}.
          In the Razorpay dashboard, add a webhook to <code className="rounded bg-slate-100 px-1">{`<your API address>${settings.razorpay_webhook_path}`}</code>{" "}
          for the events payment_link.paid, payment_link.expired, payment_link.cancelled and refund.processed.
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Razorpay key secret">
            <Input name="key_secret" type="password" autoComplete="off" required minLength={8} />
          </Field>
          <Field label="Razorpay webhook secret">
            <Input name="webhook_secret" type="password" autoComplete="off" required minLength={8} />
          </Field>
        </div>
        <Button type="submit" disabled={busy}>
          Save secrets
        </Button>
      </form>
    </div>
  );
}
