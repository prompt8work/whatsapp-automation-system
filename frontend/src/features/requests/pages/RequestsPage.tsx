import { useTimezone } from "@/features/clinic";
import { Empty, ErrorText, Loading } from "@/shared/ui/Feedback";
import { PageHeader } from "@/shared/ui/PageHeader";

import { useDecision, useRequests } from "../api/requests";
import { RequestCard } from "../components/RequestCard";
import { requestKind, sortQueue } from "../model/requests";

/** The approval queue (PRD AP-3.1/3.2): new bookings and reschedule requests. */
export function RequestsPage() {
  const requests = useRequests();
  const decide = useDecision();
  const timeZone = useTimezone();

  return (
    <div>
      <PageHeader title={`Requests${requests.data ? ` (${requests.data.length})` : ""}`} />
      <ErrorText error={requests.error ?? decide.error} />
      {requests.isLoading && <Loading />}
      {requests.data?.length === 0 && <Empty>No requests waiting. New ones appear here automatically.</Empty>}
      <div className="space-y-3">
        {sortQueue(requests.data ?? []).map((a) => {
          const reschedule = requestKind(a) === "reschedule";
          return (
            <RequestCard
              key={a.id}
              appointment={a}
              timeZone={timeZone}
              busy={decide.isPending}
              onApprove={() => decide.mutate({ kind: reschedule ? "approve-reschedule" : "approve", id: a.id })}
              onDecline={(reason) =>
                decide.mutate({ kind: reschedule ? "decline-reschedule" : "decline", id: a.id, reason })
              }
            />
          );
        })}
      </div>
    </div>
  );
}
