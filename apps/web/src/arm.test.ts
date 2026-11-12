import { describe, expect, it } from "vitest";

import { parseMacCommand } from "./arm";

describe("parseMacCommand", () => {
  it("splits the project from a multi-line request", () => {
    expect(parseMacCommand("/mac visao rode os testes\ne me diga o que falhou")).toEqual({
      project: "visao",
      prompt: "rode os testes\ne me diga o que falhou",
    });
  });

  it("asks for usage when something is missing and ignores normal messages", () => {
    expect(parseMacCommand("/mac")).toBe("usage");
    expect(parseMacCommand("/mac visao")).toBe("usage");
    expect(parseMacCommand("me ajuda no mac")).toBeNull();
    expect(parseMacCommand("/macarrão é bom")).toBeNull();
  });
});
