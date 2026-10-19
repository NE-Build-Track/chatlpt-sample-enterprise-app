import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export function Composer({
  onSend,
  onStop,
  streaming = false,
  disabled = false,
  autoFocus = true,
}: {
  onSend: (text: string) => void | Promise<void>;
  onStop?: () => void;
  streaming?: boolean;
  disabled?: boolean;
  autoFocus?: boolean;
}) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [text]);

  function submit() {
    const value = text.trim();
    if (!value || disabled || streaming) return;
    setText("");
    void onSend(value);
  }

  function onKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="px-4 pb-4">
      <div className="mx-auto flex w-full max-w-3xl items-end gap-2 rounded-2xl border bg-card p-2 shadow-sm focus-within:ring-1 focus-within:ring-ring">
        <Textarea
          ref={ref}
          rows={1}
          autoFocus={autoFocus}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          placeholder={disabled ? "Chat is unavailable" : "Message ChatLPT"}
          aria-label="Message"
          disabled={disabled}
          className="min-h-10 max-h-60 flex-1 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
        />
        {streaming ? (
          <Button size="icon" variant="secondary" aria-label="Stop" onClick={onStop}>
            <Square className="size-4" />
          </Button>
        ) : (
          <Button size="icon" aria-label="Send" onClick={submit} disabled={disabled || !text.trim()}>
            <ArrowUp className="size-4" />
          </Button>
        )}
      </div>
      <p className="mx-auto mt-2 max-w-3xl text-center text-xs text-muted-foreground">
        Enter to send, Shift+Enter for a new line. Every reply is paid on the Livepeer network.
      </p>
    </div>
  );
}
