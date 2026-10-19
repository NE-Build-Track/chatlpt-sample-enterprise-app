import { Link } from "react-router";
import { useAdminUsers, useSetDisabled } from "@/api/admin";
import { useMe } from "@/api/auth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatMoney, formatTokens } from "@/features/usage/format";

export function AdminPage() {
  const me = useMe();
  const users = useAdminUsers();
  const setDisabled = useSetDisabled();
  if (me.data && !me.data.is_admin) return <p className="p-6 text-sm">Admins only.</p>;

  const rows = users.data ?? [];
  const sum = (pick: (t: NonNullable<(typeof rows)[number]["totals"]>) => number) =>
    rows.reduce((acc, r) => acc + (r.totals ? pick(r.totals) : 0), 0);

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Admin · this month</h1>
          <p className="text-sm text-muted-foreground">Retail is tokens at list price. Network is what Livepeer charged. The gap is the margin.</p>
        </div>
        <Button variant="outline" asChild><Link to="/">Back to chat</Link></Button>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>User</TableHead>
            <TableHead className="text-right">Replies</TableHead>
            <TableHead className="text-right">Tokens in / out</TableHead>
            <TableHead className="text-right">Retail</TableHead>
            <TableHead className="text-right">Network</TableHead>
            <TableHead className="text-right">Margin</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map(({ user, totals }) => {
            const margin = totals ? Number(totals.retail.amount) - Number(totals.wholesale.amount) : null;
            return (
              <TableRow key={user.id} className={user.disabled ? "opacity-60" : undefined}>
                <TableCell>
                  <div className="font-medium">{user.display_name}</div>
                  <div className="text-xs text-muted-foreground">{user.email}</div>
                  <div className="mt-1 flex gap-1">
                    {user.is_admin && <Badge variant="secondary">admin</Badge>}
                    {user.disabled && <Badge variant="destructive">disabled</Badge>}
                  </div>
                </TableCell>
                <TableCell className="text-right">{totals?.replies ?? 0}</TableCell>
                <TableCell className="text-right">{formatTokens(totals?.prompt_tokens ?? 0)} / {formatTokens(totals?.completion_tokens ?? 0)}</TableCell>
                <TableCell className="text-right">{formatMoney(totals?.retail)}</TableCell>
                <TableCell className="text-right">
                  {formatMoney(totals?.wholesale)}
                  {totals && totals.wholesale_pending > 0 && <span className="text-xs text-muted-foreground"> +{totals.wholesale_pending} pending</span>}
                </TableCell>
                <TableCell className="text-right">{margin === null ? "–" : formatMoney({ amount: margin.toFixed(10), currency: "USD" })}</TableCell>
                <TableCell className="text-right">
                  {user.id !== me.data?.id && (
                    <Button size="sm" variant="outline" onClick={() => setDisabled.mutate({ id: user.id, disabled: !user.disabled })}>
                      {user.disabled ? "Enable" : "Disable"}
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
          <TableRow className="font-medium">
            <TableCell>Total</TableCell>
            <TableCell className="text-right">{sum((t) => t.replies)}</TableCell>
            <TableCell className="text-right">{formatTokens(sum((t) => t.prompt_tokens))} / {formatTokens(sum((t) => t.completion_tokens))}</TableCell>
            <TableCell className="text-right">{formatMoney({ amount: sum((t) => Number(t.retail.amount)).toFixed(10), currency: "USD" })}</TableCell>
            <TableCell className="text-right">{formatMoney({ amount: sum((t) => Number(t.wholesale.amount)).toFixed(10), currency: "USD" })}</TableCell>
            <TableCell className="text-right">{formatMoney({ amount: (sum((t) => Number(t.retail.amount)) - sum((t) => Number(t.wholesale.amount))).toFixed(10), currency: "USD" })}</TableCell>
            <TableCell />
          </TableRow>
        </TableBody>
      </Table>
    </div>
  );
}
