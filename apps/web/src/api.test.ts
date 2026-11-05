import { describe, expect, it } from "vitest";

import { Api, ApiError } from "./api";

function fakeFetch(responses: Array<{ status: number; body?: unknown }>) {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const impl = async (url: RequestInfo | URL, init: RequestInit = {}) => {
    calls.push({ url: String(url), init });
    const next = responses.shift()!;
    return new Response(next.body === undefined ? null : JSON.stringify(next.body), {
      status: next.status,
    });
  };
  return { impl: impl as typeof fetch, calls };
}

describe("Api", () => {
  it("logs in with a form body and then sends the bearer token", async () => {
    const { impl, calls } = fakeFetch([
      { status: 200, body: { access_token: "tok" } },
      { status: 200, body: [] },
    ]);
    const api = new Api("/api", impl);

    await api.login("a@b.c", "segredo-longo");
    await api.listConversations();

    expect(calls[0].url).toBe("/api/auth/login");
    expect(calls[0].url).not.toContain("segredo");
    expect(String(calls[0].init.body)).toContain("password=segredo-longo");
    expect(new Headers(calls[1].init.headers).get("Authorization")).toBe("Bearer tok");
  });

  it("sends onboarding answers and the skip as JSON", async () => {
    const result = { completed: true, skipped: false, saved: [], discarded: false };
    const { impl, calls } = fakeFetch([
      { status: 200, body: result },
      { status: 200, body: result },
    ]);
    const api = new Api("/api", impl);

    await api.finishOnboarding({ who: "eu", work: "", goal: "", tone: "" });
    await api.skipOnboarding();

    expect(calls.map((call) => call.url)).toEqual(["/api/onboarding", "/api/onboarding"]);
    expect(calls.map((call) => call.init.method)).toEqual(["POST", "POST"]);
    for (const call of calls) {
      expect(new Headers(call.init.headers).get("Content-Type")).toBe("application/json");
    }
    expect(JSON.parse(String(calls[0].init.body)).answers.who).toBe("eu");
    expect(JSON.parse(String(calls[1].init.body))).toEqual({ skip: true });
  });

  it("surfaces the API detail and forgets the token on 401", async () => {
    const { impl } = fakeFetch([
      { status: 200, body: { access_token: "tok" } },
      { status: 401, body: { detail: "Credenciais inválidas" } },
    ]);
    const api = new Api("/api", impl);
    await api.login("a@b.c", "x".repeat(12));

    const error = await api.listConversations().catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(401);
    expect(error.message).toBe("Credenciais inválidas");
    expect(api.authenticated).toBe(false);
  });

  it("encodes conversation ids in paths", async () => {
    const { impl, calls } = fakeFetch([{ status: 200, body: [] }]);
    await new Api("/api", impl).messages("a/b");
    expect(calls[0].url).toBe("/api/conversations/a%2Fb/messages");
  });
});
