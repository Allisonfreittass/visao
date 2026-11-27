import { describe, expect, it } from "vitest";

import { turnAnnouncement } from "./turn-announcements";

describe("turn announcements", () => {
  it("announces discrete conversation states", () => {
    expect(turnAnnouncement({ type: "start" })).toBe("Visão começou a responder.");
    expect(turnAnnouncement({ type: "tool", label: "Procurando no seu Gmail" })).toBe("Usando uma ferramenta: Procurando no seu Gmail.");
    expect(turnAnnouncement({ type: "complete" })).toBe("Resposta concluída.");
    expect(turnAnnouncement({ type: "cancel" })).toBe("Resposta interrompida.");
  });
});
