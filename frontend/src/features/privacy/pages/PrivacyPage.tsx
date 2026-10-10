import { usePermission } from "@/features/auth";
import { useTimezone } from "@/features/clinic";
import { formatDate, formatWhen } from "@/shared/lib/time";
import { Card } from "@/shared/ui/Card";
import { Empty, ErrorText, Loading } from "@/shared/ui/Feedback";
import { PageHeader } from "@/shared/ui/PageHeader";

import { useDeletionDecision, useDeletionRecords, useDeletionRequests, useUpcomingDeletions } from "../api/privacy";
import { DeletionRequestCard } from "../components/DeletionRequestCard";
import { describeCounts, ruleLabel, sortRequests } from "../model/privacy";

/** Data protection (PRD §7.10): patients' deletion requests, what retention deletes soon, and
 * the record of what was deleted. */
export function PrivacyPage() {
  const timeZone = useTimezone();
  const canDecide = usePermission("case.manage");
  const requests = useDeletionRequests(canDecide);
  const decide = useDeletionDecision();
  const upcoming = useUpcomingDeletions();
  const records = useDeletionRecords();

  return (
    <div className="space-y-6">
      <PageHeader title="Privacy" />

      {canDecide && (
        <section>
          <h2 className="mb-2 font-medium">Deletion requests</h2>
          <ErrorText error={requests.error ?? decide.error} />
          {requests.isLoading && <Loading />}
          {requests.data?.length === 0 && <Empty>No requests. Patients can ask on WhatsApp by typing DELETE MY DATA.</Empty>}
          <div className="space-y-3">
            {sortRequests(requests.data ?? []).map((r) => (
              <DeletionRequestCard
                key={r.id}
                request={r}
                timeZone={timeZone}
                busy={decide.isPending}
                onApprove={() => decide.mutate({ kind: "approve", id: r.id })}
                onReject={(reason) => decide.mutate({ kind: "reject", id: r.id, reason })}
              />
            ))}
          </div>
        </section>
      )}

      <Card title="Deleting in the next 7 days">
        <ErrorText error={upcoming.error} />
        {upcoming.data?.length === 0 && <p className="text-sm text-slate-500">Nothing due.</p>}
        <ul className="divide-y divide-slate-100 text-sm">
          {upcoming.data?.map((u) => (
            <li key={`${u.purger}:${u.subject_id}`} className="flex flex-wrap justify-between gap-2 py-2">
              <span>
                {u.label || (u.subject_type === "contact" ? "Unused WhatsApp contact" : u.subject_type)}
                <span className="ml-2 text-slate-500">{ruleLabel(u.rule)}</span>
              </span>
              <span className="text-slate-600">{formatDate(u.due_at, timeZone)}</span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-slate-500">To keep a case, reopen it or put it on legal hold from one of its appointments.</p>
      </Card>

      <Card title="Deletion record">
        <ErrorText error={records.error} />
        {records.isLoading && <Loading />}
        {records.data?.length === 0 && <p className="text-sm text-slate-500">Nothing deleted yet.</p>}
        <ul className="divide-y divide-slate-100 text-sm">
          {records.data?.map((r) => (
            <li key={r.id} className="flex flex-wrap justify-between gap-2 py-2">
              <span>
                {ruleLabel(r.rule)}: {describeCounts(r.counts)}
              </span>
              <span className="text-slate-500">{formatWhen(r.at, timeZone)}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
