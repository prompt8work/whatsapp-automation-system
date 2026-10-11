import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/shared/api/client";
import { unwrap, unwrapEmpty } from "@/shared/api/call";

import type { PaymentAction, PaymentSettings, PaymentStatus } from "../model/payments";

export const paymentKeys = {
  all: ["payments"] as const,
  list: (status: string) => ["payments", "list", status] as const,
  forSubject: (id: string) => ["payments", "subject", id] as const,
  settings: ["payments", "settings"] as const,
};

export function usePayments(status: PaymentStatus | "") {
  return useQuery({
    queryKey: paymentKeys.list(status),
    queryFn: () => unwrap(api.GET("/api/payments", { params: { query: status ? { status } : {} } })),
    refetchInterval: 60_000,
  });
}

/** Payments of one appointment (usually one). */
export function useSubjectPayments(appointmentId: string, enabled = true) {
  return useQuery({
    queryKey: paymentKeys.forSubject(appointmentId),
    queryFn: () => unwrap(api.GET("/api/payments", { params: { query: { subject_id: [appointmentId] } } })),
    enabled: enabled && Boolean(appointmentId),
    refetchInterval: 60_000,
  });
}

export function usePaymentAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action, note = "" }: { id: string; action: PaymentAction; note?: string }) => {
      const args = { params: { path: { payment_id: id } }, body: { note } };
      switch (action) {
        case "mark-paid":
          return unwrap(api.POST("/api/payments/{payment_id}/mark-paid", args));
        case "mark-refunded":
          return unwrap(api.POST("/api/payments/{payment_id}/mark-refunded", args));
        case "cancel":
          return unwrap(api.POST("/api/payments/{payment_id}/cancel", args));
        case "refund":
          return unwrap(api.POST("/api/payments/{payment_id}/refund", args));
      }
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: paymentKeys.all }),
  });
}

export function usePaymentSettings(enabled = true) {
  return useQuery({
    queryKey: paymentKeys.settings,
    queryFn: () => unwrap(api.GET("/api/payments/settings")),
    enabled,
  });
}

export function useSavePaymentSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PaymentSettings) => unwrapEmpty(api.PUT("/api/payments/settings", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: paymentKeys.settings }),
  });
}

export function useSaveRazorpaySecrets() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { key_secret: string; webhook_secret: string }) =>
      unwrapEmpty(api.PUT("/api/payments/settings/razorpay-secrets", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: paymentKeys.settings }),
  });
}
