import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { followLiveUpdates } from "@/shared/api/live";

/** Which cached queries each live topic refreshes (backend: ModuleDefinition.live_topics). */
const TOPIC_QUERIES: Record<string, readonly string[][]> = {
  appointments: [["appointments"]],
  inbox: [["inbox"]],
  payments: [["payments"]],
  privacy: [["privacy"]],
};

/** While signed in: refetch exactly the areas that changed, the moment they change (§8.9). */
export function useLiveUpdates() {
  const queryClient = useQueryClient();
  useEffect(() => {
    const controller = new AbortController();
    void followLiveUpdates((topics) => {
      for (const topic of topics) {
        for (const queryKey of TOPIC_QUERIES[topic] ?? []) void queryClient.invalidateQueries({ queryKey });
      }
    }, controller.signal);
    return () => controller.abort();
  }, [queryClient]);
}
