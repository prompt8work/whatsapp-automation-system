import { useState, type FormEvent } from "react";

import { Button } from "@/shared/ui/Button";

type Props = { canSend: boolean; busy: boolean; onSend: (text: string) => void };

/** Free text only inside WhatsApp's 24 h window (PRD PL-5.4); after that templates only. */
export function ReplyBox({ canSend, busy, onSend }: Props) {
  const [text, setText] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    onSend(text.trim());
    setText("");
  }

  if (!canSend) {
    return (
      <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800">
        More than 24 hours since this person last wrote, so WhatsApp only allows approved templates. Wait for them
        to message again.
      </p>
    );
  }
  return (
    <form onSubmit={submit} className="flex gap-2">
      <textarea
        aria-label="Reply"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={2}
        className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
        placeholder="Write a reply… (sending takes the chat over from the bot)"
      />
      <Button type="submit" disabled={busy || !text.trim()}>
        Send
      </Button>
    </form>
  );
}
