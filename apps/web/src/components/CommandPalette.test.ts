import { describe, expect, it } from "vitest";

import { filterItems, fold, type PaletteItem } from "./CommandPalette";

const item = (label: string, keywords?: string): PaletteItem => ({ id: label, label, icon: "home", group: "Ações", keywords, run: () => undefined });

describe("palette search", () => {
  it("ignores case and accents", () => {
    expect(fold("Início")).toBe("inicio");
    expect(filterItems([item("Ir para o Início"), item("Rotinas")], "INICIO").map((i) => i.label)).toEqual(["Ir para o Início"]);
  });

  it("needs every word, in the label or the keywords", () => {
    const items = [item("Canais", "telegram whatsapp"), item("Caderno", "memória")];
    expect(filterItems(items, "tele").map((i) => i.label)).toEqual(["Canais"]);
    expect(filterItems(items, "ca memo").map((i) => i.label)).toEqual(["Caderno"]);
    expect(filterItems(items, "")).toHaveLength(2);
  });
});
