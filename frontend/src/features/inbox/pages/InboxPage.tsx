import { useNavigate, useParams } from "react-router";

import { usePermission, useSession } from "@/features/auth";
import { useTimezone } from "@/features/clinic";
import { Button } from "@/shared/ui/Button";
import { Empty, ErrorText, Loading } from "@/shared/ui/Feedback";
import { PageHeader } from "@/shared/ui/PageHeader";

import { useConversation, useConversations, useInboxAction } from "../api/inbox";
import { ConversationList } from "../components/ConversationList";
import { ReplyBox } from "../components/ReplyBox";
import { Thread } from "../components/Thread";
import { displayName, handlerLabel } from "../model/inbox";

/** Shared inbox (PRD §6.5): every WhatsApp conversation; take over, reply, hand back. */
export function InboxPage() {
  const { contactId } = useParams();
  const navigate = useNavigate();
  const timeZone = useTimezone();
  const session = useSession();
  const canReply = usePermission("inbox.reply");
  const conversations = useConversations();
  const conversation = useConversation(contactId ?? "");
  const act = useInboxAction(contactId ?? "");
  const me = session.status === "authenticated" ? session.me.user_id : undefined;
  const c = conversation.data;

  return (
    <div>
      <PageHeader title="Inbox" />
      <ErrorText error={conversations.error ?? act.error} />
      <div className="grid gap-4 md:grid-cols-[20rem_1fr]">
        <div>
          {conversations.isLoading && <Loading />}
          {conversations.data?.length === 0 && <Empty>No conversations yet.</Empty>}
          {!!conversations.data?.length && (
            <ConversationList
              items={conversations.data}
              selected={contactId}
              onSelect={(id) => navigate(`/inbox/${id}`)}
            />
          )}
        </div>
        <div>
          {!contactId && <Empty>Choose a conversation.</Empty>}
          {contactId && conversation.isLoading && <Loading />}
          {c && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-medium">{displayName(c.contact)}</p>
                  <p className="text-xs text-slate-500">Handled by: {handlerLabel(c.handover, me)}</p>
                </div>
                {canReply && (
                  <div className="flex gap-2">
                    {(!c.handover || c.handover.assigned_user_id !== me) && (
                      <Button variant="ghost" className="border border-slate-200" disabled={act.isPending} onClick={() => act.mutate({ kind: "takeover" })}>
                        Take over
                      </Button>
                    )}
                    {c.handover && (
                      <Button variant="ghost" className="border border-slate-200" disabled={act.isPending} onClick={() => act.mutate({ kind: "handback" })}>
                        Hand back to bot
                      </Button>
                    )}
                  </div>
                )}
              </div>
              <Thread messages={c.messages} timeZone={timeZone} />
              {canReply && (
                <ReplyBox
                  canSend={c.can_send_text}
                  busy={act.isPending}
                  onSend={(text) => act.mutate({ kind: "reply", text })}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
