import { describe, expect, it } from "vitest";

import { money, paymentActions, type Payment } from "./payments";

const base = { status: "pending", method: "at_clinic" } as Payment;

describe("payments model", () => {
  it("formats rupees with Indian grouping", () => {
    expect(money(50000)).toBe("₹500");
    expect(money(123456789)).toBe("₹12,34,567.89");
  });

  it("offers Razorpay refunds only for paid Razorpay payments", () => {
    expect(paymentActions({ ...base, status: "paid", method: "razorpay_link" }).refund).toBe(true);
    expect(paymentActions({ ...base, status: "paid" }).refund).toBe(false);
    expect(paymentActions({ ...base, status: "paid" }).markRefunded).toBe(true);
  });

  it("lets staff record a late payment, but not pay twice", () => {
    expect(paymentActions({ ...base, status: "expired" }).markPaid).toBe(true);
    expect(paymentActions({ ...base, status: "paid" }).markPaid).toBe(false);
    expect(paymentActions(base).cancel).toBe(true);
  });
});
