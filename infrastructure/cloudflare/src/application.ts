export interface Env {
  ASSETS: Fetcher;
  LOGIN_LIMITER: RateLimit;
  BACKEND: { getByName(name: string): { fetch(request: Request): Promise<Response> } };
  VISION_DATABASE_URL: string;
  VISION_SECRET_KEY: string;
  VISION_CLOUD_TICK_KEY: string;
  [key: string]: unknown;
}

// Forward only application configuration, not arbitrary Cloudflare bindings or credentials.
export const APP_KEYS = [
  "VISION_BUILD_SHA", "VISION_CODE_AUTONOMY_ENABLED", "VISION_CODE_AUTONOMY_KEY",
  "VISION_DATABASE_URL", "VISION_DATABASE_SCHEMA", "VISION_SECRET_KEY", "VISION_CLOUD_TICK_KEY",
  "VISION_LLM_PROVIDER_NAME", "VISION_LLM_BASE_URL", "VISION_LLM_API_KEY", "VISION_LLM_MODEL",
  "VISION_LLM_PRICE_INPUT_PER_MTOK", "VISION_LLM_PRICE_OUTPUT_PER_MTOK", "VISION_LLM_TIMEOUT_SECONDS",
  "VISION_LLM_FALLBACK_PROVIDER_NAME", "VISION_LLM_FALLBACK_BASE_URL", "VISION_LLM_FALLBACK_API_KEY",
  "VISION_LLM_FALLBACK_MODEL", "VISION_LLM_FALLBACK_PRICE_INPUT_PER_MTOK",
  "VISION_LLM_FALLBACK_PRICE_OUTPUT_PER_MTOK", "VISION_LLM_MAX_OUTPUT_TOKENS",
  "VISION_LLM_CURATION_MAX_OUTPUT_TOKENS", "VISION_LLM_DAILY_BUDGET_USD",
  "VISION_LLM_CONVERSATION_BUDGET_USD", "VISION_LLM_CONTEXT_CHAR_BUDGET",
  "VISION_LLM_MAX_PAID_SPEND_USD", "VISION_LLM_PAID_DAILY_USD", "VISION_LLM_PAID_MONTHLY_USD", "VISION_LLM_FREE_GRANTS",
  "VISION_LLM_BUDGET_CALLS_PER_DAY", "VISION_LLM_BUDGET_CALLS_PER_HOUR",
  "VISION_LLM_BUDGET_INPUT_TOKENS_PER_DAY", "VISION_LLM_BUDGET_OUTPUT_TOKENS_PER_DAY",
  "VISION_LLM_BUDGET_INPUT_TOKENS_PER_CALL", "VISION_LLM_BUDGET_OUTPUT_TOKENS_PER_CALL",
  "VISION_LLM_BUDGET_CONCURRENCY",
  "VISION_CURIOSITY_ENABLED", "VISION_RESEARCH_PER_DAY", "VISION_RESEARCH_PER_CONVERSATION",
  "VISION_AUTONOMY_CYCLE_MINUTES", "VISION_AUTONOMY_LLM_CALLS_PER_DAY",
  "VISION_AUTONOMY_TOKENS_PER_DAY", "VISION_AUTONOMY_MAX_ACTIONS_PER_CYCLE",
  "VISION_AUTONOMY_MAX_SECONDS", "VISION_LOG_LEVEL",
  "VISION_ENVIRONMENT", "VISION_ACCESS_TOKEN_TTL_MINUTES",
  "VISION_LLM_TRUST_ZERO_PRICE", "VISION_LLM_FAST_EXTRA_BODY",
  "VISION_LLM_FALLBACK_FAST_EXTRA_BODY", "VISION_LLM_FALLBACK2_FAST_EXTRA_BODY",
  "VISION_LLM_FALLBACK2_PROVIDER_NAME", "VISION_LLM_FALLBACK2_BASE_URL", "VISION_LLM_FALLBACK2_API_KEY",
  "VISION_LLM_FALLBACK2_MODEL", "VISION_LLM_FALLBACK2_PRICE_INPUT_PER_MTOK",
  "VISION_LLM_FALLBACK2_PRICE_OUTPUT_PER_MTOK",
  "VISION_MIND_ENABLED", "VISION_MIND_THINK_MINUTES", "VISION_MIND_REVIEW_TURNS",
  "VISION_MIND_INITIATIVES_PER_DAY", "VISION_STUDY_INTERVAL_MINUTES", "VISION_RESEARCH_MAX_RESULTS",
  "VISION_TTS_APPROVED_VOICES", "VISION_TTS_MAX_CHARS", "VISION_STT_MODEL", "VISION_STT_MAX_BYTES",
  "VISION_WEBPUSH_PUBLIC_KEY", "VISION_WEBPUSH_PRIVATE_KEY", "VISION_WEBPUSH_SUBJECT",
  "VISION_GITHUB_TOKEN", "VISION_TAVILY_API_KEY",
] as const;

