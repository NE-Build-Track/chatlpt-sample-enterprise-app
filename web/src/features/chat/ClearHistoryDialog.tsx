import { useState } from "react";
import { useNavigate } from "react-router";
import { useClearHistory } from "@/api/conversations";
import { HttpError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

type Choice = { label: string; olderThanDays: number | null };
const CHOICES: Choice[] = [
  { label: "Older than 30 days", olderThanDays: 30 },
  { label: "Older than 90 days", olderThanDays: 90 },
  { label: "All chats", olderThanDays: null },
];

// Clear history: chats not touched in 30 or 90 days, or all of them. Usage records are kept.
export function ClearHistoryDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [choice, setChoice] = useState<Choice>(CHOICES[0]);
  const [result, setResult] = useState<string | null>(null);
  const clear = useClearHistory();
  const navigate = useNavigate();

  async function confirm() {
    setResult(null);
    try {
      const { deleted } = await clear.mutateAsync(choice.olderThanDays);
      setResult(deleted === 0 ? "Nothing to delete." : `Deleted ${deleted} ${deleted === 1 ? "chat" : "chats"}.`);
      if (deleted > 0) navigate("/");
    } catch (e) {
      setResult(e instanceof HttpError ? e.message : "Deleting failed; try again.");
    }
  }

  function change(next: boolean) {
    if (!next) setResult(null);
    onOpenChange(next);
  }

  return (
    <Dialog open={open} onOpenChange={change}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete chats</DialogTitle>
          <DialogDescription>Deleted chats cannot be recovered. Your usage records are kept.</DialogDescription>
        </DialogHeader>
        <div role="radiogroup" className="grid gap-2">
          {CHOICES.map((c) => (
            <button
              key={c.label}
              role="radio"
              aria-checked={choice === c}
              onClick={() => setChoice(c)}
              className={cn(
                "rounded-lg border px-3 py-2 text-left text-sm hover:bg-accent",
                choice === c && "border-foreground font-medium",
              )}
            >
              {c.label}
            </button>
          ))}
        </div>
        {result && <p role="status" className="text-sm text-muted-foreground">{result}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={() => change(false)}>Close</Button>
          <Button variant="destructive" onClick={() => void confirm()} disabled={clear.isPending}>
            Delete {choice.olderThanDays === null ? "all chats" : `chats older than ${choice.olderThanDays} days`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
