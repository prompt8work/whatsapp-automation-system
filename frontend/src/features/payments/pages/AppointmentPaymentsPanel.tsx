import { usePermission } from "@/features/auth";
import { Badge } from "@/shared/ui/Badge";
import { Card } from "@/shared/ui/Card";
import { ErrorText } from "@/shared/ui/Feedback";

import { usePaymentAction, useSubjectPayments } from "../api/payments";
import { PaymentActions } from "../components/PaymentActions";
import { METHOD_LABEL, STATUS_TONE, money } from "../model/payments";

/** The payment of one appointment, on its detail page (PRD AP-5.3). Hidden when there is none. */
export function AppointmentPaymentsPanel({ appointmentId }: { appointmentId: string }) {
  const canRead = usePermission("payment.read");
  const canMark = usePermission("payment.mark");
  const payments = useSubjectPayments(appointmentId, canRead);
  const act = usePaymentAction();
  if (!payments.data?.length) return null;

  return (
    <Card title="Payment">
      <ErrorText error={act.error} />
      <ul className="space-y-3 text-sm">
        {payments.data.map((p) => (
          <li key={p.id} className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{money(p.amount_minor, p.currency)}</span>
              <Badge tone={STATUS_TONE[p.status]}>{p.status}</Badge>
              <span className="text-slate-500">
                {METHOD_LABEL[p.method]} · {p.receipt_number}
              </span>
            </div>
            {canMark && (
              <PaymentActions payment={p} busy={act.isPending} onAction={(action, note) => act.mutate({ id: p.id, action, note })} />
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
