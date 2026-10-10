import { useEffect, useRef } from "react";

import { formatWhen } from "@/shared/lib/time";

import type { Conversation } from "../model/inbox";

/** The chat as the patient saw it, oldest first. */
export function Thread({ messages, timeZone }: { messages: Conversation["messages"]; timeZone: string }) {
  const box = useRef<HTMLDivElement>(null);
  const newest = messages.at(-1)?.id;
  useEffect(() => {
    box.current?.scrollTo({ top: box.current.scrollHeight }); // newest message in view
  }, [newest]);
  return (
    <div ref={box} className="flex max-h-[60vh] flex-col gap-2 overflow-y-auto rounded-lg bg-slate-100 p-3">
      {messages.map((m) => (
        <div key={m.id} className={`flex ${m.direction === "outbound" ? "justify-end" : "justify-start"}`}>
          <div
            className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm shadow-sm ${
              m.direction === "outbound" ? "bg-emerald-50" : "bg-white"
            }`}
          >
            {m.text}
            <div className="mt-1 text-right text-[10px] text-slate-400">
              {formatWhen(m.created_at, timeZone)}
              {m.direction === "outbound" && ` · ${m.status}`}
              {m.error && <span className="text-rose-500"> · {m.error}</span>}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
