import { describe, expect, it } from "vitest";

import type { AppCatalogItem, ToolAction } from "./api";
import { argumentLines, cardText, searchCatalog, spokenApp } from "./apps";

const action: ToolAction = {
  id: "a1",
  toolkit: "github",
  tool: "GITHUB_CREATE_AN_ISSUE",
  version: "20251111_00",
  summary: "GitHub: Create an issue",
  app: "GitHub",
  tool_name: "Create an issue",
  description: "Creates an issue.",
  arguments: { owner: "dono", repo: "visao", title: "Erro no login", body: "Passo 1\nPasso 2", labels: ["bug"] },
  status: "proposed",
  result: "",
  conversation_id: "c1",
  created_at: "2026-11-25T12:00:00",
};

describe("the app change card", () => {
  it("shows every argument in full, one per line", () => {
    const text = argumentLines(action.arguments);
    expect(text).toContain("title: Erro no login");
    expect(text).toContain("body: Passo 1\nPasso 2");
    expect(text).toContain("labels: bug");
    expect(argumentLines({ page: { id: "p1" } })).toBe('page: {"id":"p1"}');
    expect(argumentLines({})).toBe("(sem argumentos)");
  });

  it("names the tool once, the app being the card's label", () => {
    expect(cardText(action)).toBe("Create an issue: Creates an issue.");
    expect(cardText({ ...action, description: "" })).toBe("Create an issue");
  });

  it("reads the change aloud before a spoken yes", () => {
    const spoken = spokenApp(action);
    expect(spoken.question).toContain("Preparei uma mudança no GitHub: Create an issue (Creates an issue.)");
    expect(spoken.question).toContain('"pode fazer"');
    expect(spoken.done).toBe("Pronto, fiz no GitHub.");
  });
});

describe("the catalog search", () => {
  const item = (slug: string, name: string, categories: string[] = []): AppCatalogItem => ({
    slug, name, description: "", logo: "", categories, managed: true,
  });
  const catalog = [item("github", "GitHub", ["Developer Tools"]), item("notion", "Notion", ["Produtividade"]), item("slack", "Slack")];

  it("finds by name, slug or category, ignoring accents", () => {
    expect(searchCatalog(catalog, "not").map((a) => a.slug)).toEqual(["notion"]);
    expect(searchCatalog(catalog, "developer").map((a) => a.slug)).toEqual(["github"]);
    expect(searchCatalog(catalog, "produtividáde").map((a) => a.slug)).toEqual(["notion"]);
    expect(searchCatalog(catalog, "")).toHaveLength(3);
    expect(searchCatalog(catalog, "", 2)).toHaveLength(2);
  });
});
