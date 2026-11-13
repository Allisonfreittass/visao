// Thin typed client for the VISÃO API. In development, /api is proxied by Vite.

// API timestamps are UTC, including older SQLite rows serialized without an offset.
export function utcDate(value: string): Date {
  return new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`);
}

export type Role = "user" | "assistant";

export interface Source {
  title: string;
  url: string;
  source: string;
}

/** One thing the turn in flight is doing, said as it starts ("Pesquisando “voos”"). */
export interface ProgressStep {
  label: string;
  detail?: string | null;
}

export interface TurnProgress {
  active: boolean;
  elapsed_ms: number;
  steps: ProgressStep[];
}

/** A page it writes (docs/ARTEFATOS.md); "pending" while it is being written. */
export interface ArtifactSummary {
  id: string;
  title: string;
  status: "pending" | "ready" | "failed";
  /** Relative to the API ("/p/<token>"); use Api.pageUrl to open it. */
  path: string | null;
  error?: string | null;
  conversation_id?: string | null;
  created_at: string;
}

/** The Bancada: what it really did in a conversation, its pages and the sites it read live. */
export interface Bench {
  deeds: { at: string; text: string }[];
  pages: ArtifactSummary[];
  visits: { title: string; url: string; at: string }[];
}

/** A photo or file sent with a message. */
export interface Attachment {
  id: string;
  kind: "image" | "document";
  filename: string;
  media_type: string;
  size_bytes: number;
  /** For documents: whether any text could be read out of it. */
  readable?: boolean | null;
}

export interface Message {
  id: string;
  role: Role;
  content: string;
  created_at: string;
  /** "initiative" when the agent started this message on its own. */
  origin?: string;
  /** Sources the reply was given (only known for replies received in this session). */
  sources?: Source[];
  attachments?: Attachment[];
  /** A page this reply said it would write. */
  artifact?: ArtifactSummary | null;
  /** The earlier message this one answers (Responder). */
  reply_to?: { id: string; role: Role; excerpt: string } | null;
  /** Shown before the server answered (only on this device); "queued" waits for the reply in flight. */
  local?: "sending" | "queued" | "failed" | "stopped";
}

export interface MindNote {
  content: string;
  reason: string;
  limit: number;
  updated_at: string | null;
}

export interface Tendency {
  name: string;
  value: number;
  level: string;
  why: string;
}

export interface Mind {
  enabled: boolean;
  /** Computed from what happened between you; tendencies, never claimed as feelings. */
  temperament: { states: Tendency[]; traits: Tendency[]; avoids: Tendency[] };
  questions: { question: string; status: "waiting" | "asked" | "answered"; answer: string }[];
  self_text: string;
  interests: { topic: string; why: string; strength: number }[];
  thoughts: { content: string; created_at: string; ask_owner: string; wanted_to_say: string; delivery: string | null }[];
  self_history: { version: number; content: string; reason: string; created_at: string }[];
  profile: MindNote;
  rules: MindNote;
}

export interface Conversation {
  id: string;
  created_at: string;
  memory_status?: string | null;
  project_id?: string | null;
}

/** A subject with its conversations, pages and files (Projetos). */
export interface Project {
  id: string;
  name: string;
  created_at: string;
  conversations: number;
  pages: number;
  files: number;
}

export interface ProjectDetail extends Project {
  conversation_list: { id: string; created_at: string; title: string }[];
  page_list: ArtifactSummary[];
  file_list: Attachment[];
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

export interface ArmDevice {
  id: string;
  name: string;
  projects: string[];
  version: string;
  online: boolean;
  last_seen_at: string | null;
  token?: string;
}

export interface ArmTask {
  id: string;
  project: string;
  prompt: string;
  status: "proposed" | "approved" | "running" | "done" | "failed" | "rejected" | "cancelled";
  requested_by: "owner" | "agent";
  result: string;
  error: string;
  cost_usd: string | null;
  claude_session_id: string | null;
  conversation_id: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface PushDelivery {
  at: string;
  /** success | failed | no_device | disabled */
  outcome: string;
  devices: number;
  sent: number;
  errors: string[];
}

export interface PushState {
  enabled: boolean;
  public_key: string | null;
  subscriptions: number;
  last_delivery: PushDelivery | null;
}

export interface PushSubscriptionBody {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}

export interface GoogleAction {
  id: string;
  kind: "send_email" | "create_event";
  summary: string;
  payload: {
    to?: string; subject?: string; body?: string;
    title?: string; start?: string; end?: string; location?: string; attendees?: string[];
  };
  status: string;
  result: string;
  conversation_id: string | null;
  created_at: string;
}

export interface GoogleState {
  connected: boolean;
  email: string;
  background: boolean;
  problem: string;
  pending: GoogleAction[];
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
  /** "initiative" also lands in the chat as a message; the rest only lives here. */
  kind: string;
  title: string;
  body: string;
  created_at: string;
  read_at: string | null;
}

export interface StudyEntry {
  id: string;
  previous_entry_id: string | null;
  status: string;
  topic: string;
  question: string;
  rationale: string;
  outcome_reason: string;
  created_at: string;
  evidence: {
    findings?: Array<{ claim: string; sources: number[] }>;
    sources?: Array<{ id: number; url: string; title: string; retrieved_at: string }>;
    uncertain?: string;
    next_question?: string;
  };
}

export interface StudyNotebook {
  scheduler?: { last_tick_at: string; status: string } | null;
  enabled: boolean;
  paused: boolean;
  code_evolution?: Array<{ id: string; status: string; summary?: string; reason?: string; files?: string[]; commit?: string; run_url?: string; error?: string }>;
  interval_hours: number;
  next_eligible_at: string | null;
  source: string;
  entries: StudyEntry[];
}

export interface OnboardingAnswers {
  who: string;
  work: string;
  goal: string;
  tone: string;
}

export interface OnboardingStatus {
  completed: boolean;
  mind_enabled: boolean;
  /** Characters still free in each permanent note. */
  room: { profile: number; rules: number };
}

export interface OnboardingResult {
  completed: boolean;
  skipped: boolean;
  saved: Array<"profile" | "rules">;
  /** The person wrote something and it was not kept. */
  discarded: boolean;
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

  createConversation(projectId?: string | null): Promise<Conversation> {
    const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return this.request(`/conversations${query}`, { method: "POST" });
  }

  moveConversation(conversationId: string, projectId: string | null): Promise<Conversation> {
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/project`, {
      method: "PUT",
      body: JSON.stringify({ project_id: projectId }),
      headers: { "Content-Type": "application/json" },
    });
  }

  projects(): Promise<Project[]> {
    return this.request("/projects");
  }

  project(id: string): Promise<ProjectDetail> {
    return this.request(`/projects/${encodeURIComponent(id)}`);
  }

  createProject(name: string): Promise<Project> {
    return this.request("/projects", {
      method: "POST",
      body: JSON.stringify({ name }),
      headers: { "Content-Type": "application/json" },
    });
  }

  renameProject(id: string, name: string): Promise<Project> {
    return this.request(`/projects/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
      headers: { "Content-Type": "application/json" },
    });
  }

  deleteProject(id: string): Promise<void> {
    return this.request(`/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
  }

  messages(conversationId: string): Promise<Message[]> {
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/messages`);
  }

  send(
    conversationId: string,
    content: string,
    modality: "text" | "voice" = "text",
    attachmentIds: string[] = [],
    replyToId: string | null = null,
    signal?: AbortSignal,
  ): Promise<Turn> {
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      signal,
      body: JSON.stringify({ content, modality, attachment_ids: attachmentIds, reply_to_id: replyToId }),
      headers: { "Content-Type": "application/json" },
    });
  }

  artifact(id: string): Promise<ArtifactSummary> {
    return this.request(`/artifacts/${encodeURIComponent(id)}`);
  }

  artifacts(): Promise<ArtifactSummary[]> {
    return this.request("/artifacts");
  }

  deleteArtifact(id: string): Promise<void> {
    return this.request(`/artifacts/${encodeURIComponent(id)}`, { method: "DELETE" });
  }

  /** The page's full address, to open or share: anyone with it can see the page. */
  pageUrl(path: string): string {
    return new URL(`${this.baseUrl}${path}`, window.location.origin).toString();
  }

  bench(conversationId: string): Promise<Bench> {
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/bench`);
  }

  /** Parar: the turn in flight stops at its next step. */
  cancel(conversationId: string): Promise<{ cancelled: boolean }> {
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/cancel`, { method: "POST" });
  }

  progress(conversationId: string): Promise<TurnProgress> {
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/progress`);
  }

  uploadAttachment(file: Blob, filename: string): Promise<Attachment> {
    const body = new FormData();
    body.append("file", file, filename);
    return this.request("/attachments", { method: "POST", body });
  }

  /** The file's bytes: sent with the token, so an <img> shows it through an object URL. */
  async attachmentBlob(id: string): Promise<Blob> {
    const response = await this.sendRaw(`/attachments/${encodeURIComponent(id)}`, {});
    return response.blob();
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

  replyToNotification(notificationId: string, conversationId: string | null): Promise<{ conversation_id: string }> {
    return this.request(`/notifications/${encodeURIComponent(notificationId)}/reply`, {
      method: "POST",
      body: JSON.stringify({ conversation_id: conversationId }),
      headers: { "Content-Type": "application/json" },
    });
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

  async changePassword(currentPassword: string, newPassword: string): Promise<string> {
    const data = await this.request<{ access_token: string }>("/auth/password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      headers: { "Content-Type": "application/json" },
    });
    this.token = data.access_token;
    return data.access_token;
  }

  async changeEmail(currentPassword: string, newEmail: string): Promise<string> {
    const data = await this.request<{ access_token: string }>("/auth/email", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_email: newEmail }),
      headers: { "Content-Type": "application/json" },
    });
    this.token = data.access_token;
    return data.access_token;
  }

  me(): Promise<{ email: string }> {
    return this.request("/auth/me");
  }

  armDevices(): Promise<ArmDevice[]> {
    return this.request("/arm/devices");
  }

  pairArm(name: string): Promise<ArmDevice> {
    return this.request("/arm/devices", {
      method: "POST",
      body: JSON.stringify({ name }),
      headers: { "Content-Type": "application/json" },
    });
  }

  unpairArm(id: string): Promise<void> {
    return this.request(`/arm/devices/${encodeURIComponent(id)}`, { method: "DELETE" });
  }

  armTasks(): Promise<ArmTask[]> {
    return this.request("/arm/tasks");
  }

  askArm(project: string, prompt: string, conversationId: string | null): Promise<ArmTask> {
    return this.request("/arm/tasks", {
      method: "POST",
      body: JSON.stringify({ project, prompt, conversation_id: conversationId }),
      headers: { "Content-Type": "application/json" },
    });
  }

  /** `via: "voz"`: said in a call after it read the task aloud; the server records it. */
  decideArm(id: string, decision: "approve" | "reject", via: "toque" | "voz" = "toque"): Promise<ArmTask> {
    return this.request(`/arm/tasks/${encodeURIComponent(id)}/${decision}?via=${via}`, { method: "POST" });
  }

  google(): Promise<GoogleState> {
    return this.request("/google");
  }

  googleDisconnect(): Promise<void> {
    return this.request("/google", { method: "DELETE" });
  }

  googleBackground(enabled: boolean): Promise<GoogleState> {
    return this.request("/google/background", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
      headers: { "Content-Type": "application/json" },
    });
  }

  googleActions(): Promise<GoogleAction[]> {
    return this.request("/google/actions");
  }

  decideGoogle(id: string, decision: "approve" | "reject", via: "toque" | "voz" = "toque"): Promise<GoogleAction> {
    return this.request(`/google/actions/${encodeURIComponent(id)}/${decision}?via=${via}`, { method: "POST" });
  }

  pushState(): Promise<PushState> {
    return this.request("/push");
  }

  subscribePush(subscription: PushSubscriptionBody): Promise<void> {
    return this.request("/push/subscriptions", {
      method: "POST",
      body: JSON.stringify(subscription),
      headers: { "Content-Type": "application/json" },
    });
  }

  unsubscribePush(endpoint: string): Promise<void> {
    return this.request("/push/subscriptions", {
      method: "DELETE",
      body: JSON.stringify({ endpoint }),
      headers: { "Content-Type": "application/json" },
    });
  }

  /** With a delay, the test goes out that many seconds later (`scheduled` devices). */
  testPush(delaySeconds = 0): Promise<{ sent: number; scheduled: number }> {
    const query = delaySeconds > 0 ? `?delay=${delaySeconds}` : "";
    return this.request(`/push/test${query}`, { method: "POST" });
  }

  mind(): Promise<Mind> {
    return this.request("/mind");
  }

  undoNote(kind: "profile" | "rules"): Promise<void> {
    return this.request(`/mind/notes/${kind}/undo`, { method: "POST" });
  }

  eraseNote(kind: "profile" | "rules"): Promise<void> {
    return this.request(`/mind/notes/${kind}`, { method: "DELETE" });
  }

  revertSelf(version: number | null): Promise<void> {
    return this.request("/mind/self/revert", {
      method: "POST",
      body: JSON.stringify({ version }),
      headers: { "Content-Type": "application/json" },
    });
  }

  onboarding(): Promise<OnboardingStatus> {
    return this.request("/onboarding");
  }

  finishOnboarding(answers: OnboardingAnswers): Promise<OnboardingResult> {
    return this.request("/onboarding", {
      method: "POST",
      body: JSON.stringify({ answers }),
      headers: { "Content-Type": "application/json" },
    });
  }

  restartOnboarding(): Promise<void> {
    return this.request("/onboarding", { method: "DELETE" });
  }

  skipOnboarding(): Promise<OnboardingResult> {
    return this.request("/onboarding", {
      method: "POST",
      body: JSON.stringify({ skip: true }),
      headers: { "Content-Type": "application/json" },
    });
  }

  study(): Promise<StudyNotebook> {
    return this.request("/study");
  }

  setStudyEnabled(enabled: boolean): Promise<{ enabled: boolean }> {
    return this.request("/study/settings", {
      method: "PUT", body: JSON.stringify({ enabled }),
      headers: { "Content-Type": "application/json" },
    });
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
