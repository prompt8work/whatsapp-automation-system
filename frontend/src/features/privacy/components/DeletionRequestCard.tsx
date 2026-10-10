import { useState } from "react";

import { formatDate, relative } from "@/shared/lib/time";
import { Badge } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { Input } from "@/shared/ui/Field";

import { describeCounts, patientNames, type DeletionRequest } from "../model/privacy";

type Props = {
  request: DeletionRequest;
  timeZone: string;
  busy: boolean;
  onApprove: () => void;
  onReject: (reason: string) => void;
};

const TONE = { pending: "warn", completed: "good", rejected: "neutral" } as const;

/** One "delete my data" request. Approving deletes for good, so it asks once more. */
export function DeletionRequestCard({ request: r, timeZone, busy, onApprove, onReject }: Props) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{patientNames(r)}</span>
        <Badge tone={TONE[r.status]}>{r.status}</Badge>
        <span className="text-sm text-slate-500">asked {relative(r.requested_at)}</span>
        {r.status === "pending" && (
          <span className="text-sm text-amber-700">answer by {formatDate(r.answer_by, timeZone)}</span>
        )}
      </div>
      {r.status === "completed" && (
        <p className="mt-1 text-sm text-slate-600">Deleted: {describeCounts(r.deleted_counts) || "nothing left"}</p>
      )}
      {r.status === "rejected" && <p className="mt-1 text-sm text-slate-600">Reason: {r.rejection_reason}</p>}

      {r.status === "pending" && (
        <>
          <p className="mt-2 text-sm text-slate-600">
            Approving cancels their upcoming appointments and permanently deletes their profile, cases and history.
            Payment records are kept.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button
              disabled={busy}
              onClick={() => {
                if (window.confirm(`Permanently delete the data of ${patientNames(r)}?`)) onApprove();
              }}
            >
              Approve and delete
            </Button>
            {rejecting ? (
              <form
                className="flex flex-wrap gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (reason.trim()) onReject(reason.trim());
                }}
              >
                <Input
                  className="w-80"
                  placeholder="Reason, sent to the patient"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
                <Button type="submit" variant="ghost" className="border border-slate-200" disabled={busy || !reason.trim()}>
                  Reject
                </Button>
              </form>
            ) : (
              <Button variant="ghost" onClick={() => setRejecting(true)}>
                Reject…
              </Button>
            )}
          </div>
        </>
      )}
    </article>
  );
}
