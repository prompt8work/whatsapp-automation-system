/**
 * The signed-in session (ARCHITECTURE §8.8).
 *
 * - The ACCESS token lives only in memory (this module) - never in localStorage, so a script
 *   injected into the page cannot steal a long-lived credential.
 * - The REFRESH token is an httpOnly cookie the browser sends to /api/auth/* automatically.
 *   On page load, and whenever the access token expires, we call /api/auth/refresh.
 *
 * React reads this store through `useSession()` (features/auth).
 */
import { env } from "@/shared/config/env";

import type { components } from "./schema";

export type Me = components["schemas"]["MeResponse"];
export type SessionResponse = components["schemas"]["SessionResponse"];

export type SessionState =
  | { status: "unknown" } // not checked yet (page just loaded)
  | { status: "anonymous" }
  | { status: "authenticated"; accessToken: string; me: Me };

let state: SessionState = { status: "unknown" };
const listeners = new Set<() => void>();

function emit(next: SessionState): void {
  state = next;
  listeners.forEach((listener) => listener());
}

export const sessionStore = {
  get: (): SessionState => state,
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  signIn(session: SessionResponse): void {
    emit({ status: "authenticated", accessToken: session.access_token, me: session.me });
  },
  signOut(): void {
    emit({ status: "anonymous" });
  },
  accessToken(): string | null {
    return state.status === "authenticated" ? state.accessToken : null;
  },
};

let inFlight: Promise<boolean> | null = null;

/**
 * Exchange the refresh cookie for a new session. Concurrent callers share one request
 * (several API calls failing with 401 at once must not rotate the token several times).
 * Pass `tenantId` to switch clinic.
 */
export function refreshSession(tenantId?: string): Promise<boolean> {
  if (inFlight && !tenantId) return inFlight;
  const request = (async () => {
    try {
      const response = await fetch(`${env.apiBaseUrl}/api/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(tenantId ? { tenant_id: tenantId } : {}),
      });
      if (!response.ok) {
        sessionStore.signOut();
        return false;
      }
      sessionStore.signIn((await response.json()) as SessionResponse);
      return true;
    } catch {
      sessionStore.signOut();
      return false;
    } finally {
      inFlight = null;
    }
  })();
  if (!tenantId) inFlight = request;
  return request;
}
