import { useNavigate } from "react-router";
import { useCreateConversation, useModel } from "@/api/conversations";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Composer } from "./Composer";

const EXAMPLES = [
  "Explain how probabilistic micropayments work in two paragraphs.",
  "Write a Python function that parses server-sent events.",
  "Compare wholesale and retail pricing for an inference product.",
];

export function EmptyChat() {
  const navigate = useNavigate();
  const create = useCreateConversation();
  const model = useModel();

  async function start(text: string) {
    const c = await create.mutateAsync();
    navigate(`/c/${c.id}`, { state: { initialMessage: text } });
  }

  return (
    <div className="flex flex-1 flex-col">
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
              onClick={() => start(text)}
              className="rounded-xl border p-3 text-left text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              {text}
            </button>
          ))}
        </div>
      </div>
      <Composer disabled={create.isPending || model.data?.chat_available === false} onSend={start} />
    </div>
  );
}
