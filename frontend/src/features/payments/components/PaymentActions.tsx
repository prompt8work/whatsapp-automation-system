import { Button } from "@/shared/ui/Button";

import { paymentActions, type Payment, type PaymentAction } from "../model/payments";

type Props = { payment: Payment; busy: boolean; onAction: (action: PaymentAction, note: string) => void };

/** Staff actions on one payment. Each asks for a short note (e.g. "cash") or a confirmation. */
export function PaymentActions({ payment, busy, onAction }: Props) {
  const can = paymentActions(payment);
  const ask = (action: PaymentAction, question: string) => {
    const note = window.prompt(question);
    if (note !== null) onAction(action, note);
  };
  return (
    <div className="flex flex-wrap gap-1">
      {can.markPaid && (
        <Button variant="ghost" className="border border-slate-200" disabled={busy} onClick={() => ask("mark-paid", "Mark as paid. Note (e.g. cash, UPI at counter):")}>
          Mark paid
        </Button>
      )}
      {can.refund && (
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() => window.confirm("Refund the full amount through Razorpay?") && onAction("refund", "")}
        >
          Refund
        </Button>
      )}
      {can.markRefunded && !can.refund && (
        <Button variant="ghost" disabled={busy} onClick={() => ask("mark-refunded", "Refunded outside the system. Note:")}>
          Mark refunded
        </Button>
      )}
      {can.cancel && (
        <Button variant="ghost" disabled={busy} onClick={() => window.confirm("Cancel this payment request? Nothing will be due.") && onAction("cancel", "")}>
          Cancel request
        </Button>
      )}
    </div>
  );
}
