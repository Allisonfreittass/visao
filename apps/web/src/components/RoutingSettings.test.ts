import { describe, expect, it } from "vitest";

import { routingNote } from "./RoutingSettings";

const three = ["Claude", "OpenAI", "Gemini"];

describe("Ajustes > Escolha do provedor says the order each task gets", () => {
  it("keeps the configured order in the fixed mode", () => {
    expect(routingNote({ mode: "fixa", configured: three, personal: three, public: three })).toBe(
      "Sempre Claude, OpenAI, Gemini, nessa ordem. Passa para o próximo só se um falhar.",
    );
  });

  it("names both orders per task", () => {
    const note = routingNote({
      mode: "por_tarefa",
      configured: three,
      personal: three,
      public: ["Gemini", "Claude", "OpenAI"],
    });
    expect(note).toMatch(/algo seu vão primeiro em Claude, OpenAI, Gemini\./);
    expect(note).toMatch(/só com texto público, vai primeiro em Gemini, Claude, OpenAI\./);
  });

  it("says the switch changes nothing with a single provider", () => {
    expect(routingNote({ mode: "por_tarefa", configured: ["Claude"], personal: ["Claude"], public: ["Claude"] })).toMatch(
      /^Só o Claude está configurado/,
    );
  });
});
