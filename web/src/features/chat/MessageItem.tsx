import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { ChevronDown, ChevronRight, Copy } from "lucide-react";
import type { GeneratedImage, Message } from "@/api/schemas";
import { Download } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { describeWholesale, formatMoney, formatTokens } from "@/features/usage/format";
import { cn } from "@/lib/utils";

export function MessageItem({
  message,
  streaming = false,
  onContinue,
  canContinue = false,
  attached = false,
}: {
  message: Message;
  streaming?: boolean;
  onContinue?: (message: Message) => void;
  canContinue?: boolean;
  attached?: boolean;
}) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl bg-muted px-4 py-2.5 text-sm">{message.content}</div>
      </div>
    );
  }
  const continuation = Boolean(message.continues_message_id) || attached;
  if (message.kind === "tool_call") {
    return <ImageBlock message={message} streaming={streaming} />;
  }
  return (
    <div className={cn("space-y-2", continuation && "-mt-4")}>
      {message.dropped_turns ? (
        <p className="text-xs text-muted-foreground">
          {message.dropped_turns} earlier {message.dropped_turns === 1 ? "message was" : "messages were"} left out so this reply fits the model's context.
        </p>
      ) : null}
      {message.reasoning && <Thinking text={message.reasoning} streaming={streaming && !message.content} />}
      <div className={cn("prose prose-sm max-w-none dark:prose-invert prose-pre:bg-muted prose-pre:text-foreground", streaming && "animate-pulse-caret")}>
        {message.content ? (
          <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]} components={{ img: SafeImage }}>
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
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>
            {message.content
              ? "This reply was cut off at the output limit."
              : `The model used its whole output budget while thinking${
                  message.usage ? ` (${formatTokens(message.usage.completion_tokens)} tokens)` : ""
                } and produced no answer. Try again, or ask for a shorter answer.`}
          </span>
          {canContinue && message.content && onContinue && (
            <button onClick={() => onContinue(message)} className="rounded-md border px-2 py-1 text-xs hover:bg-accent">
              Continue generating
            </button>
          )}
        </div>
      )}
      {message.state === "complete" && <CostLine message={message} />}
    </div>
  );
}

function ImageBlock({ message, streaming }: { message: Message; streaming: boolean }) {
  const prompts = message.tool_calls.map((c) => String(c.arguments.prompt ?? ""));
  return (
    <div className="space-y-2">
      {message.reasoning && <Thinking text={message.reasoning} streaming={streaming && message.images.length === 0} />}
      {message.images.length === 0 && message.state !== "failed" && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="inline-block size-2 animate-pulse rounded-full bg-muted-foreground" />
          Generating image{prompts[0] ? `: ${prompts[0].slice(0, 80)}${prompts[0].length > 80 ? "…" : ""}` : "…"}
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        {message.images.map((image) => (
          <ImageCard key={image.id} image={image} />
        ))}
      </div>
      {message.state === "failed" && <p className="text-sm text-destructive">The image could not be generated: {message.error ?? "unknown error"}</p>}
      {message.state === "uncertain" && <p className="text-sm text-destructive">Payment went out but the image did not arrive.</p>}
    </div>
  );
}

function ImageCard({ image }: { image: GeneratedImage }) {
  const src = `/api/images/${image.id}`;
  const wholesale = describeWholesale(image.wholesale);
  const portrait = image.height > image.width;
  return (
    <figure className={cn("overflow-hidden rounded-xl border bg-muted", portrait ? "w-72" : "w-96 max-w-full")}>
      {image.expired ? (
        <div className="flex aspect-[4/3] items-center justify-center text-sm text-muted-foreground">This image has expired.</div>
      ) : (
        <img src={src} alt={image.prompt} width={image.width} height={image.height} className="block h-auto w-full" loading="lazy" />
      )}
      <figcaption className="flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground">
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="min-w-0 flex-1 cursor-default break-words">{image.width}×{image.height} · retail {formatMoney(image.retail)} · {wholesale.label}</span>
          </TooltipTrigger>
          <TooltipContent className="max-w-sm">
            <p className="mb-1 font-medium">Prompt</p>
            <p>{image.prompt}</p>
            {image.seed !== null && image.seed !== undefined && <p className="mt-1">Seed {image.seed}</p>}
          </TooltipContent>
        </Tooltip>
        {!image.expired && (
          <a href={src} download={`chatlpt-${image.id}.${image.content_type === "image/png" ? "png" : "jpg"}`} className="rounded p-1 hover:bg-accent hover:text-foreground" aria-label="Download image">
            <Download className="size-3.5" />
          </a>
        )}
      </figcaption>
    </figure>
  );
}

/** Only images the app serves are rendered; a model-invented URL becomes its alt text instead of a broken picture. */
function SafeImage({ src, alt }: { src?: string | Blob; alt?: string }) {
  const url = typeof src === "string" ? src : "";
  if (url.startsWith("/api/images/")) return <img src={url} alt={alt ?? ""} className="rounded-lg" />;
  return alt ? <em>{alt}</em> : null;
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
