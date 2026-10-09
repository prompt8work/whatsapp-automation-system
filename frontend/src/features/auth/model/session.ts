/** model/: pure rules about the signed-in user. No React, no fetching. */
import { z } from "zod";

import type { Me } from "@/shared/api/session";

export type { Me };

export const loginSchema = z.object({
  email: z.email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});
export type LoginInput = z.infer<typeof loginSchema>;

/**
 * UI-only check to hide buttons the user cannot use. The backend ALWAYS re-checks;
 * never rely on this for security.
 */
export function can(me: Me | null | undefined, permission: string): boolean {
  return !!me && me.permissions.includes(permission);
}

export function activeTenantName(me: Me): string | null {
  return me.memberships.find((m) => m.tenant_id === me.active_tenant_id)?.tenant_name ?? null;
}

const ROLE_LABEL: Record<string, string> = { admin: "Admin", staff: "Staff", doctor: "Doctor" };

export function roleLabel(role: string | null | undefined): string {
  return role ? (ROLE_LABEL[role] ?? role) : "Platform operator";
}

const LOGIN_ERRORS: Record<string, string> = {
  "identity.invalid_credentials": "Wrong email or password.",
  "identity.not_a_member": "You do not have access to that clinic.",
};

export function loginErrorMessage(code: string | undefined): string {
  return (code && LOGIN_ERRORS[code]) || "Could not sign in. Please try again.";
}
