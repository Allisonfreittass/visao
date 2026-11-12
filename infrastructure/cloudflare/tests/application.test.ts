import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { APP_KEYS, appEnvironment, handler, type Env } from "../src/application";

// JSONC: drop // and /* */ comments outside strings, then trailing commas.
function parseJsonc(text: string): Record<string, unknown> {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') {
      let j = i + 1;
      while (j < text.length && text[j] !== '"') j += text[j] === "\\" ? 2 : 1;
      out += text.slice(i, j + 1);
      i = j;
    } else if (c === "/" && text[i + 1] === "/") {
      while (i < text.length && text[i] !== "\n") i++;
      out += "\n";
    } else if (c === "/" && text[i + 1] === "*") {
      i = text.indexOf("*/", i + 2) + 1;
    } else out += c;
  }
  return JSON.parse(out.replace(/,(\s*[}\]])/g, "$1"));
}

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
  it("forwards the reviewed budget configuration into the Python container", () => {
    const { value } = env();
    const budget = {
      VISION_LLM_MAX_PAID_SPEND_USD: "0",
      VISION_LLM_FREE_GRANTS: '[{"provider":"test-only"}]',
      VISION_LLM_BUDGET_CALLS_PER_DAY: "30", VISION_LLM_BUDGET_CALLS_PER_HOUR: "10",
      VISION_LLM_BUDGET_INPUT_TOKENS_PER_DAY: "60000",
      VISION_LLM_BUDGET_OUTPUT_TOKENS_PER_DAY: "15000",
      VISION_LLM_BUDGET_INPUT_TOKENS_PER_CALL: "32768",
      VISION_LLM_BUDGET_OUTPUT_TOKENS_PER_CALL: "4096",
      VISION_LLM_BUDGET_CONCURRENCY: "1",
    };
    expect(appEnvironment({ ...value, ...budget })).toMatchObject(budget);
  });
  it("forwards every VISION_* variable that wrangler.jsonc configures", () => {
    const config = parseJsonc(readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8"));
    const vars = Object.keys(config.vars as Record<string, string>).filter((k) => k.startsWith("VISION_"));
    expect(vars.length).toBeGreaterThan(10);
    expect(vars.filter((key) => !(APP_KEYS as readonly string[]).includes(key))).toEqual([]);
  });
  it("forwards model, fallback and inner-life settings while pinning production", () => {
    const { value } = env();
    const extra = {
      VISION_LLM_TRUST_ZERO_PRICE: "true", VISION_LLM_FAST_EXTRA_BODY: '{"reasoning":{"enabled":false}}',
      VISION_LLM_FALLBACK2_MODEL: "m2", VISION_MIND_ENABLED: "true", VISION_STUDY_INTERVAL_MINUTES: "360",
      VISION_WEBPUSH_SUBJECT: "mailto:owner@example.com",
    };
    const config = appEnvironment({ ...value, ...extra, VISION_ENVIRONMENT: "development" } as Env);
    expect(config).toMatchObject(extra);
    expect(config.VISION_ENVIRONMENT).toBe("production");
    expect(config.VISION_STT_MODEL).toBe("");
    expect(config.VISION_TTS_APPROVED_VOICES).toBe("");
  });
});
