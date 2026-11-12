import { describe, expect, it } from "vitest";

import { dayLabel } from "./labels";

describe("dayLabel", () => {
  const now = new Date(2026, 10, 12, 15, 0);
  it("names today and yesterday", () => {
    expect(dayLabel(new Date(2026, 10, 12, 11, 33), now)).toBe("Hoje, 11:33");
    expect(dayLabel(new Date(2026, 10, 11, 23, 5), now)).toBe("Ontem, 23:05");
  });
  it("shows day and month this year, the full date otherwise", () => {
    expect(dayLabel(new Date(2026, 10, 3, 9, 12), now)).toBe("03/11, 09:12");
    expect(dayLabel(new Date(2025, 11, 31, 9, 12), now)).toBe("31/12/2025, 09:12");
  });
});
