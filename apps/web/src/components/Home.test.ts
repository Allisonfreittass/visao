import { describe, expect, it } from "vitest";

import type { PanelItem } from "../api";
import { stepSensor } from "./ChatView";
import { homeSuggestions, statusLine, watchCount } from "./InboxView";
import { panelKnown } from "./PanelsBoard";

const item = (kind: "flight" | "hotel", cost: string | null) => ({ kind, cost }) as PanelItem;

describe("Início", () => {
  it("counts the panels it watches, with a non-breaking space", () => {
    expect(watchCount(null)).toBeNull();
    expect(watchCount([{ status: "paused" }])).toBeNull();
    expect(watchCount([{ status: "active" }])).toBe("1 painel");
    expect(watchCount([{ status: "active" }, { status: "active" }])).toBe("2 painéis");
  });

  it("builds the status line from real data", () => {
    expect(statusLine({ online: false, macOnline: true, pendingCount: 0, panels: [] })).toBe("Sem conexão com o servidor.");
    expect(statusLine({ online: true, macOnline: true, pendingCount: 0, panels: [{ items: [item("flight", null), item("hotel", "164")] }] }))
      .toBe("Mac conectado · 1 voo aguardando preço");
    expect(statusLine({ online: true, macOnline: false, pendingCount: 2, panels: null })).toBe("Sem conexão com o Mac · 2 pedidos esperando você");
    expect(statusLine({ online: true, macOnline: null, pendingCount: 0, panels: null })).toBe("");
  });

  it("suggests from what is there", () => {
    const open = () => undefined;
    const withFlight = homeSuggestions([{ title: "Chile", items: [item("flight", null)] }], { id: "p", name: "Chile" }, open);
    expect(withFlight.map((s) => s.label)).toEqual(["Relatório do dia", "Acompanhar preço dos voos", "Abrir projeto Chile"]);
    expect(homeSuggestions(null, null, open).map((s) => s.label)).toEqual(["Relatório do dia", "Acompanhar um preço", "Pedir ao Mac"]);
  });

  it("shows what is already known on a panel", () => {
    expect(panelKnown({ total: null, items: [] })).toEqual({ amount: "—", tag: "Faltam dados", missingData: true });
    const partial = panelKnown({ total: null, items: [item("hotel", "164"), item("flight", null)] });
    expect(partial.amount).toMatch(/164 \+ voo$/);
    expect(partial.tag).toBe("Voo a confirmar");
    expect(panelKnown({ total: "500", items: [item("hotel", "500")] }).tag).toBeNull();
  });

  it("puts the right sensor on a step", () => {
    expect(stepSensor("Abrindo o Finder no Mac")).toBe("mac");
    expect(stepSensor("Procurando no seu Gmail")).toBe("email");
    expect(stepSensor("Olhando sua agenda")).toBe("caderno");
    expect(stepSensor("Pesquisando “voos”")).toBe("projeto");
  });
});
