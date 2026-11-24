import { describe, expect, it } from "vitest";
import { projectBlurb, projectCounts, projectSummary, sameName } from "./ProjectsView";

const base = { id: "p", name: "Viagem para o Chile", created_at: "2026-11-17T12:00:00Z", conversations: 1, pages: 0, files: 0 };

describe("projectSummary", () => {
  it("says what the project holds, for the card on top of its chat", () => {
    expect(projectSummary({ ...base, notes: "- a\n- b\n- c", panels: 1 })).toBe("3 anotações · 1 painel");
    expect(projectSummary({ ...base, notes: "- a", pages: 2, files: 1 })).toBe("1 anotação · 2 páginas · 1 arquivo");
    expect(projectSummary(base)).toBe("só o chat, por enquanto");
  });
});

describe("project cards", () => {
  it("uses his first note as the line under the name, and says when a panel is live", () => {
    expect(projectBlurb({ notes: "- Hotéis, voos e o roteiro de março\n- outra", panels: 1 })).toBe("Hotéis, voos e o roteiro de março. Tem um painel ativo.");
    expect(projectBlurb({ notes: "", panels: 2 })).toBe("Tem 2 painéis ativos.");
    expect(projectBlurb({ notes: undefined, panels: 0 })).toBe("Só o chat, por enquanto.");
  });

  it("counts conversations, pages and files", () => {
    expect(projectCounts({ conversations: 14, pages: 1, files: 0 })).toEqual(["14 conversas", "1 página", "0 arquivos"]);
  });
});

describe("one name, one project", () => {
  it("finds the project already called that, ignoring case, accents and spaces", () => {
    const list = [{ id: "1", name: "Viagem à Lisboa" }, { id: "2", name: "Estudos de Go" }];
    expect(sameName(list, "  viagem a   LISBOA ")?.id).toBe("1");
    expect(sameName(list, "Viagem")).toBeNull();
  });
});
