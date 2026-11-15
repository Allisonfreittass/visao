import { describe, expect, it } from "vitest";

import { brl, checkedLabel } from "./PanelsBoard";

describe("panel card text", () => {
  it("writes money the Brazilian way, from the server's numbers", () => {
    expect(brl("5945.00")?.replace(/\s/g, " ")).toBe("R$ 5.945");
    expect(brl("4250.50")?.replace(/\s/g, " ")).toBe("R$ 4.250,50");
    expect(brl(null)).toBeNull();
  });

  it("never says a number from another day is from today", () => {
    expect(checkedLabel({ checked_at: null, checked_today: false })).toBe("ainda não conferido");
    expect(checkedLabel({ checked_at: "2026-11-13T12:14:00", checked_today: false })).toMatch(/^conferido em 13\/11, \d\d:\d\d · não conferido hoje$/);
    expect(checkedLabel({ checked_at: "2026-11-15T12:14:00", checked_today: true })).toMatch(/^conferido hoje, \d\d:\d\d$/);
  });
});
