import { describe, expect, it, vi } from "vitest";
import { appEnvironment, handler, type Env } from "../src/application";

function env() {
  const backend = { fetch: vi.fn(async () => new Response('{"ok":true}')) };
  const value = {
    LOGIN_LIMITER: { limit: vi.fn(async () => ({ success: true })) },
    ASSETS: { fetch: vi.fn(async () => new Response("frontend")) },
    BACKEND: { getByName: vi.fn(() => backend) },
    VISION_DATABASE_URL: "postgresql+psycopg://app:password@example.com/postgres",
    VISION_DATABASE_SCHEMA: "visao", VISION_SECRET_KEY: "test-only-key",
    VISION_CLOUD_TICK_KEY: "cron-key", UNRELATED_ACCOUNT_SECRET: "must-not-forward",
  } as unknown as Env;
  return { value, backend };
}

describe("Cloudflare edge routing", () => {
  it("serves assets without waking a container", async () => {
    const { value } = env();
    expect(await (await handler.fetch(new Request("https://visao.test/"), value)).text()).toBe("frontend");
    expect(value.BACKEND.getByName).not.toHaveBeenCalled();
  });
  it("cannot publicly reach scheduler routes or forward a forged scheduler key", async () => {
    const { value, backend } = env();
    for (const path of ["/internal/cloud/tick", "/api/internal/cloud/tick"]) {
      const response = await handler.fetch(new Request(`https://visao.test${path}`, { method:"POST" }), value);
      expect(response.status).toBe(404);
    }
    expect(backend.fetch).not.toHaveBeenCalled();
    const response = await handler.fetch(new Request("https://visao.test/api/conversations", {
      headers: { Authorization:"Bearer user-token", "X-Visao-Cron-Key":"forged" },
    }), value);
    const forwarded = backend.fetch.mock.calls[0][0] as unknown as Request;
    expect(new URL(forwarded.url).pathname).toBe("/conversations");
    expect(forwarded.headers.has("X-Visao-Cron-Key")).toBe(false);
    expect(forwarded.headers.get("Authorization")).toBe("Bearer user-token");
    expect(response.headers.get("Cache-Control")).toBe("no-store");
  });
  it("runs a scheduled tick with only the private server key", async () => {
    const { value, backend } = env();
    await handler.scheduled({} as ScheduledController, value);
    const request = backend.fetch.mock.calls[0][0] as unknown as Request;
    expect(request.method).toBe("POST");
    expect(request.headers.get("X-Visao-Cron-Key")).toBe("cron-key");
    expect(new URL(request.url).pathname).toBe("/internal/cloud/tick");
  });
  it("limits login attempts before waking the container", async () => {
    const { value, backend } = env();
    value.LOGIN_LIMITER = { limit: vi.fn(async () => ({ success: false })) } as unknown as RateLimit;
    const response = await handler.fetch(new Request("https://visao.test/api/auth/login", {method:"POST"}), value);
    expect(response.status).toBe(429);
    expect(backend.fetch).not.toHaveBeenCalled();
  });
  it("only forwards selected app variables and refuses ephemeral SQLite storage", () => {
    const { value } = env();
    const config = appEnvironment(value);
    expect(config.UNRELATED_ACCOUNT_SECRET).toBeUndefined();
    expect(config.VISION_DATABASE_SCHEMA).toBe("visao");
    expect(config.VISION_ENVIRONMENT).toBe("production");
    expect(() => appEnvironment({...value, VISION_DATABASE_URL:"sqlite:///dev.db"})).toThrow();
  });
});
