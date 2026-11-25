import { describe, expect, it } from "vitest";

import { ApiError } from "../api";
import { loginError } from "./Login";

describe("loginError", () => {
  it("points at the fields only when the credentials are wrong", () => {
    expect(loginError(new ApiError(401, "Credenciais inválidas"))).toEqual({ text: "E-mail ou senha não conferem.", credentials: true });
    expect(loginError(new ApiError(422, "Unprocessable Entity")).credentials).toBe(true);
  });

  it("keeps the server's own text for too many attempts", () => {
    expect(loginError(new ApiError(429, "Muitas tentativas. Aguarde alguns minutos."))).toEqual({
      text: "Muitas tentativas. Aguarde alguns minutos.",
      credentials: false,
    });
  });

  it("never shows a raw server status, and never blames the password for it", () => {
    for (const status of [500, 502, 503, 504]) {
      const error = loginError(new ApiError(status, "Internal Server Error"));
      expect(error.credentials).toBe(false);
      expect(error.text).not.toMatch(/Internal|Server Error|Gateway/);
    }
    expect(loginError(new ApiError(418, "I'm a teapot")).text).toBe("Não consegui entrar agora. Tente de novo.");
  });

  it("tells a timeout apart from no connection", () => {
    expect(loginError(new DOMException("timeout", "TimeoutError")).text).toBe("O servidor demorou para responder. Tente de novo.");
    expect(loginError(new TypeError("Failed to fetch")).text).toMatch(/^Sem conexão/);
  });
});

describe("the first account on the owner's machine", () => {
  it("asks for 12 characters and the same password twice before going to the server", async () => {
    const { firstRunProblem } = await import("./Login");
    expect(firstRunProblem("curta", "curta")).toMatch(/12 caracteres/);
    expect(firstRunProblem("uma senha bem longa", "outra senha longa")).toMatch(/não são iguais/);
    expect(firstRunProblem("uma senha bem longa", "uma senha bem longa")).toBeNull();
  });
});
