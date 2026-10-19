import { describe, expect, it } from "vitest";
import { describeWholesale, formatMoney, formatTokens } from "./format";

describe("formatMoney", () => {
  it("shows sub-cent amounts with enough digits", () => {
    expect(formatMoney({ amount: "0.000111", currency: "USD" })).toBe("$0.0001110");
    expect(formatMoney({ amount: "0.0009", currency: "USD" })).toBe("$0.0009000");
    expect(formatMoney({ amount: "0.0123", currency: "USD" })).toBe("$0.0123");
    expect(formatMoney({ amount: "12.5", currency: "USD" })).toBe("$12.50");
    expect(formatMoney({ amount: "0", currency: "USD" })).toBe("$0.00");
    expect(formatMoney(null)).toBe("–");
  });
});

describe("describeWholesale", () => {
  it("never shows pending as zero", () => {
    expect(describeWholesale({ status: "pending" })).toEqual({ label: "network pending", pending: true });
    expect(describeWholesale({ status: "delivered", amount: { amount: "0.00003", currency: "USD" } }).label).toBe(
      "network $0.0000300",
    );
    expect(describeWholesale(null).label).toBe("no network charge");
  });
});

describe("formatTokens", () => {
  it("groups thousands", () => {
    expect(formatTokens(1204)).toBe("1,204");
  });
});
