import { useMyUsage } from "@/api/conversations";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { formatMoney, formatTokens, networkSpent } from "./format";

// This month's usage: retail at list price vs. what the Livepeer network charged (D29).
export function UsageDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const usage = useMyUsage();
  const t = usage.data;
  const rows: [string, string][] = t
    ? [
        ["Replies", String(t.replies)],
        ["Images", String(t.images)],
        ["Tokens in / out", `${formatTokens(t.prompt_tokens)} / ${formatTokens(t.completion_tokens)}`],
        ["Retail (list price)", formatMoney(t.retail)],
        ["Network, delivered", formatMoney(t.wholesale)],
        ["Network, failed after payment", formatMoney(t.wholesale_failed)],
        ["Network, total", formatMoney(networkSpent(t))],
      ]
    : [];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Usage this month</DialogTitle>
          <DialogDescription>Retail is your tokens at the model vendor's list price. Network is what the Livepeer network charged.</DialogDescription>
        </DialogHeader>
        {!t ? (
          <p className="text-sm text-muted-foreground">{usage.isError ? "Usage is unavailable right now." : "Loading…"}</p>
        ) : (
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 text-sm">
            {rows.map(([label, value]) => (
              <div key={label} className="contents">
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="text-right tabular-nums">{value}</dd>
              </div>
            ))}
            {t.wholesale_pending > 0 && (
              <p className="col-span-2 pt-1 text-xs text-muted-foreground">
                {t.wholesale_pending} network {t.wholesale_pending === 1 ? "cost is" : "costs are"} still arriving.
              </p>
            )}
          </dl>
        )}
      </DialogContent>
    </Dialog>
  );
}