export function appEnvironment(env: Env): Record<string, string> {
  if (!env.VISION_DATABASE_URL?.startsWith("postgresql+psycopg://")) {
    throw new Error("Configure a persistent PostgreSQL database before starting VISÃO");
  }
  if (env.VISION_DATABASE_SCHEMA !== "visao") throw new Error("A private application schema is required");
  if (!env.VISION_SECRET_KEY || !env.VISION_CLOUD_TICK_KEY) {
    throw new Error("Missing application secrets");
  }
  const values: Record<string, string> = {};
  for (const key of APP_KEYS) {
    const value = env[key];
    if (typeof value === "string" && value) values[key] = value;
  }
  // Self-hosted voice models are not included in this small text-and-study deployment, so voice
  // stays off unless configured; the edge is always a production deployment.
  return { VISION_STT_MODEL: "", VISION_TTS_APPROVED_VOICES: "", ...values,
    VISION_ENVIRONMENT: "production", PYTHONDONTWRITEBYTECODE: "1" };
}

export const handler = {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/internal")) return new Response("Not found", { status: 404 });
    if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
      if (url.pathname === "/api/auth/login" && request.method === "POST") {
        const result = await env.LOGIN_LIMITER.limit({ key: `visao-login:${request.headers.get("CF-Connecting-IP") ?? "unknown"}` });
        if (!result.success) return Response.json({ detail: "Muitas tentativas. Aguarde um minuto." }, { status: 429 });
      }
      const backendUrl = new URL(request.url);
      backendUrl.pathname = url.pathname.slice(4) || "/";
      // Block normalized paths too: /api/internal must not bypass the public edge.
      if (backendUrl.pathname.startsWith("/internal")) return new Response("Not found", { status: 404 });
      const forwarded = new Request(backendUrl, request);
      forwarded.headers.delete("X-Visao-Cron-Key");
      try {
        const response = await env.BACKEND.getByName("primary").fetch(forwarded);
        const headers = new Headers(response.headers);
        headers.set("Cache-Control", "no-store");
        headers.set("X-Content-Type-Options", "nosniff");
        return new Response(response.body, { status: response.status, headers });
      } catch {
        console.error("VISÃO backend unavailable");
        return Response.json({ detail: "O VISÃO está temporariamente indisponível. Tente novamente." }, { status: 503 });
      }
    }
    return env.ASSETS.fetch(request);
  },
  async scheduled(_controller: ScheduledController, env: Env): Promise<void> {
    const response = await env.BACKEND.getByName("primary").fetch(new Request(
      "https://container/internal/cloud/tick", {
        method: "POST", headers: { "X-Visao-Cron-Key": env.VISION_CLOUD_TICK_KEY },
      },
    ));
    await response.body?.cancel();
    if (!response.ok) throw new Error(`VISÃO scheduled tick failed (${response.status})`);
  },
} satisfies ExportedHandler<Env>;

export default handler;
