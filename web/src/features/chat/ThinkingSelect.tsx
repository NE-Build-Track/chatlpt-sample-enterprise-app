import { Brain } from "lucide-react";
import type { ThinkingLevel } from "@/api/schemas";
import { useSetThinking } from "@/api/conversations";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";

const LEVELS: { value: ThinkingLevel; label: string; hint: string }[] = [
  { value: "off", label: "Off", hint: "Answer directly, no chain of thought" },
  { value: "low", label: "Low", hint: "A short think first" },
  { value: "medium", label: "Medium", hint: "The default" },
  { value: "high", label: "High", hint: "Think at length; slower and longer" },
];

export function ThinkingSelect({ conversationId, value }: { conversationId: string; value: ThinkingLevel }) {
  const set = useSetThinking();
  const current = LEVELS.find((l) => l.value === value) ?? LEVELS[2];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground" title="How much the model thinks before answering">
          <Brain className="size-4" /> Thinking: {current.label}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        {LEVELS.map((level) => (
          <DropdownMenuItem key={level.value} onClick={() => set.mutate({ id: conversationId, thinking: level.value })}>
            <div>
              <div className="text-sm">{level.label}{level.value === value ? " ✓" : ""}</div>
              <div className="text-xs text-muted-foreground">{level.hint}</div>
            </div>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
