// Thin typed client for the VISÃO API. In development, /api is proxied by Vite.

export type Role = "user" | "assistant";

export interface Source {
  title: string;
  url: string;
  source: string;
}

export interface Message {
  id: string;
  role: Role;
  content: string;
  created_at: string;
  /** Sources the reply was given (only known for replies received in this session). */
  sources?: Source[];
}

export interface Conversation {
  id: string;
  created_at: string;
  memory_status?: string | null;
}

export interface Turn {
  user_message: Message;
  assistant_message: Message;
  usage: { provider: string; model: string; latency_ms: number | null; cost_usd: string };
  sources: Source[];
}

export interface SystemStatus {
  genesis_completed: boolean;
  identity: { internal_id: string; chosen_name: string | null } | null;
}

export interface VoiceStatus {
  enabled: boolean;
  listening: boolean;
  current_voice: string | null;
  source: "chosen" | "system_default" | "none";
}

export interface Goal {
  id: string;
  title: string;
  rationale: string;
  success_criteria: string;
  required_permissions: string[];
  status: string;
}

export interface AppNotification {
  id: string;
  title: string;
  body: string;
  created_at: string;
  read_at: string | null;
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

  send(
    conversationId: string,
    content: string,
    modality: "text" | "voice" = "text",
  ): Promise<Turn> {
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, modality }),
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

  stt(wav: Blob): Promise<{ text: string; model: string; elapsed_ms: number }> {
    return this.request("/voice/stt", {
      method: "POST",
      body: wav,
      headers: { "Content-Type": "audio/wav" },
    });
  }

  approvals(): Promise<Goal[]> {
    return this.request("/approvals");
  }

  decideGoal(goalId: string, decision: "approve" | "reject"): Promise<Goal> {
    return this.request(`/goals/${encodeURIComponent(goalId)}/${decision}`, {
      method: "POST",
      body: JSON.stringify({ reason: "" }),
      headers: { "Content-Type": "application/json" },
    });
  }

  notifications(): Promise<AppNotification[]> {
    return this.request("/notifications");
  }

  markRead(notificationId: string): Promise<void> {
    return this.request(`/notifications/${encodeURIComponent(notificationId)}/read`, {
      method: "POST",
    });
  }

  permissions(): Promise<{ auto_research: boolean }> {
    return this.request("/autonomy/permissions");
  }

  setAutoResearch(enabled: boolean): Promise<{ auto_research: boolean }> {
    return this.request("/autonomy/permissions", {
      method: "PUT",
      body: JSON.stringify({ auto_research: enabled }),
      headers: { "Content-Type": "application/json" },
    });
  }

  autonomy(): Promise<{ paused: boolean }> {
    return this.request("/system/autonomy");
  }

  setAutonomyPaused(paused: boolean): Promise<{ paused: boolean }> {
    return this.request("/system/autonomy", {
      method: "PUT",
      body: JSON.stringify({ paused, reason: paused ? "pausa pela interface" : "retomada" }),
      headers: { "Content-Type": "application/json" },
    });
  }

  feedback(
    messageId: string,
    rating: 1 | -1,
    tags: string[],
  ): Promise<{ state_version: number; state_changed: boolean }> {
    return this.request(`/messages/${encodeURIComponent(messageId)}/feedback`, {
      method: "POST",
      body: JSON.stringify({ rating, tags, comment: "" }),
      headers: { "Content-Type": "application/json" },
    });
  }

  voiceStatus(): Promise<VoiceStatus> {
    return this.request("/voice/status");
  }

  async sentences(text: string): Promise<string[]> {
    const body = await this.request<{ sentences: string[] }>("/voice/sentences", {
      method: "POST",
      body: JSON.stringify({ text }),
      headers: { "Content-Type": "application/json" },
    });
    return body.sentences;
  }

  async tts(text: string, signal?: AbortSignal): Promise<ArrayBuffer> {
    const response = await this.sendRaw("/voice/tts", {
      method: "POST",
      body: JSON.stringify({ text }),
      headers: { "Content-Type": "application/json" },
      signal,
    });
    return response.arrayBuffer();
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.sendRaw(path, init);
    return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
  }

  private async sendRaw(path: string, init: RequestInit): Promise<Response> {
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
    return response;
  }
}
