import { useState } from "react";
import { Link, useParams } from "react-router";

import { usePermission } from "@/features/auth";
import { useTimezone } from "@/features/clinic";
import { addDays, formatWhen, localDate } from "@/shared/lib/time";
import { Button } from "@/shared/ui/Button";
import { Card } from "@/shared/ui/Card";
import { Input } from "@/shared/ui/Field";
import { ErrorText, Loading } from "@/shared/ui/Feedback";
import { PageHeader } from "@/shared/ui/PageHeader";

import { useAppointment, useAppointmentAction, useCaseAction, usePatientCases, useSlots } from "../api/appointments";
import { CaseCard } from "../components/CaseCard";
import { HistoryTimeline } from "../components/HistoryTimeline";
import { SlotPicker } from "../components/SlotPicker";
import { StatusBadge } from "../components/StatusBadge";
import { actionsFor } from "../model/appointments";

/** Everything about one appointment on one screen (PRD AP-7.3, AP-7.4, AP-7.5). */
export function AppointmentDetailPage() {
  const { appointmentId = "" } = useParams();
  const timeZone = useTimezone();
  const detail = useAppointment(appointmentId);
  const act = useAppointmentAction(appointmentId);
  const canManageCases = usePermission("case.manage");
  const [moving, setMoving] = useState(false);
  const [moveDay, setMoveDay] = useState(addDays(localDate(new Date(), timeZone), 1));
  const a = detail.data?.appointment;
  const slots = useSlots(moving && a ? a.slot.doctor_id : "", moveDay);
  const cases = usePatientCases(a?.patient_id ?? "");
  const caseAction = useCaseAction(a?.case_id ?? "");
  const theCase = cases.data?.find((c) => c.id === a?.case_id);

  if (detail.isLoading) return <Loading />;
  if (!detail.data || !a) return <ErrorText error={detail.error ?? new Error("Not found")} />;
  const can = actionsFor(a);

  return (
    <div>
      <p className="mb-2 text-sm">
        <Link to="/appointments" className="text-slate-500 hover:underline">
          ← Appointments
        </Link>
      </p>
      <PageHeader title={`${a.patient_name} · ${a.reference}`}>
        <StatusBadge status={a.status} />
      </PageHeader>
      <ErrorText error={act.error ?? caseAction.error} />

      <div className="grid gap-4 md:grid-cols-3">
        <div className="space-y-4 md:col-span-2">
          <Card title="Appointment">
            <dl className="grid grid-cols-[9rem_1fr] gap-y-2 text-sm">
              <dt className="text-slate-500">When</dt>
              <dd className="font-medium">{formatWhen(a.slot.start, timeZone)}</dd>
              {a.was_rescheduled && (
                <>
                  <dt className="text-slate-500">Originally</dt>
                  <dd className="text-slate-500 line-through">{formatWhen(a.original_slot.start, timeZone)}</dd>
                </>
              )}
              {a.pending_slot && (
                <>
                  <dt className="text-slate-500">Patient asks for</dt>
                  <dd>{formatWhen(a.pending_slot.start, timeZone)} (see Requests)</dd>
                </>
              )}
              <dt className="text-slate-500">Doctor</dt>
              <dd>{a.doctor_name}</dd>
              <dt className="text-slate-500">Phone</dt>
              <dd>{detail.data.phone}</dd>
              <dt className="text-slate-500">Reason</dt>
              <dd>{a.reason || "—"}</dd>
              {Object.entries(a.fields).map(([key, value]) => (
                <div key={key} className="contents">
                  <dt className="text-slate-500">{key}</dt>
                  <dd>{String(value)}</dd>
                </div>
              ))}
            </dl>
          </Card>

          {(can.reschedule || can.cancel || can.attendance) && (
            <Card title="Actions">
              <div className="flex flex-wrap gap-2">
                {can.reschedule && (
                  <Button variant="ghost" className="border border-slate-200" onClick={() => setMoving(!moving)}>
                    Reschedule…
                  </Button>
                )}
                {can.cancel && (
                  <Button
                    variant="ghost"
                    className="border border-slate-200"
                    disabled={act.isPending}
                    onClick={() => {
                      const reason = window.prompt("Reason for cancelling (sent to the patient):");
                      if (reason !== null) act.mutate({ kind: "cancel", reason });
                    }}
                  >
                    Cancel appointment
                  </Button>
                )}
                {can.attendance && (
                  <>
                    <Button disabled={act.isPending} onClick={() => act.mutate({ kind: "attendance", attended: true })}>
                      Mark completed
                    </Button>
                    <Button
                      variant="ghost"
                      disabled={act.isPending}
                      onClick={() => act.mutate({ kind: "attendance", attended: false })}
                    >
                      Mark no-show
                    </Button>
                  </>
                )}
              </div>
              {moving && (
                <div className="mt-4 space-y-3">
                  <Input type="date" value={moveDay} onChange={(e) => setMoveDay(e.target.value)} className="w-44" />
                  {slots.isLoading ? (
                    <Loading />
                  ) : (
                    <SlotPicker
                      slots={slots.data?.slots ?? []}
                      timeZone={timeZone}
                      disabled={act.isPending}
                      onPick={(start) => act.mutate({ kind: "reschedule", start }, { onSuccess: () => setMoving(false) })}
                    />
                  )}
                </div>
              )}
            </Card>
          )}
        </div>

        <div className="space-y-4">
          {theCase && (
            <Card title="Case">
              <CaseCard
                case={theCase}
                timeZone={timeZone}
                canManage={canManageCases}
                busy={caseAction.isPending}
                onAction={(action) => caseAction.mutate(action)}
              />
            </Card>
          )}
          <Card title="History">
            <HistoryTimeline entries={detail.data.history} timeZone={timeZone} />
          </Card>
        </div>
      </div>
    </div>
  );
}
