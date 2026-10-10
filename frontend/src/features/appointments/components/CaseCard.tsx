import type { Schemas } from "@/shared/api/types";
import { formatDate } from "@/shared/lib/time";
import { Badge } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";

type Case = Schemas["CaseResponse"];
type Action = { kind: "close"; note: string } | { kind: "reopen" } | { kind: "hold"; hold: boolean };
type Props = { case: Case; timeZone: string; canManage: boolean; busy: boolean; onAction: (a: Action) => void };

/** The treatment episode this appointment belongs to (PRD AP-10.1-10.6): close / reopen,
 * legal hold, and when retention will delete it. */
export function CaseCard({ case: c, timeZone, canManage, busy, onAction }: Props) {
  const open = c.status === "open";
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={open ? "info" : "neutral"}>{open ? "open" : "closed"}</Badge>
        {c.legal_hold && <Badge tone="warn">legal hold</Badge>}
        <span className="text-slate-500">since {formatDate(c.opened_at, timeZone)}</span>
      </div>
      {c.closing_note && <p className="text-slate-600">“{c.closing_note}”</p>}
      <p className="text-slate-600">
        {c.deletes_at
          ? `${open ? "If nothing happens, its data" : "Its data"} will be deleted on ${formatDate(c.deletes_at, timeZone)}.`
          : "Kept until the legal hold is lifted."}
      </p>
      {canManage && (
        <div className="flex flex-wrap gap-2">
          {open ? (
            <Button
              variant="ghost"
              className="border border-slate-200"
              disabled={busy}
              onClick={() => {
                const note = window.prompt("Closing note (optional, staff only):");
                if (note !== null) onAction({ kind: "close", note });
              }}
            >
              Close case
            </Button>
          ) : (
            <Button variant="ghost" className="border border-slate-200" disabled={busy} onClick={() => onAction({ kind: "reopen" })}>
              Reopen case
            </Button>
          )}
          <Button variant="ghost" disabled={busy} onClick={() => onAction({ kind: "hold", hold: !c.legal_hold })}>
            {c.legal_hold ? "Lift legal hold" : "Legal hold"}
          </Button>
        </div>
      )}
    </div>
  );
}
