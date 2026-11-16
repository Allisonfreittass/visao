import { describe, expect, it } from "vitest";

import { conversationLabel, dividerDay, dividers } from "./labels";

const now = new Date(2026, 10, 16, 15, 0);
const at = (iso: string) => new Date(iso);

describe("continuous conversation", () => {
  it("names the days of the dividers", () => {
    expect(dividerDay(new Date(2026, 10, 16, 9), now)).toBe("Hoje");
    expect(dividerDay(new Date(2026, 10, 15, 22), now)).toBe("Ontem");
    expect(dividerDay(new Date(2026, 10, 10, 9), now)).toBe("10/11");
  });

  it("puts a divider at each new day and at each stretch's start, with its subject", () => {
    const messages = [
      { id: "a", created_at: new Date(2026, 10, 15, 10).toISOString() },
      { id: "b", created_at: new Date(2026, 10, 15, 10, 5).toISOString() },
      { id: "c", created_at: new Date(2026, 10, 16, 9).toISOString() },
      { id: "d", created_at: new Date(2026, 10, 16, 14).toISOString() },
    ];
    const segments = [
      { first_message_id: "a", title: "Viagem a Santiago", status: "summarized" },
      { first_message_id: "d", title: "", status: "failed" },
    ];
    const found = dividers(messages, segments, at, now);
    expect([...found.entries()]).toEqual([
      ["a", "Viagem a Santiago · Ontem"],
      ["c", "Hoje"],
    ]);
  });

  it("calls the continuous one Conversa in the menu", () => {
    const created_at = new Date(2026, 10, 1).toISOString();
    expect(conversationLabel({ continuous: true, title: "Algo", created_at }, at)).toBe("Conversa");
    expect(conversationLabel({ title: "Bug no login", created_at }, at)).toBe("Bug no login");
  });
});
