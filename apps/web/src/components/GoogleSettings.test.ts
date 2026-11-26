import { describe, expect, it } from "vitest";

import { callbackAddress, googleReturn } from "./GoogleSettings";

describe("callbackAddress", () => {
  it("is the address the Web application client registers, on this very origin", () => {
    expect(callbackAddress("https://54-20-150-130.sslip.io")).toBe("https://54-20-150-130.sslip.io/api/google/web/callback");
  });
});

describe("googleReturn", () => {
  it("says nothing without a return from Google", () => {
    expect(googleReturn("")).toBeNull();
    expect(googleReturn("?c=123")).toBeNull();
  });

  it("says it connected, and names the permissions left unticked", () => {
    expect(googleReturn("?google=conectado")).toEqual({
      ok: true,
      text: "Google conectado. Agora eu leio seu email e sua agenda quando você pedir.",
    });
    const partial = googleReturn("?google=conectado&faltou=gmail.send%2Ccalendar.events");
    expect(partial?.ok).toBe(true);
    expect(partial?.text).toContain("Você não marcou mandar email e a agenda");
  });

  it("turns each reason into words, never the raw code", () => {
    for (const reason of ["vencido", "navegador", "recusado", "troca", "google", "outro"]) {
      const said = googleReturn(`?google=erro&motivo=${reason}`);
      expect(said?.ok).toBe(false);
      expect(said?.text).not.toBe(reason);
      expect(said?.text.length).toBeGreaterThan(20);
    }
    expect(googleReturn("?google=erro&motivo=navegador")?.text).toContain("mesmo navegador");
  });
});
