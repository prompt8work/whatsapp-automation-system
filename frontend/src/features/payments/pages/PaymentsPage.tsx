import { useState } from "react";
import { Link } from "react-router";

import { useTimezone } from "@/features/clinic";
import { formatWhen } from "@/shared/lib/time";
import { Badge } from "@/shared/ui/Badge";
import { Select } from "@/shared/ui/Field";
import { Empty, ErrorText, Loading } from "@/shared/ui/Feedback";
import { PageHeader } from "@/shared/ui/PageHeader";

import { usePaymentAction, usePayments } from "../api/payments";
import { PaymentActions } from "../components/PaymentActions";
import { METHOD_LABEL, STATUS_TONE, money, type PaymentStatus } from "../model/payments";

/** Payments and the ledger (PRD §6.6, RT-7). Detached entries are kept after data deletion. */
export function PaymentsPage() {
  const [status, setStatus] = useState<PaymentStatus | "">("pending");
  const payments = usePayments(status);
  const act = usePaymentAction();
  const timeZone = useTimezone();

  return (
    <div>
      <PageHeader title="Payments">
        <Select value={status} onChange={(e) => setStatus(e.target.value as PaymentStatus | "")} className="w-40" aria-label="Status">
          <option value="pending">Pending</option>
          <option value="paid">Paid</option>
          <option value="refunded">Refunded</option>
          <option value="expired">Expired</option>
          <option value="failed">Failed</option>
          <option value="">All</option>
        </Select>
      </PageHeader>
      <ErrorText error={payments.error ?? act.error} />
      {payments.isLoading && <Loading />}
      {payments.data?.length === 0 && <Empty>No payments here.</Empty>}
      {payments.data && payments.data.length > 0 && (
        <table className="w-full overflow-hidden rounded-lg border border-slate-200 bg-white text-sm">
          <thead className="bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-3 py-2 font-medium">Receipt</th>
              <th className="px-3 py-2 font-medium">Payer</th>
              <th className="px-3 py-2 font-medium">For</th>
              <th className="px-3 py-2 font-medium">Amount</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {payments.data.map((p) => (
              <tr key={p.id} className="border-t border-slate-100 align-top">
                <td className="px-3 py-2">
                  <div className="font-mono">{p.receipt_number}</div>
                  <div className="text-xs text-slate-500">{formatWhen(p.paid_at ?? p.created_at, timeZone)}</div>
                </td>
                <td className="px-3 py-2">
                  <div>{p.payer_name}</div>
                  <div className="text-xs text-slate-500">{p.payer_phone}</div>
                </td>
                <td className="px-3 py-2">
                  {p.subject_id ? (
                    <Link to={`/appointments/${p.subject_id}`} className="hover:underline">
                      {p.purpose}
                    </Link>
                  ) : (
                    <span title="The appointment was deleted; the payment is kept">{p.purpose} (ledger)</span>
                  )}
                  <div className="text-xs text-slate-500">
                    {METHOD_LABEL[p.method]}
                    {p.note && ` · ${p.note}`}
                  </div>
                </td>
                <td className="px-3 py-2 font-medium">{money(p.amount_minor, p.currency)}</td>
                <td className="px-3 py-2">
                  <Badge tone={STATUS_TONE[p.status]}>{p.status}</Badge>
                </td>
                <td className="px-3 py-2">
                  <PaymentActions
                    payment={p}
                    busy={act.isPending}
                    onAction={(action, note) => act.mutate({ id: p.id, action, note })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
