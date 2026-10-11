import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/shared/api/client";
import { unwrap, unwrapEmpty } from "@/shared/api/call";

export const inboxKeys = {
  all: ["inbox"] as const,
  conversation: (contactId: string) => ["inbox", contactId] as const,
};

export function useConversations() {
  return useQuery({
    queryKey: inboxKeys.all,
    queryFn: () => unwrap(api.GET("/api/inbox")),
    refetchInterval: 60_000, // live updates (§8.9); polling is the fallback
  });
}

export function useConversation(contactId: string) {
  return useQuery({
    queryKey: inboxKeys.conversation(contactId),
    queryFn: () => unwrap(api.GET("/api/inbox/{contact_id}", { params: { path: { contact_id: contactId } } })),
    enabled: Boolean(contactId),
    refetchInterval: 60_000,
  });
}

type Action = { kind: "takeover" } | { kind: "handback" } | { kind: "reply"; text: string };

export function useInboxAction(contactId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (action: Action) => {
      const path = { params: { path: { contact_id: contactId } } };
      if (action.kind === "takeover") await unwrap(api.POST("/api/inbox/{contact_id}/takeover", path));
      else if (action.kind === "handback") await unwrapEmpty(api.POST("/api/inbox/{contact_id}/handback", path));
      else await unwrap(api.POST("/api/inbox/{contact_id}/reply", { ...path, body: { text: action.text } }));
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: inboxKeys.all }),
  });
}
