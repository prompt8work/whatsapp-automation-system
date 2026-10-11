import type { Schemas } from "@/shared/api/types";
import type { BadgeTone } from "@/shared/ui/Badge";

export type Payment = Schemas["PaymentResponse"];
export type PaymentStatus = Payment["status"];
export type PaymentMethod = Payment["method"];
export type PaymentSettings = Schemas["PaymentSettingsSchema"];
export type PaymentAction = "mark-paid" | "mark-refunded" | "cancel" | "refund";

/** 50000 paise -> "₹500"; Indian digit grouping (₹12,34,567.89). */
export function money(amountMinor: number, currency = "INR"): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    minimumFractionDigits: amountMinor % 100 ? 2 : 0,
  }).format(amountMinor / 100);
}

export const METHOD_LABEL: Record<PaymentMethod, string> = {
  whatsapp_pay: "WhatsApp Pay",
  razorpay_link: "Razorpay link",
  at_clinic: "At clinic",
};

export const STATUS_TONE: Record<PaymentStatus, BadgeTone> = {
  pending: "warn",
  paid: "good",
  failed: "bad",
  expired: "neutral",
  refunded: "info",
};

/** What staff may do with a payment right now (PRD PL-6.4, PL-6.5). */
export function paymentActions(p: Payment) {
  return {
    markPaid: p.status !== "paid" && p.status !== "refunded",
    cancel: p.status === "pending",
    refund: p.status === "paid" && p.method === "razorpay_link",
    markRefunded: p.status === "paid",
  };
}
