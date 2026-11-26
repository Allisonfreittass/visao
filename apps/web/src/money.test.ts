import { describe, expect, it } from "vitest";

import { moneyWords } from "./api";

describe("moneyWords", () => {
  it("says a payment the way the card and the confirmation show it", () => {
    expect(moneyWords({ amount: "1234.5", currency: "BRL", to: "Ana" })).toBe("BRL 1.234,50 para Ana");
    expect(moneyWords({ amount: "50.00", currency: "USD", to: "" })).toBe("USD 50,00");
  });
});
