import { useModel } from "@/api/conversations";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

const EXAMPLES = [
  "Explain how probabilistic micropayments work in two paragraphs.",
  "Write a Python function that parses server-sent events.",
  "Draw a watercolor lighthouse at sunset.",
];

// The empty state of a chat: shown on the home page and in a conversation with no messages yet.
export function Welcome({ onPick, disabled = false }: { onPick: (text: string) => void; disabled?: boolean }) {
  const model = useModel();
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 px-4">
      <div className="text-center">
        <h1 className="text-2xl font-semibold tracking-tight">What can I help with?</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {model.data?.model?.model_id ?? "Qwen3.8-27B"} running on the Livepeer network
          {model.data?.model ? ` · ${new Intl.NumberFormat().format(model.data.model.max_model_len)} token context` : ""}
        </p>
      </div>
      {model.data && !model.data.chat_available && (
        <Alert variant="destructive" className="max-w-xl">
          <AlertTitle>Chat is unavailable</AlertTitle>
          <AlertDescription>{model.data.reason ?? "The model is not available right now."}</AlertDescription>
        </Alert>
      )}
      <div className="grid w-full max-w-2xl gap-2 sm:grid-cols-3">
        {EXAMPLES.map((text) => (
          <button
            key={text}
            disabled={disabled}
            onClick={() => onPick(text)}
            className="rounded-xl border p-3 text-left text-sm text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}
