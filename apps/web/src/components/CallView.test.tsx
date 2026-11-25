import { renderToStaticMarkup } from "react-dom/server";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import { CallView } from "./CallView";

const base = {
  agentName: null,
  state: "LISTENING" as const,
  level: () => 0,
  messages: [{ id: "1", role: "user" as const, content: "vê se chegou a confirmação", created_at: "2026-11-24T12:00:00Z" }],
  engine: "server" as const,
  speaking: false,
  error: null,
  onInterrupt: () => undefined,
  onHangUp: () => undefined,
};

describe("CallView", () => {
  // No DOM here: just the size of a computer window and no reduced motion.
  beforeAll(() => vi.stubGlobal("window", { innerWidth: 1440, innerHeight: 900, matchMedia: () => ({ matches: false }) }));
  afterAll(() => vi.unstubAllGlobals());

  it("shows the crow with the amber eye between turns, with your last sentence", () => {
    const html = renderToStaticMarkup(<CallView {...base} />);
    expect(html).toContain("/marca/corvo-olho.svg");
    expect(html).toContain('alt="O corvo do VISAO, de olho âmbar"');
    expect(html).not.toContain('class="nano');
    expect(html).toContain("Você: “vê se chegou a confirmação”");
    expect(html).toContain("Desligar");
  });

  it("turns into the tool during a step and says what he is doing", () => {
    const html = renderToStaticMarkup(<CallView {...base} step={{ label: "Procurando no seu Gmail", detail: "reserva Lisboa", kind: "email" } as never} />);
    expect(html).toContain('class="nano');
    expect(html).not.toContain("corvo-olho");
    expect(html).toContain("Procurando no seu Gmail…");
    expect(html).toContain("reserva Lisboa");
  });
});
