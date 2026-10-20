import { useNavigate } from "react-router";
import { useCreateConversation, useModel } from "@/api/conversations";
import { Composer } from "./Composer";
import { Welcome } from "./Welcome";

// "/" and "New chat": the conversation is created with the first message, so an abandoned new chat
// leaves nothing behind in the sidebar.
export function EmptyChat() {
  const navigate = useNavigate();
  const create = useCreateConversation();
  const model = useModel();

  async function start(text: string) {
    const c = await create.mutateAsync();
    navigate(`/c/${c.id}`, { state: { initialMessage: text } });
  }

  const unavailable = create.isPending || model.data?.chat_available === false;
  return (
    <div className="flex flex-1 flex-col">
      <Welcome onPick={start} disabled={unavailable} />
      <Composer disabled={unavailable} onSend={start} />
    </div>
  );
}
