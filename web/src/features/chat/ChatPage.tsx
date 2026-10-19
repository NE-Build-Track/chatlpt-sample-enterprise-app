import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { continueMessage, sendMessage } from "@/api/chat";
import { conversationKeys, useConversation, useModel } from "@/api/conversations";
import type { Message } from "@/api/schemas";
import { HttpError } from "@/api/client";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Composer } from "./Composer";
import { MessageItem } from "./MessageItem";
import { formatMoney } from "@/features/usage/format";
import { ThinkingSelect } from "./ThinkingSelect";

type Live = { message: Message; content: string; reasoning: string };

export function ChatPage() {
  const { conversationId = "" } = useParams();
  const location = useLocation();
  const client = useQueryClient();
  const conversation = useConversation(conversationId);
  const model = useModel();
  const [live, setLive] = useState<Live | null>(null);
  const [finished, setFinished] = useState<Message[]>([]); // messages completed during the current run
  const [pendingUser, setPendingUser] = useState<Message | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const started = useRef(false);

  const run = useCallback(
    async (events: (signal: AbortSignal) => AsyncGenerator<import("@/api/schemas").ReplyEvent>) => {
      setError(null);
      const controller = new AbortController();
      abort.current = controller;
      try {
        for await (const event of events(controller.signal)) {
          if (event.type === "start" && event.message) {
            if (event.user_message) setPendingUser(event.user_message);
            setLive({ message: event.message, content: "", reasoning: "" });
          } else if (event.type === "tool_call" && event.message) {
            setLive((l) => (l ? { ...l, message: { ...l.message, kind: "tool_call", tool_calls: event.message!.tool_calls } } : l));
          } else if (event.type === "image" && event.image) {
            setLive((l) => (l ? { ...l, message: { ...l.message, images: [...l.message.images, event.image!] } } : l));
          } else if (event.type === "done" && event.message) {
            const done = event.message;
            setFinished((list) => [...list, done]);
            setLive(null);
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
          const detail = e instanceof Error ? e.message : String(e);
          setError(e instanceof HttpError ? e.message : `The reply could not be shown (${detail}). Reload the page; the reply was saved if it completed.`);
        }
      } finally {
        abort.current = null;
        setLive(null);
        setPendingUser(null);
        setFinished([]);
        await client.invalidateQueries({ queryKey: conversationKeys.one(conversationId) });
        await client.invalidateQueries({ queryKey: conversationKeys.all });
        await client.invalidateQueries({ queryKey: ["usage", "me"] });
      }
    },
    [client, conversationId],
  );

  const send = useCallback(
    (text: string) => {
      setFinished([]);
      setPendingUser({
        id: "pending-user",
        conversation_id: conversationId,
        role: "user",
        kind: "text",
        content: text,
        tool_calls: [],
        images: [],
        state: "complete",
        created_at: new Date().toISOString(),
      });
      return run((signal) => sendMessage(conversationId, text, signal));
    },
    [conversationId, run],
  );

  const continueFrom = useCallback(
    (message: Message) => run((signal) => continueMessage(conversationId, message.id, signal)),
    [conversationId, run],
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
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const busy = Boolean(live) || Boolean(pendingUser) || finished.length > 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {conversation.data && (
        <div className="flex justify-end px-4">
          <ThinkingSelect conversationId={conversationId} value={conversation.data.conversation.thinking} />
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto px-4">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 py-6">
          {messages
            .filter((m) => !(live && m.id === live.message.id))
            .map((m, index, all) => (
              <MessageItem
                key={m.id}
                message={m}
                attached={index > 0 && all[index - 1].role === "assistant" && all[index - 1].kind === "tool_call" && m.role === "assistant"}
                canContinue={!busy && lastAssistant?.id === m.id}
                onContinue={continueFrom}
              />
            ))}
          {pendingUser && !messages.some((m) => m.id === pendingUser.id) && <MessageItem message={pendingUser} />}
          {finished
            .filter((m) => !messages.some((x) => x.id === m.id))
            .map((m) => <MessageItem key={m.id} message={m} />)}
          {live && (
            <MessageItem
              streaming
              message={{ ...live.message, content: live.content, reasoning: live.reasoning || null, state: live.message.kind === "tool_call" ? live.message.state : "streaming" }}
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
        streaming={busy}
        disabled={model.data?.chat_available === false}
      />
    </div>
  );
}
