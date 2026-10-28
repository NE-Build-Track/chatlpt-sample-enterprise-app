import type { Money, UsageTotals, WholesaleCost } from "@/api/schemas";

/** Format a decimal string as dollars with enough precision to show sub-cent network costs. */
export function formatMoney(money: Money | null | undefined, { compact = false } = {}): string {
  if (!money) return "–";
  const value = Number(money.amount);
  if (!Number.isFinite(value)) return `$${money.amount}`;
  if (value === 0) return "$0.00";
  const abs = Math.abs(value);
  const digits = abs >= 1 ? 2 : abs >= 0.01 ? 4 : compact ? 5 : 7;
  return `$${value.toFixed(digits)}`;
}

/** Everything the network charged in a period: delivered plus paid work that failed (D29). */
export function networkSpent(totals: UsageTotals): Money {
  const sum = Number(totals.wholesale.amount) + Number(totals.wholesale_failed.amount);
  return { amount: sum.toFixed(10), currency: "USD" };
}

export function formatTokens(count: number | null | undefined): string {
  if (count === null || count === undefined) return "–";
  return new Intl.NumberFormat().format(count);
}

export function describeWholesale(wholesale: WholesaleCost | null | undefined): { label: string; pending: boolean } {
  if (!wholesale || wholesale.status === "none") return { label: "no network charge", pending: false };
  if (wholesale.status === "pending") return { label: "network pending", pending: true };
  if (wholesale.status === "unknown") return { label: "network unknown", pending: false }; // never $0 (D29)
  const amount = formatMoney(wholesale.amount);
  if (wholesale.status === "delivered") {
    const failedOver = wholesale.failed ? ` · failed over ${formatMoney(wholesale.failed)}` : "";
    return { label: `network ${amount}${failedOver}`, pending: false };
  }
  if (wholesale.status === "uncertain") return { label: `network ${amount} (uncertain)`, pending: false };
  return { label: `network ${amount} (failed after payment)`, pending: false };
}
