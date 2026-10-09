/**
 * api/: session hooks. Components and pages use these, never the store or fetch directly.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";

import { api, ApiError } from "@/shared/api/client";
import { refreshSession, sessionStore, type SessionState } from "@/shared/api/session";

import { can, type LoginInput } from "../model/session";

export function useSession(): SessionState {
  return useSyncExternalStore(sessionStore.subscribe, sessionStore.get, sessionStore.get);
}

/** On first render, turn the refresh cookie (if any) into a session. */
export function useRestoreSession(): SessionState {
  const session = useSession();
  useEffect(() => {
    if (session.status === "unknown") void refreshSession();
  }, [session.status]);
  return session;
}

export function usePermission(permission: string): boolean {
  const session = useSession();
  return session.status === "authenticated" && can(session.me, permission);
}

export function useLogin() {
  return useMutation({
    mutationFn: async (input: LoginInput) => {
      const { data, error, response } = await api.POST("/api/auth/login", { body: input });
      if (!data) throw ApiError.from(response.status, error);
      sessionStore.signIn(data);
      return data.me;
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await api.POST("/api/auth/logout");
    },
    onSettled: () => {
      sessionStore.signOut();
      queryClient.clear(); // never show the previous user's cached data
    },
  });
}

export function useSwitchTenant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (tenantId: string) => {
      if (!(await refreshSession(tenantId))) throw new Error("Could not switch clinic");
    },
    onSuccess: () => queryClient.clear(), // every cached list belonged to the old clinic
  });
}
