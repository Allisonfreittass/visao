import { describe, expect, it } from "vitest";

import type { QuoteTable } from "../api";
import { assumedLine, tableBubble } from "./QuoteTable";

const table: QuoteTable = {
  version: 1,
  title: "Santiago, 10 noites em agosto de 2027",
  travelers: 2,
  rows: [{ option: "JetSMART + Hostel", dates: "14–24 ago", total: "3300.00", total_text: "R$ 3.300", currency: "BRL", sites: ["google.com"] }],
  notes: ["Fica de fora do total: bagagem de mão (JetSMART)."],
  assumed: { origem: "Guarulhos (GRU)", pessoas: "2 adultos" },
  text: "Santiago · 2 pessoas\n1. JetSMART + Hostel · 14–24 ago · R$ 3.300",
};

describe("quote table", () => {
  it("draws the table in place of the bubble that holds its text", () => {
    expect(tableBubble(["Considerei GRU.", table.text], table)).toBe(1);
    expect(tableBubble(["Sem tabela."], table)).toBe(-1);
    expect(tableBubble(["x", table.text], null)).toBe(-1);
  });

  it("says what was assumed in one line, or nothing", () => {
    expect(assumedLine(table.assumed)).toBe("Considerando: Guarulhos (GRU) · 2 adultos");
    expect(assumedLine({})).toBe("");
    expect(assumedLine(undefined)).toBe("");
  });
});
