import { useState } from "react";

import { formatWhen, relative } from "@/shared/lib/time";
import { Badge } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { Input } from "@/shared/ui/Field";

import { requestKind, type Appointment } from "../model/requests";

type Props = {
  appointment: Appointment;
  timeZone: string;
  busy: boolean;
  onApprove: () => void;
  onDecline: (reason: string) => void;
};

export function RequestCard({ appointment: a, timeZone, busy, onApprove, onDecline }: Props) {
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const kind = requestKind(a);

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium">
            {a.patient_name} <span className="text-slate-400">·</span> {a.doctor_name}
          </p>
          {kind === "new" ? (
            <p className="text-sm text-slate-700">{formatWhen(a.slot.start, timeZone)}</p>
          ) : (
            <p className="text-sm text-slate-700">
              <span className="line-through">{formatWhen(a.slot.start, timeZone)}</span> →{" "}
              <strong>{formatWhen(a.pending_slot!.start, timeZone)}</strong>
            </p>
          )}
          {a.reason && <p className="mt-1 text-sm text-slate-500">“{a.reason}”</p>}
        </div>
        <div className="text-right">
          <Badge tone={kind === "new" ? "info" : "warn"}>{kind === "new" ? "New request" : "Reschedule"}</Badge>
          <p className="mt-1 text-xs text-slate-400">
            {a.reference} · {relative(a.created_at)}
          </p>
        </div>
      </div>

      {declining ? (
        <form
          className="mt-3 flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            onDecline(reason);
          }}
        >
          <Input
            aria-label="Reason for declining"
            placeholder="Reason (sent to the patient)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="min-w-60 flex-1"
          />
          <Button type="submit" disabled={busy}>
            Send decline
          </Button>
          <Button variant="ghost" onClick={() => setDeclining(false)}>
            Back
          </Button>
        </form>
      ) : (
        <div className="mt-3 flex gap-2">
          <Button disabled={busy} onClick={onApprove}>
            Approve
          </Button>
          <Button variant="ghost" disabled={busy} onClick={() => setDeclining(true)}>
            Decline…
          </Button>
        </div>
      )}
    </article>
  );
}
