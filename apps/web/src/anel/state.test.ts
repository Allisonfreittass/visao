import { describe, expect, it } from "vitest";

import { anelEstado } from "./state";

describe("anelEstado", () => {
  it("shows what happens now before what waits", () => {
    expect(anelEstado({ state: "THINKING", approvals: 2, paused: true })).toBe("pensando");
    expect(anelEstado({ state: "LISTENING", approvals: 1 })).toBe("ouvindo");
    expect(anelEstado({ state: "INTERRUPTED" })).toBe("ouvindo");
    expect(anelEstado({ state: "SPEAKING" })).toBe("fala");
  });

  it("goes silent without the server, whatever waits", () => {
    expect(anelEstado({ state: "DISCONNECTED", approvals: 3, opening: true })).toBe("silencio");
  });

  it("at rest: Mac work, then a yes to give, then the pause, then an unread opening", () => {
    expect(anelEstado({ state: "IDLE", macWorking: true, approvals: 1 })).toBe("pensando");
    expect(anelEstado({ state: "IDLE", approvals: 1, paused: true })).toBe("aprovacao");
    expect(anelEstado({ state: "IDLE", paused: true, opening: true })).toBe("pausado");
    expect(anelEstado({ state: "IDLE", opening: true })).toBe("fala");
    expect(anelEstado({ state: "IDLE" })).toBe("ocioso");
  });
});
