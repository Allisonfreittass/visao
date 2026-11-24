import { describe, expect, it } from "vitest";

import { DEFAULT_THEME, parseTheme, THEME_COLOR, THEMES } from "./theme";

describe("parseTheme", () => {
  it("keeps the three themes", () => {
    expect(parseTheme("papel")).toBe("papel");
    expect(parseTheme("tinta")).toBe("tinta");
    expect(parseTheme("rotulo")).toBe("rotulo");
  });

  it("carries the old choices over", () => {
    expect(parseTheme("dark")).toBe("tinta");
    expect(parseTheme("light")).toBe("papel");
    expect(parseTheme("system")).toBe(DEFAULT_THEME);
  });

  it("falls back to Papel when nothing is saved", () => {
    expect(parseTheme(null)).toBe("papel");
    expect(parseTheme("qualquer")).toBe("papel");
  });

  it("has a bar color and a label for every theme", () => {
    for (const t of THEMES) expect(THEME_COLOR[t.value]).toMatch(/^#[0-9A-F]{6}$/);
  });
});
