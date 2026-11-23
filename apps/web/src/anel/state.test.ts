import { describe, expect, it } from "vitest";

import { anelEstado, anelForma } from "./state";

describe("anelEstado", () => {
  it("without the server the ring is silent, whatever else is true", () => {
    expect(anelEstado({ state: "DISCONNECTED" })).toBe("silencio");
    expect(anelEstado({ state: "DISCONNECTED", macWorking: true, approvals: 3, paused: true, opening: true })).toBe("silencio");
  });

  it("what happens now wins over what waits", () => {
    const waiting = { approvals: 2, paused: true, opening: true, macWorking: true };
    expect(anelEstado({ state: "THINKING", ...waiting })).toBe("pensando");
    expect(anelEstado({ state: "LISTENING", ...waiting })).toBe("ouvindo");
    expect(anelEstado({ state: "INTERRUPTED", ...waiting })).toBe("ouvindo");
  });

  it("his voice playing is the listening wave, never 'fala'", () => {
    expect(anelEstado({ state: "SPEAKING" })).toBe("ouvindo");
    expect(anelEstado({ state: "SPEAKING", opening: true })).toBe("ouvindo");
  });

  it("at rest the order is Mac, then a yes to give, then the pause, then an unread opening", () => {
    expect(anelEstado({ state: "IDLE", macWorking: true, approvals: 1, paused: true, opening: true })).toBe("pensando");
    expect(anelEstado({ state: "IDLE", approvals: 1, paused: true, opening: true })).toBe("aprovacao");
    expect(anelEstado({ state: "IDLE", paused: true, opening: true })).toBe("pausado");
    expect(anelEstado({ state: "IDLE", opening: true })).toBe("fala");
    expect(anelEstado({ state: "IDLE" })).toBe("ocioso");
  });

  it("'fala' is only an opening not read yet", () => {
    expect(anelEstado({ state: "IDLE", opening: false })).toBe("ocioso");
    expect(anelEstado({ state: "IDLE", approvals: 0, opening: true })).toBe("fala");
  });
});

describe("anelForma", () => {
  it("below 32 px: the thin circle, no dim marks", () => {
    expect(anelForma(18)).toBe("mini");
    expect(anelForma(31)).toBe("mini");
  });

  it("from 32 to 120 px: the ring alone", () => {
    expect(anelForma(32)).toBe("anel");
    expect(anelForma(96)).toBe("anel");
    expect(anelForma(120)).toBe("anel");
  });

  it("above 120 px: Muninn inside the ring", () => {
    expect(anelForma(121)).toBe("muninn");
    expect(anelForma(220)).toBe("muninn");
  });
});
