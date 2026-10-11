import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/shared/api/client";
import { unwrap, unwrapEmpty } from "@/shared/api/call";
import type { Schemas } from "@/shared/api/types";

import type { BookingRules, WorkingHours } from "../model/settings";

const keys = {
  locations: ["settings", "locations"] as const,
  rules: ["settings", "booking-rules"] as const,
  members: ["settings", "members"] as const,
  doctors: ["doctors"] as const,
};

export function useLocations() {
  return useQuery({ queryKey: keys.locations, queryFn: () => unwrap(api.GET("/api/locations")) });
}

export function useBookingRules() {
  return useQuery({ queryKey: keys.rules, queryFn: () => unwrap(api.GET("/api/appointments/settings")) });
}

export function useMembers() {
  return useQuery({ queryKey: keys.members, queryFn: () => unwrap(api.GET("/api/users")) });
}

function useSave<T>(fn: (input: T) => Promise<unknown>, invalidate: readonly string[]) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: invalidate }),
  });
}

export const useAddLocation = () =>
  useSave((body: Schemas["LocationRequest"]) => unwrap(api.POST("/api/locations", { body })), keys.locations);

export const useAddDoctor = () =>
  useSave((body: Schemas["AddDoctorRequest"]) => unwrap(api.POST("/api/doctors", { body })), keys.doctors);

export const useUpdateDoctor = () =>
  useSave(
    ({ id, body }: { id: string; body: Schemas["UpdateDoctorRequest"] }) =>
      unwrap(api.PATCH("/api/doctors/{doctor_id}", { params: { path: { doctor_id: id } }, body })),
    keys.doctors,
  );

export const useSetHours = () =>
  useSave(
    ({ id, hours }: { id: string; hours: WorkingHours[] }) =>
      unwrap(api.PUT("/api/doctors/{doctor_id}/working-hours", { params: { path: { doctor_id: id } }, body: hours })),
    keys.doctors,
  );

export const useSaveBookingRules = () =>
  useSave((body: BookingRules) => unwrap(api.PUT("/api/appointments/settings", { body })), keys.rules);

export const useAddMember = () =>
  useSave((body: Schemas["AddMemberRequest"]) => unwrap(api.POST("/api/users", { body })), keys.members);

const templateKeys = ["settings", "templates"] as const;

/** Template slots and the clinic's approved template for each (PRD PL-4.2). */
export function useTemplates(enabled = true) {
  return useQuery({ queryKey: templateKeys, queryFn: () => unwrap(api.GET("/api/templates")), enabled });
}

export const useMapTemplate = () =>
  useSave(
    ({ slot, ...body }: { slot: string; template_name: string; language: string }) =>
      unwrapEmpty(api.PUT("/api/templates/{slot}", { params: { path: { slot } }, body })),
    templateKeys,
  );
