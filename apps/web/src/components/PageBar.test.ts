import { describe, expect, it } from "vitest";

import { pageTitle } from "./PageBar";

describe("pageTitle", () => {
  it("names the place", () => {
    expect(pageTitle("inbox")).toBe("Início");
    expect(pageTitle("study")).toBe("Caderno");
    expect(pageTitle("settings")).toBe("Ajustes");
  });

  it("uses the conversation's title in the chat, when it has one", () => {
    expect(pageTitle("conversation", "Debounce na busca")).toBe("Debounce na busca");
    expect(pageTitle("conversation", null)).toBe("Chat");
    expect(pageTitle("conversation", "  ")).toBe("Chat");
    expect(pageTitle("projects", "Debounce na busca")).toBe("Projetos");
  });
});
