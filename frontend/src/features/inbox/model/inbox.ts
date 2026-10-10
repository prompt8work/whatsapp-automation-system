import type { Schemas } from "@/shared/api/types";

export type ConversationSummary = Schemas["ConversationSummarySchema"];
export type Conversation = Schemas["ConversationSchema"];
export type Handover = Schemas["HandoverSchema"];

/** Who is handling the chat (PRD PL-5.2). */
export function handlerLabel(handover: Handover | null | undefined, myUserId: string | undefined): string {
  if (!handover) return "Bot";
  if (!handover.assigned_user_id) return "Waiting for staff";
  return handover.assigned_user_id === myUserId ? "You" : "Another staff member";
}

export function displayName(c: { profile_name: string | null; phone: string }): string {
  return c.profile_name ? `${c.profile_name} (${c.phone})` : c.phone;
}
