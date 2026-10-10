import { Badge } from "@/shared/ui/Badge";

import { statusOf } from "../model/appointments";

export function StatusBadge({ status }: { status: string }) {
  const { label, tone } = statusOf(status);
  return <Badge tone={tone}>{label}</Badge>;
}
