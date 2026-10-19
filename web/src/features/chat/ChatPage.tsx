import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { sendMessage } from "@/api/chat";
import { conversationKeys, useConversation, useModel } from "@/api/conversations";
import type { Message } from "@/api/schemas";
import { HttpError } from "@/api/client";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Composer } from "./Composer";
import { MessageItem } from "./MessageItem";
import { formatMoney } from "@/features/usage/format";

type Live = { message: Message; content: string; reasoning: string };

export function ChatPage() {
  const { conversationId = "" } = useParams();
  const location = useLocation();
  const client = useQueryClient();
  const conversation = useConversation(conversationId);
  const model = useModel();
  const [live, setLive] = useState<Live | null>(null);
  const [pendingUser, setPendingUser] = useState<Message | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const started = useRef(false);

  const send = useCallback(
    async (text: string) => {
      setError(null);
      const controller = new AbortController();
      abort.current = controller;
      setPendingUser({
        id: "pending-user",
        conversation_id: conversationId,
        role: "user",
        content: text,
        state: "complete",
        created_at: new Date().toISOString(),
      });
      try {
        for await (const event of sendMessage(conversationId, text, controller.signal)) {
          if (event.type === "start" && event.message) {
            setPendingUser(event.user_message ?? null);
            setLive({ message: event.message, content: "", reasoning: "" });
          } else if (event.type === "content") {
            setLive((l) => (l ? { ...l, content: l.content + event.text } : l));
          } else if (event.type === "reasoning") {
            setLive((l) => (l ? { ...l, reasoning: l.reasoning + event.text } : l));
          } else if (event.type === "error") {
            setError(event.error ?? "the reply failed");
          }
        }
      } catch (e) {
        if (!(e instanceof DOMException && e.name === "AbortError")) {
          setError(e instanceof HttpError ? e.message : "the reply failed");
        }
      } finally {
        abort.current = null;
        setLive(null);
        setPendingUser(null);
        await client.invalidateQueries({ queryKey: conversationKeys.one(conversationId) });
        await client.invalidateQueries({ queryKey: conversationKeys.all });
        await client.invalidateQueries({ queryKey: ["usage", "me"] });
      }
    },
    [client, conversationId],
  );

  useEffect(() => {
    const initial = (location.state as { initialMessage?: string } | null)?.initialMessage;
    if (initial && !started.current && conversation.data) {
      started.current = true;
      window.history.replaceState({}, "");
      void send(initial);
    }
  }, [location.state, conversation.data, send]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [conversation.data?.messages.length, live?.content, live?.reasoning, pendingUser]);

  const messages = conversation.data?.messages ?? [];
  const totals = conversation.data?.totals;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-4">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 py-6">
          {messages
            .filter((m) => !(live && m.id === live.message.id))
            .map((m) => <MessageItem key={m.id} message={m} />)}
          {pendingUser && !messages.some((m) => m.id === pendingUser.id) && <MessageItem message={pendingUser} />}
          {live && (
            <MessageItem
              streaming
              message={{ ...live.message, content: live.content, reasoning: live.reasoning || null, state: "streaming" }}
            />
          )}
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <div ref={bottom} />
        </div>
      </div>
      {totals && totals.replies > 0 && (
        <p className="px-4 pb-1 text-center text-xs text-muted-foreground">
          Conversation · {totals.replies} replies · retail {formatMoney(totals.retail)} · network {formatMoney(totals.wholesale)}
          {totals.wholesale_pending > 0 ? ` (+${totals.wholesale_pending} pending)` : ""}
        </p>
      )}
      <Composer
        onSend={send}
        onStop={() => abort.current?.abort()}
        streaming={Boolean(live) || Boolean(pendingUser)}
        disabled={model.data?.chat_available === false}
      />
    </div>
  );
}
