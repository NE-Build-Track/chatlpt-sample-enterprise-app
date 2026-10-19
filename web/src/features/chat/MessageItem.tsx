import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { ChevronDown, ChevronRight, Copy } from "lucide-react";
import type { Message } from "@/api/schemas";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { describeWholesale, formatMoney, formatTokens } from "@/features/usage/format";
import { cn } from "@/lib/utils";

export function MessageItem({ message, streaming = false }: { message: Message; streaming?: boolean }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl bg-muted px-4 py-2.5 text-sm">{message.content}</div>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {message.reasoning && <Thinking text={message.reasoning} streaming={streaming && !message.content} />}
      <div className={cn("prose prose-sm max-w-none dark:prose-invert prose-pre:bg-muted prose-pre:text-foreground", streaming && "animate-pulse-caret")}>
        {message.content ? (
          <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
            {message.content}
          </Markdown>
        ) : streaming ? (
          <p className="text-muted-foreground">Thinking…</p>
        ) : null}
      </div>
      {message.state === "failed" && <p className="text-sm text-destructive">This reply failed: {message.error ?? "unknown error"}</p>}
      {message.state === "uncertain" && (
        <p className="text-sm text-destructive">
          Payment went out but the reply did not arrive. The network cost, if any, will show here when it is known.
        </p>
      )}
      {message.state === "complete" && message.finish_reason === "length" && (
        <p className="text-sm text-muted-foreground">
          {message.content
            ? "This reply was cut off at the output limit."
            : `The model used its whole output budget while thinking${
                message.usage ? ` (${formatTokens(message.usage.completion_tokens)} tokens)` : ""
              } and produced no answer. Try again, or ask for a shorter answer.`}
        </p>
      )}
      {message.state === "complete" && <CostLine message={message} />}
    </div>
  );
}

function Thinking({ text, streaming }: { text: string; streaming: boolean }) {
  const [open, setOpen] = useState(streaming);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground">
        {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
        {streaming ? "Thinking…" : "Thinking"}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-1 whitespace-pre-wrap border-l-2 pl-3 text-xs text-muted-foreground">{text}</div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function CostLine({ message }: { message: Message }) {
  const usage = message.usage;
  const wholesale = describeWholesale(message.wholesale);
  const copy = () => void navigator.clipboard?.writeText(message.content);
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-default">
            {formatTokens(usage?.prompt_tokens)} in · {formatTokens(usage?.completion_tokens)} out
            {usage && usage.reasoning_tokens > 0 ? ` (${formatTokens(usage.reasoning_tokens)} reasoning)` : ""}
          </span>
        </TooltipTrigger>
        <TooltipContent>Tokens as the runner reported them.</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-default">retail {formatMoney(message.retail)}</span>
        </TooltipTrigger>
        <TooltipContent>What these tokens cost at Alibaba Cloud's list price for Qwen3.8-27B.</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className={cn("cursor-default", wholesale.pending && "animate-pulse")}>{wholesale.label}</span>
        </TooltipTrigger>
        <TooltipContent>
          What the Livepeer network charged for this reply{message.orchestrator_url ? ` (${message.orchestrator_url})` : ""}.
          {wholesale.pending ? " Arrives once the clearinghouse reports usage." : ""}
        </TooltipContent>
      </Tooltip>
      <button onClick={copy} aria-label="Copy reply" className="ml-auto rounded p-1 hover:bg-accent hover:text-foreground">
        <Copy className="size-3.5" />
      </button>
    </div>
  );
}
