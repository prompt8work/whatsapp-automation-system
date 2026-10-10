import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/shared/api/client";
import { unwrap } from "@/shared/api/call";

export const appointmentKeys = {
  all: ["appointments"] as const,
  day: (on: string, status: string) => ["appointments", "list", on, status] as const,
  detail: (id: string) => ["appointments", "detail", id] as const,
  slots: (doctorId: string, date: string) => ["appointments", "slots", doctorId, date] as const,
  doctors: ["doctors"] as const,
};

type Status = "requested" | "confirmed" | "rescheduled" | "declined" | "expired" | "cancelled" | "completed" | "no_show";

export function useAppointments(on: string, status: string) {
  return useQuery({
    queryKey: appointmentKeys.day(on, status),
    queryFn: () =>
      unwrap(
        api.GET("/api/appointments", {
          params: { query: { on, ...(status ? { status: [status as Status] } : {}) } },
        }),
      ),
    refetchInterval: 15_000,
  });
}

export function useAppointment(id: string) {
  return useQuery({
    queryKey: appointmentKeys.detail(id),
    queryFn: () => unwrap(api.GET("/api/appointments/{appointment_id}", { params: { path: { appointment_id: id } } })),
  });
}

export function useDoctors() {
  return useQuery({
    queryKey: appointmentKeys.doctors,
    queryFn: () => unwrap(api.GET("/api/doctors")),
  });
}

export function useSlots(doctorId: string, date: string) {
  return useQuery({
    queryKey: appointmentKeys.slots(doctorId, date),
    queryFn: () =>
      unwrap(api.GET("/api/doctors/{doctor_id}/slots", { params: { path: { doctor_id: doctorId }, query: { date } } })),
    enabled: Boolean(doctorId && date),
  });
}

type Action =
  | { kind: "cancel"; reason: string }
  | { kind: "attendance"; attended: boolean }
  | { kind: "reschedule"; start: string };

export function useAppointmentAction(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: Action) => {
      const path = { params: { path: { appointment_id: id } } };
      switch (action.kind) {
        case "cancel":
          return unwrap(api.POST("/api/appointments/{appointment_id}/cancel", { ...path, body: { reason: action.reason } }));
        case "attendance":
          return unwrap(
            api.POST("/api/appointments/{appointment_id}/attendance", { ...path, body: { attended: action.attended } }),
          );
        case "reschedule":
          return unwrap(
            api.POST("/api/appointments/{appointment_id}/reschedule", { ...path, body: { start: action.start } }),
          );
      }
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: appointmentKeys.all }),
  });
}

/** The patient's cases, newest first, with each one's scheduled deletion date (AP-10.6). */
export function usePatientCases(patientId: string) {
  return useQuery({
    queryKey: ["appointments", "cases", patientId] as const,
    queryFn: () =>
      unwrap(api.GET("/api/patients/{patient_id}/cases", { params: { path: { patient_id: patientId } } })),
    enabled: Boolean(patientId),
  });
}

export type CaseAction = { kind: "close"; note: string } | { kind: "reopen" } | { kind: "hold"; hold: boolean };

export function useCaseAction(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: CaseAction) => {
      const path = { params: { path: { case_id: caseId } } };
      switch (action.kind) {
        case "close":
          return unwrap(api.POST("/api/cases/{case_id}/close", { ...path, body: { note: action.note } }));
        case "reopen":
          return unwrap(api.POST("/api/cases/{case_id}/reopen", path));
        case "hold":
          return unwrap(api.PUT("/api/cases/{case_id}/legal-hold", { ...path, body: { hold: action.hold } }));
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
      void queryClient.invalidateQueries({ queryKey: ["privacy"] });
    },
  });
}
