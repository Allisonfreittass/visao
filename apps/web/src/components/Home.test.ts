import { describe, expect, it } from "vitest";

import type { PanelItem } from "../api";
import { stepSensor } from "./ChatView";
import { ago, homeSuggestions, statusLine, thoughtWhen, watchCount } from "./InboxView";
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
    expect(statusLine({ online: true, macOnline: true, pendingCount: 0, panels: [{ status: "active", items: [item("flight", null), item("hotel", "164")] }] }))
      .toBe("Acompanhando 1\u00a0painel · Mac conectado · 1 voo aguardando preço");
    expect(statusLine({ online: true, macOnline: false, pendingCount: 2, panels: null })).toBe("2 pedidos esperando você · Sem conexão com o Mac");
    expect(statusLine({ online: true, macOnline: null, pendingCount: 0, panels: null })).toBe("");
  });

  it("suggests from what is there", () => {
    const open = () => undefined;
    const withFlight = homeSuggestions([{ title: "Chile", items: [item("flight", null)] }], { id: "p", name: "Chile" }, open);
    expect(withFlight.map((s) => s.label)).toEqual(["Relatório do dia", "Acompanhar preço dos voos", "Abrir projeto Chile"]);
    expect(homeSuggestions(null, null, open).map((s) => s.label)).toEqual(["Relatório do dia", "Acompanhar um preço", "Pedir ao Mac"]);
  });

  it("shows what is already known on a panel", () => {
    expect(panelKnown({ total: null, items: [] })).toEqual({ amount: "—", tag: "Faltam dados", missingData: true, sub: null });
    const partial = panelKnown({ total: null, items: [item("hotel", "164"), item("flight", null)] });
    expect(partial.amount).toMatch(/164 parcial$/);
    expect(partial.tag).toBe("Falta voo");
    expect(partial.sub).toBe("total parcial: 1 de 2 itens cotados, falta cotar voo");
    expect(panelKnown({ total: "500", items: [item("hotel", "500")] }).tag).toBeNull();
  });

  it("never shows one item's price as the package total (Pacote Santiago)", () => {
    // Only the hotel came back; the flight is not even in the list. The server says what is missing.
    const santiago = panelKnown({ total: null, items: [item("hotel", "1640")], partial: "1640.00", missing: ["flight"] });
    expect(santiago.amount.replace(/\s/g, " ")).toBe("R$ 1.640 parcial");
    expect(santiago.tag).toBe("Falta voo");
    expect(santiago.sub).toBe("total parcial: 1 de 2 itens cotados, falta cotar voo");
  });

  it("puts the right sensor on a step", () => {
    expect(stepSensor("Abrindo o Finder no Mac")).toBe("mac");
    expect(stepSensor("Procurando no seu Gmail")).toBe("email");
    expect(stepSensor("Olhando sua agenda")).toBe("caderno");
    expect(stepSensor("Pesquisando “voos”")).toBe("projeto");
  });

  it("dates his thought and the requests", () => {
    const now = new Date(2026, 10, 24, 10, 0);
    expect(thoughtWhen(new Date(2026, 10, 24, 8, 45), now)).toBe("Pensado hoje, 08:45");
    expect(thoughtWhen(new Date(2026, 10, 23, 22, 10), now)).toBe("Pensado ontem, 22:10");
    expect(thoughtWhen(new Date(2026, 10, 12, 9, 0), now)).toBe("Pensado em 12/11, 09:00");
    expect(ago(new Date(2026, 10, 24, 9, 35), now)).toBe("há 25 min");
    expect(ago(new Date(2026, 10, 24, 7, 0), now)).toBe("há 3 h");
    expect(ago(new Date(2026, 10, 22, 10, 0), now)).toBe("há 2 dias");
  });
});
