import { describe, expect, it } from "vitest";

import {
  AMBER_SHARE,
  CENTER,
  DESENHOS,
  FADE_MS,
  FERRAMENTAS,
  type Forma,
  HOLD_MS,
  MORPH_MS,
  agendaInicial,
  amostrar,
  ambar,
  formaDoPasso,
  mulberry32,
  particleCount,
  pedir,
  proximaTroca,
  voo,
} from "./nanorrobos";

describe("the shape a step asks for", () => {
  it("is the tool of a real kind", () => {
    expect(formaDoPasso({ label: "Procurando no seu Gmail", kind: "gmail" }, "corvo")).toBe("gmail");
    expect(formaDoPasso({ label: "Olhando sua agenda", kind: "agenda" }, "gmail")).toBe("agenda");
    expect(formaDoPasso({ label: "Pesquisando “voos”", kind: "pesquisa" }, "corvo")).toBe("pesquisa");
    expect(formaDoPasso({ label: "Abrindo github.com", kind: "site" }, "corvo")).toBe("site");
    expect(formaDoPasso({ label: "Montando o pedido ao Mac", kind: "mac" }, "corvo")).toBe("mac");
    expect(formaDoPasso({ label: "Lendo notas.md", kind: "arquivo" }, "corvo")).toBe("arquivo");
  });

  it("does not change without a kind, nor with one it does not know", () => {
    expect(formaDoPasso({ label: "Montando seu painel", kind: null }, "site")).toBe("site");
    expect(formaDoPasso({ label: "Conferindo a resposta" }, "pesquisa")).toBe("pesquisa");
    expect(formaDoPasso({ label: "Fazendo café", kind: "cafeteira" }, "gmail")).toBe("gmail");
  });

  it("goes back to the crow on Pensando, Escrevendo a resposta and the end of the turn", () => {
    expect(formaDoPasso({ label: "Pensando", kind: null }, "gmail")).toBe("corvo");
    expect(formaDoPasso({ label: "Escrevendo a resposta" }, "site")).toBe("corvo");
    expect(formaDoPasso(null, "arquivo")).toBe("corvo");
  });
});

describe("each shape stays at least 1.2 s", () => {
  it("a call opens with the crow and the first tool shows at once", () => {
    const a = pedir(agendaInicial(), "gmail", 1000);
    expect(a).toEqual({ forma: "gmail", pronta: 1000 + MORPH_MS, pendente: null });
  });

  it("the next shape waits until the current one has been formed for 1.2 s", () => {
    let a = pedir(agendaInicial(), "gmail", 0);
    a = pedir(a, "pesquisa", MORPH_MS + HOLD_MS - 1);
    expect(a.forma).toBe("gmail");
    expect(proximaTroca(a)).toBe(MORPH_MS + HOLD_MS);
    a = pedir(a, a.pendente as Forma, MORPH_MS + HOLD_MS);
    expect(a.forma).toBe("pesquisa");
    expect(a.pendente).toBeNull();
  });

  it("quick steps in between go straight to the last one", () => {
    let a = pedir(agendaInicial(), "gmail", 0);
    a = pedir(a, "pesquisa", 300);
    a = pedir(a, "site", 600);
    a = pedir(a, "arquivo", 900);
    expect(a.forma).toBe("gmail");
    expect(a.pendente).toBe("arquivo");
  });

  it("asking again for the shape on screen drops what was waiting", () => {
    let a = pedir(agendaInicial(), "gmail", 0);
    a = pedir(a, "site", 100);
    a = pedir(a, "gmail", 200);
    expect(a.pendente).toBeNull();
    expect(proximaTroca(a)).toBeNull();
  });

  it("goes back to the crow after the tool had its time", () => {
    let a = pedir(agendaInicial(), "site", 0);
    a = pedir(a, "corvo", 500); // "Escrevendo a resposta" right after
    expect(a.forma).toBe("site");
    a = pedir(a, "corvo", proximaTroca(a) as number);
    expect(a).toMatchObject({ forma: "corvo", pendente: null });
  });

  it("with reduced motion the shape is formed after the 200 ms fade", () => {
    let a = pedir(agendaInicial(), "agenda", 0, FADE_MS);
    a = pedir(a, "corvo", FADE_MS + HOLD_MS, FADE_MS);
    expect(a.forma).toBe("corvo");
  });
});

describe("the particles", () => {
  it("are 3000, or 2000 under 400 px wide", () => {
    expect(particleCount(390)).toBe(2000);
    expect(particleCount(400)).toBe(3000);
  });

  it("2.5 % are amber, the same in every shape", () => {
    const marks = ambar(3000, mulberry32(1));
    expect(marks.reduce((s, v) => s + v, 0)).toBe(Math.round(3000 * AMBER_SHARE));
  });

  it("every shape is sampled into the same number of points, sorted by angle round the centre", () => {
    for (const f of FERRAMENTAS) {
      const pts = amostrar(DESENHOS[f], 500, mulberry32(3));
      expect(pts.length).toBe(1000);
      const angles = Array.from({ length: 500 }, (_, i) => Math.atan2(pts[i * 2 + 1] - CENTER, pts[i * 2] - CENTER));
      expect(angles.every((a, i) => i === 0 || a >= angles[i - 1])).toBe(true);
      // Centred in the ring, inside it.
      for (let i = 0; i < 500; i++) expect(Math.hypot(pts[i * 2] - CENTER, pts[i * 2 + 1] - CENTER)).toBeLessThan(440);
    }
  });

  it("fly eased from start to end with a sideways curve that is gone at both ends", () => {
    expect(voo(0, 0, 100, 0, 0, 1)).toEqual([0, 0]);
    const [x1, y1] = voo(0, 0, 100, 0, 1, 1);
    expect(x1).toBeCloseTo(100);
    expect(y1).toBeCloseTo(0);
    const [xm, ym] = voo(0, 0, 100, 0, 0.5, 1);
    expect(xm).toBeCloseTo(50);
    expect(ym).toBeCloseTo(22); // sin(π/2) × 0.22 × 1 × 100
    expect(voo(0, 0, 100, 0, 0.5, -0.5)[1]).toBeCloseTo(-11);
  });
});
