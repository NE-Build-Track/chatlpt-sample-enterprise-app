import { csrfHeaders, toError } from "./client";
import { ReplyEvent } from "./schemas";

/** POST a message and yield the server-sent reply events. Aborting the signal stops reading; the server
 *  keeps producing the paid reply and saves it. */
export function sendMessage(conversationId: string, content: string, signal: AbortSignal): AsyncGenerator<ReplyEvent> {
  return readEvents(`/api/conversations/${conversationId}/messages`, JSON.stringify({ content }), signal);
}

/** Continue a reply the runner cut off at the output limit; the events describe a new segment. */
export function continueMessage(conversationId: string, messageId: string, signal: AbortSignal): AsyncGenerator<ReplyEvent> {
  return readEvents(`/api/conversations/${conversationId}/messages/${messageId}/continue`, undefined, signal);
}

async function* readEvents(url: string, body: string | undefined, signal: AbortSignal): AsyncGenerator<ReplyEvent> {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/json", accept: "text/event-stream", ...csrfHeaders },
    body,
    signal,
  });
  if (!response.ok || !response.body) throw await toError(response);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index: number;
    while ((index = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, index);
      buffer = buffer.slice(index + 2);
      const event = parseFrame(frame);
      if (event) yield event;
    }
  }
}

export function parseFrame(frame: string): ReplyEvent | null {
  const data = frame
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
  if (!data) return null;
  return ReplyEvent.parse(JSON.parse(data));
}
