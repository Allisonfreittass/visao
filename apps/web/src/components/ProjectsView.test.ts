import { describe, expect, it } from "vitest";
import { projectSummary } from "./ProjectsView";

const base = { id: "p", name: "Viagem para o Chile", created_at: "2026-11-17T12:00:00Z", conversations: 1, pages: 0, files: 0 };

describe("projectSummary", () => {
  it("says what the project holds, for the card on top of its chat", () => {
    expect(projectSummary({ ...base, notes: "- a\n- b\n- c", panels: 1 })).toBe("3 anotações · 1 painel");
    expect(projectSummary({ ...base, notes: "- a", pages: 2, files: 1 })).toBe("1 anotação · 2 páginas · 1 arquivo");
    expect(projectSummary(base)).toBe("só o chat, por enquanto");
  });
});
