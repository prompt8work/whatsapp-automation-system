import { relative } from "@/shared/lib/time";
import { Badge } from "@/shared/ui/Badge";

import { displayName, type ConversationSummary } from "../model/inbox";

type Props = { items: ConversationSummary[]; selected: string | undefined; onSelect: (contactId: string) => void };

export function ConversationList({ items, selected, onSelect }: Props) {
  return (
    <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
      {items.map((c) => (
        <li key={c.contact.id}>
          <button
            type="button"
            onClick={() => onSelect(c.contact.id)}
            className={`block w-full px-3 py-2 text-left hover:bg-slate-50 ${selected === c.contact.id ? "bg-slate-100" : ""}`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-sm font-medium">{displayName(c.contact)}</span>
              <span className="shrink-0 text-xs text-slate-400">{relative(c.last_message.created_at)}</span>
            </div>
            <div className="mt-0.5 flex items-center gap-2">
              {c.handover && <Badge tone={c.handover.assigned_user_id ? "info" : "warn"}>{c.handover.assigned_user_id ? "Staff" : "Needs staff"}</Badge>}
              <span className={`truncate text-xs ${c.awaiting_reply ? "font-medium text-slate-800" : "text-slate-500"}`}>
                {c.last_message.direction === "outbound" ? "↪ " : ""}
                {c.last_message.text}
              </span>
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}
