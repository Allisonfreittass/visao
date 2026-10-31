// Thin typed client for the VISÃO API. In development, /api is proxied by Vite.

export type Role = "user" | "assistant";

export interface Message {
  id: string;
  role: Role;
  content: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  created_at: string;
}

export interface Turn {
  user_message: Message;
  assistant_message: Message;
  usage: { provider: string; model: string; latency_ms: number | null; cost_usd: string };
}

export interface SystemStatus {
  genesis_completed: boolean;
  identity: { internal_id: string; chosen_name: string | null } | null;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

type Fetch = typeof fetch;

export class Api {
  private token: string | null = null;

  constructor(
    private readonly baseUrl = "/api",
    private readonly fetchImpl: Fetch = (...args) => fetch(...args),
  ) {}

  get authenticated(): boolean {
    return this.token !== null;
  }

  setToken(token: string | null): void {
    this.token = token;
  }

  async login(email: string, password: string): Promise<string> {
    // OAuth2 password form: credentials go in the body, never in the URL.
    const body = new URLSearchParams({ username: email, password });
    const data = await this.request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    this.token = data.access_token;
    return data.access_token;
  }

  health(): Promise<{ status: string }> {
    return this.request("/health");
  }

  status(): Promise<SystemStatus> {
    return this.request("/system/status");
  }

  listConversations(): Promise<Conversation[]> {
    return this.request("/conversations");
  }

  createConversation(): Promise<Conversation> {
    return this.request("/conversations", { method: "POST" });
  }

  messages(conversationId: string): Promise<Message[]> {
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/messages`);
  }

  send(conversationId: string, content: string): Promise<Turn> {
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
      headers: { "Content-Type": "application/json" },
    });
  }

  memorySettings(): Promise<{ enabled: boolean }> {
    return this.request("/memory/settings");
  }

  setMemoryEnabled(enabled: boolean): Promise<{ enabled: boolean }> {
    return this.request("/memory/settings", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
      headers: { "Content-Type": "application/json" },
    });
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (this.token) headers.set("Authorization", `Bearer ${this.token}`);
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, { ...init, headers });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        // Non-JSON error body: keep the status text.
      }
      if (response.status === 401) this.token = null;
      throw new ApiError(response.status, detail);
    }
    return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
  }
}
