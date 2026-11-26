import { renderToStaticMarkup } from "react-dom/server";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import { type Api, ApiError } from "../api";
import { OLHAR_PX, olhar } from "../brand/CorvoClose";
import { Entrance } from "./Entrance";
import { Login, MIN_PASSWORD_LENGTH, loginError, missingField, staysSignedIn } from "./Login";

const api = { firstRunNeeded: async () => false } as unknown as Api;

// The markup is rendered in node: the screen only asks the window whether it runs as an installed app.
beforeAll(() => vi.stubGlobal("window", { matchMedia: () => ({ matches: false }) }));
afterAll(() => vi.unstubAllGlobals());

function entrada(firstAccount = false): string {
  return renderToStaticMarkup(
    <Entrance firstAccount={firstAccount}>
      <Login api={api} onLoggedIn={() => {}} />
    </Entrance>,
  );
}

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

describe("the empty field", () => {
  it("asks for the password before going to the server", () => {
    expect(missingField("eu@exemplo.com", "")).toEqual({ field: "password", text: "Digite a senha para entrar." });
    expect(missingField("  ", "uma senha")).toEqual({ field: "email", text: "Digite o e-mail para entrar." });
    expect(missingField("eu@exemplo.com", "uma senha")).toBeNull();
  });

  it("is checked by the screen, not by the browser's own bubble", () => {
    expect(entrada()).toContain("novalidate");
  });
});

describe("the entrance", () => {
  it("shows, in order, the name, the greeting, the line, the fields, Entrar and the two links", () => {
    const html = entrada();
    const order = ["VISAO</p>", "Bem-vindo de volta.", "Só você entra aqui. Ele lembra apenas do que você deixar.", ">E-mail</label>", ">Senha</label>", ">Entrar</button>", ">Esqueci a senha</button>", ">Primeira vez? Configurar</button>"];
    const positions = order.map((text) => html.indexOf(text));
    expect(positions.every((at) => at >= 0)).toBe(true);
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);
  });

  it("draws the crow inline, with the amber only in his eye", () => {
    const html = entrada();
    expect(html).toContain('aria-label="O corvo do VISAO, de olho âmbar"');
    expect(html).toContain('class="corvo-close-pupila"');
    expect(html.match(/#E39A2E/g)).toHaveLength(1);
    expect(html).not.toContain("<img");
  });

  it("keeps the browser's translator off the name", () => {
    expect(entrada()).toContain('<p class="entrada-marca" translate="no">VISAO</p>');
  });

  it("has no checkbox between the password and Entrar, as in the mockup", () => {
    expect(entrada()).not.toContain('type="checkbox"');
  });

  it("greets the first account without 'de volta'", () => {
    expect(entrada(true)).toContain(">Bem-vindo.</h1>");
    expect(String(MIN_PASSWORD_LENGTH)).toBe("12");
  });
});

describe("the pupil", () => {
  it("moves 6 px toward the focused field, whatever the drawing's scale", () => {
    const right = olhar({ x: 100, y: 100 }, { x: 600, y: 100 }, 2);
    expect(right.dx * 2).toBeCloseTo(OLHAR_PX);
    expect(right.dy).toBeCloseTo(0);
    const below = olhar({ x: 100, y: 100 }, { x: 100, y: 900 }, 1.5);
    expect(below.dy * 1.5).toBeCloseTo(6);
    const diagonal = olhar({ x: 0, y: 0 }, { x: 300, y: 400 }, 1);
    expect(Math.hypot(diagonal.dx, diagonal.dy)).toBeCloseTo(6);
  });

  it("stays put when there is nowhere to look", () => {
    expect(olhar({ x: 5, y: 5 }, { x: 5, y: 5 }, 1)).toEqual({ dx: 0, dy: 0 });
    expect(olhar({ x: 0, y: 0 }, { x: 10, y: 0 }, 0)).toEqual({ dx: 0, dy: 0 });
  });
});


describe("staysSignedIn", () => {
  it("keeps the Mac app and the phone app signed in, never a tab on a server elsewhere", () => {
    expect(staysSignedIn("127.0.0.1", false)).toBe(true);
    expect(staysSignedIn("localhost", false)).toBe(true);
    expect(staysSignedIn("visao.exemplo.com", true)).toBe(true);
    expect(staysSignedIn("54-20-150-130.sslip.io", false)).toBe(false);
  });
});
