import type { Position } from "./location";

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
  /** The tool the step uses (core/conversation/progress.py KINDS); null for his own steps. */
  kind?: string | null;
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

/** A table of options under a live quote, built by the server from prices pages showed. */
export interface QuoteTable {
  version: number;
  title: string;
  travelers: number;
  rows: Array<{ option: string; dates: string; total: string; total_text: string; currency: string; sites: string[] }>;
  /** At most a sentence of neighbor dates and one of what the total leaves out. */
  notes: string[];
  /** What the quote assumed instead of asking. */
  assumed: Record<string, string>;
  /** The same table as plain text: what an app that does not know this field shows. */
  text: string;
}

/** "nuvem": the cloud; "local": the model on the Mac first; "auto": the cloud, the Mac as reserve. */
export type BrainMode = "nuvem" | "local" | "auto";

/** Which cloud provider goes first for each task (docs/decisions/0022). */
export type RoutingMode = "fixa" | "por_tarefa";

export interface RoutingState {
  mode: RoutingMode;
  /** The configured providers, in the order of the server's settings. */
  configured: string[];
  /** The order right now for what carries something of the owner (almost everything). */
  personal: string[];
  /** The order right now for what carries only public text (the study review). */
  public: string[];
}

/** One skill in Habilidades (core/skills/catalog.py): a way of working, text only. */
export interface Skill {
  id: string;
  name: string;
  description: string;
  /** "instalada": read, adapted and shipped with the app. */
  origin: string;
  /** Where it came from, like "anthropics/skills". */
  source: string;
  /** The exact version that was read. */
  source_url: string;
  license: string;
  installed_on: string;
  enabled: boolean;
}

export interface BrainState {
  mode: BrainMode;
  /** The model a Mac offers right now ("qwen3:4b"); null: none online. */
  local_model: string | null;
  mac_online: boolean;
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
  /** The same text as `content` in 2 or 3 bubbles; null or missing is one bubble. */
  parts?: string[] | null;
  /** Options under a live quote; its `text` is also the last entry of `parts` (docs/COTACAO_TABELA.md). */
  quote_table?: QuoteTable | null;
  /** The reply did something in this project: "abrir o projeto" (ADR-0021). */
  project_id?: string | null;
  /** Written by the local model on the Mac (docs/MODELO_LOCAL.md): "Visão · local". */
  local_model?: boolean;
  /** Only here: it was shown as it was written, so it does not come in again. */
  streamed?: boolean;
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

/** A remembered fact (GET /memory). `source_message_ids`: the messages it came from. */
export interface MemoryItem {
  id: string;
  type: string;
  content: string;
  confidence: number;
  created_at: string;
  source_message_ids: string[];
}

/** Quiet hours, "HH:MM" in the owner's timezone (GET /notifications/settings). */
export interface QuietHours {
  quiet_start: string;
  quiet_end: string;
  timezone: string;
}

/** Model use in the last `window_days` (GET /cognition/metrics), per purpose. cost_usd is a decimal string. */
export interface CognitionMetrics {
  window_days: number;
  llm_usage: Record<string, { calls: number; tokens: number; cost_usd: string; autonomous?: boolean }>;
}

/** How he chose his name (GET /identity/name). By design the owner cannot set it. */
export interface NameRecord {
  chosen_name: string | null;
  history: {
    event_type: string;
    previous_name: string | null;
    new_name: string | null;
    alternatives_considered: string[] | null;
    rationale: string | null;
    created_at: string;
  }[];
}

/** One of the owner's goals, written only with the owner's yes (docs/decisions/0025). */
export interface OwnerGoal {
  id: string;
  content: string;
  reason: string;
  /** The owner's own words it came from. */
  source_text: string;
  source_message_id: string | null;
  status: "active" | "ended" | "undone";
  replaces_id: string | null;
  created_at: string;
  ended_at: string | null;
}

export interface OwnerGoals {
  active: OwnerGoal[];
  history: OwnerGoal[];
}

export interface Conversation {
  id: string;
  created_at: string;
  memory_status?: string | null;
  project_id?: string | null;
  /** 3 to 6 words after the first exchange; null: the menu shows the date. */
  title?: string | null;
  /** The owner's one continuous conversation (docs/CONVERSA_CONTINUA.md): the app opens it. */
  continuous?: boolean;
}

/** A closed stretch of the continuous conversation, for the dividers in the chat. */
export interface Segment {
  id: string;
  title: string;
  started_at: string;
  ended_at: string;
  first_message_id: string;
  last_message_id: string;
  messages: number;
  status: "summarized" | "failed";
}

/** A subject with its conversations, pages and files (Projetos). */
export interface Project {
  id: string;
  name: string;
  created_at: string;
  conversations: number;
  pages: number;
  files: number;
  /** What it noted here from the conversation, a "- " line per fact (ADR-0021). */
  notes?: string;
  notes_updated_at?: string | null;
  panels?: number;
}

export interface ProjectDetail extends Project {
  conversation_list: { id: string; created_at: string; title: string }[];
  panel_list?: { id: string; title: string; status: string }[];
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
  /** work: Claude Code did it; undo: the arm put back what `undo_of` changed; desktop: a
   * session at the mouse and keyboard (docs/MEXER.md). */
  kind: "work" | "undo" | "desktop";
  undo_of: string | null;
  until_tests: boolean;
  /** Measured by the arm's photos before and after, not told by Claude. */
  changed_files: ArmChangedFile[] | null;
  tests: ArmTests | null;
  undone_at: string | null;
  can_undo: boolean;
}

export interface ArmChangedFile {
  path: string;
  /** A added, M changed, D deleted */
  status: "A" | "M" | "D";
}

export interface ArmTests {
  command: string;
  passed: boolean;
  attempts: number;
  tail?: string;
  error?: string;
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

/** A change in one of the owner's other apps, through Composio, waiting for a yes (docs/APPS.md). */
export interface ToolAction {
  id: string;
  toolkit: string;
  tool: string;
  version: string;
  summary: string;
  app: string;
  tool_name: string;
  description: string;
  /** Every argument the tool will get, shown in full on the card. */
  arguments: Record<string, unknown>;
  status: string;
  result: string;
  conversation_id: string | null;
  created_at: string;
}

/** Ajustes › Apps: off (no section) without the Composio key on the server. */
export interface AppsState {
  enabled: boolean;
  notice: string;
  connected: { toolkit: string; name: string; logo: string }[];
  problem: string;
  calls_this_month: number;
  monthly_limit: number;
  pending: ToolAction[];
}

export interface AppCatalogItem {
  slug: string;
  name: string;
  description: string;
  logo: string;
  categories: string[];
  /** Connects with Composio's own sign-in. */
  managed: boolean;
  /** Can be connected from here (docs/APPS.md); the rest need an OAuth app of our own. */
  connectable: boolean;
  /** Composio's page will ask for the owner's key to this app. */
  asks_key: boolean;
}

/** After a live quote: keep it on the home screen and check the price daily (docs/PAINEIS.md). */
export interface PanelOffer {
  id: string;
  conversation_id: string;
  message_id: string | null;
  title: string;
  goal_amount: string | null;
  currency: string;
  status: string;
  summary: string;
  artifact?: ArtifactSummary | null;
  created_at: string;
}

/** One thing a live panel quotes, as a page read live showed it (docs/PAINEIS.md). */
export interface PanelItem {
  kind: "flight" | "hotel";
  provider: string;
  where: string;
  dates: string;
  connections: number | null;
  price: string | null;
  price_basis: "per_person" | "total";
  /** What it costs the whole party (computed on the server). */
  cost: string | null;
  currency: string;
  site: string;
  url: string;
  read_at: string | null;
}

/** A live card on the home screen: checked once a day by the server. */
export interface Panel {
  id: string;
  kind: string;
  title: string;
  status: "active" | "paused" | "error" | "expired";
  spec: { travelers?: number; depart?: string | null; back?: string | null; destination?: string; assumed?: Record<string, string> };
  total: string | null;
  goal: string | null;
  goal_gap: string | null;
  goal_words: string | null;
  change: string | null;
  items: PanelItem[];
  checked_at: string | null;
  checked_today: boolean;
  next_check_at: string | null;
  /** Near the goal it is checked every this many hours (outside quiet hours); null: once a day. */
  watch_every_hours?: number | null;
  note: string;
  conversation_id: string | null;
  /** The project it belongs to (ADR-0021); shown inside that project too. */
  project_id?: string | null;
  created_at: string;
  history?: Array<{ total: string | null; checked_at: string }>;
}

export interface PanelSuggestion {
  text: string;
  draft: string;
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

  async login(email: string, password: string, signal?: AbortSignal): Promise<string> {
    // OAuth2 password form: credentials go in the body, never in the URL.
    const body = new URLSearchParams({ username: email, password });
    const data = await this.request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      signal,
    });
    this.token = data.access_token;
    return data.access_token;
  }

  /** True only on the owner's machine while nobody is signed up yet (ADR-0027). */
  async firstRunNeeded(signal?: AbortSignal): Promise<boolean> {
    const data = await this.request<{ needed: boolean }>("/auth/first-run", { signal });
    return data.needed;
  }

  /** The first account and the agent's genesis, made on the first-use screen. */
  async firstRun(email: string, password: string, signal?: AbortSignal): Promise<string> {
    const data = await this.request<{ access_token: string }>("/auth/first-run", {
      method: "POST",
      body: JSON.stringify({ email, password }),
      headers: { "Content-Type": "application/json" },
      signal,
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

  /** The project's own chat: its latest conversation, made the first time. */
  projectChat(projectId: string): Promise<Conversation> {
    return this.request(`/conversations/project/${encodeURIComponent(projectId)}`);
  }

  setProjectNotes(id: string, notes: string): Promise<Project> {
    return this.request(`/projects/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify({ notes }),
      headers: { "Content-Type": "application/json" },
    });
  }

  deleteProject(id: string): Promise<void> {
    return this.request(`/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
  }

  /** With `limit`, only the last `limit` messages (before `before`, when given), oldest first. */
  messages(conversationId: string, page?: { before?: string; limit: number }): Promise<Message[]> {
    const query = page
      ? `?${new URLSearchParams({ limit: String(page.limit), ...(page.before ? { before: page.before } : {}) })}`
      : "";
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/messages${query}`);
  }

  continuousConversation(): Promise<Conversation> {
    return this.request("/conversations/continuous");
  }

  segments(conversationId: string): Promise<Segment[]> {
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/segments`);
  }

  send(
    conversationId: string,
    content: string,
    modality: "text" | "voice" = "text",
    attachmentIds: string[] = [],
    replyToId: string | null = null,
    signal?: AbortSignal,
    location: Position | null = null,
    clientMessageId: string | null = null,
  ): Promise<Turn> {
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      signal,
      body: JSON.stringify({
        content,
        modality,
        attachment_ids: attachmentIds,
        reply_to_id: replyToId,
        ...(location ? { location } : {}),
        // Once per message: the same message sent again gets the turn already made.
        ...(clientMessageId ? { client_message_id: clientMessageId } : {}),
      }),
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

  /** The turn in flight as server-sent events (docs/decisions/0011). */
  openStream(conversationId: string, lastEventId: number | null, signal: AbortSignal): Promise<Response> {
    const headers: Record<string, string> = { Accept: "text/event-stream" };
    if (lastEventId !== null) headers["Last-Event-ID"] = String(lastEventId);
    return this.sendRaw(`/conversations/${encodeURIComponent(conversationId)}/stream`, { headers, signal });
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

  permissions(): Promise<{ auto_research: boolean; morning_briefing?: boolean }> {
    return this.request("/autonomy/permissions");
  }

  setMorningBriefing(enabled: boolean): Promise<{ auto_research: boolean; morning_briefing?: boolean }> {
    return this.request("/autonomy/permissions", {
      method: "PUT",
      body: JSON.stringify({ morning_briefing: enabled }),
      headers: { "Content-Type": "application/json" },
    });
  }

  /** The morning briefing right now (ADR-0017): the worker sends it in a few seconds. */
  briefingNow(): Promise<{ queued: boolean }> {
    return this.request("/autonomy/briefing", { method: "POST" });
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

  /** `/pc <pedido>`: the command is the approval of one session at the mouse and keyboard. */
  askDesktop(prompt: string, conversationId: string | null): Promise<ArmTask> {
    return this.request("/arm/desktop", {
      method: "POST",
      body: JSON.stringify({ prompt, conversation_id: conversationId }),
      headers: { "Content-Type": "application/json" },
    });
  }

  /** `/pc parar` or Parar: the session stops before its next action. */
  stopDesktop(): Promise<{ stopped: number }> {
    return this.request("/arm/desktop/stop", { method: "POST" });
  }

  /** `via: "voz"`: said in a call after it read the task aloud; the server records it. */
  decideArm(id: string, decision: "approve" | "reject", via: "toque" | "voz" = "toque"): Promise<ArmTask> {
    return this.request(`/arm/tasks/${encodeURIComponent(id)}/${decision}?via=${via}`, { method: "POST" });
  }

  /** The tap is the approval: the arm puts the files back without Claude. */
  undoArm(id: string): Promise<ArmTask> {
    return this.request(`/arm/tasks/${encodeURIComponent(id)}/undo`, { method: "POST" });
  }

  /** Which model the Visão thinks with, and whether the Mac offers a local one now. */
  brain(): Promise<BrainState> {
    return this.request("/arm/brain");
  }

  setBrain(mode: BrainMode): Promise<BrainState> {
    return this.request("/arm/brain", {
      method: "PUT",
      body: JSON.stringify({ mode }),
      headers: { "Content-Type": "application/json" },
    });
  }

  routing(): Promise<RoutingState> {
    return this.request("/system/llm-routing");
  }

  async skills(): Promise<Skill[]> {
    const data = await this.request<{ skills: Skill[] }>("/skills");
    return data.skills;
  }

  setSkill(id: string, enabled: boolean): Promise<Skill> {
    return this.request(`/skills/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
      headers: { "Content-Type": "application/json" },
    });
  }

  setRouting(mode: RoutingMode): Promise<RoutingState> {
    return this.request("/system/llm-routing", {
      method: "PUT",
      body: JSON.stringify({ mode }),
      headers: { "Content-Type": "application/json" },
    });
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

  apps(): Promise<AppsState> {
    return this.request("/apps");
  }

  appsCatalog(): Promise<AppCatalogItem[]> {
    return this.request("/apps/catalog");
  }

  appsConnect(slug: string): Promise<{ connection_id: string; url: string }> {
    return this.request(`/apps/${encodeURIComponent(slug)}/connect`, { method: "POST" });
  }

  /** Resolves when the owner finished signing in on Composio's page (up to two minutes). */
  appsWait(connectionId: string): Promise<AppsState> {
    return this.request(`/apps/connections/${encodeURIComponent(connectionId)}/wait`, { method: "POST" });
  }

  appsDisconnect(slug: string): Promise<void> {
    return this.request(`/apps/${encodeURIComponent(slug)}`, { method: "DELETE" });
  }

  appActions(): Promise<ToolAction[]> {
    return this.request("/apps/actions");
  }

  decideApp(id: string, decision: "approve" | "reject", via: "toque" | "voz" = "toque"): Promise<ToolAction> {
    return this.request(`/apps/actions/${encodeURIComponent(id)}/${decision}?via=${via}`, { method: "POST" });
  }

  panels(): Promise<Panel[]> {
    return this.request("/panels");
  }

  panel(id: string): Promise<Panel> {
    return this.request(`/panels/${encodeURIComponent(id)}`);
  }

  panelSuggestions(): Promise<PanelSuggestion[]> {
    return this.request("/panels/suggestions");
  }

  setPanelStatus(id: string, status: "active" | "paused"): Promise<Panel> {
    return this.request(`/panels/${encodeURIComponent(id)}`, {
      method: "PATCH", body: JSON.stringify({ status }),
      headers: { "Content-Type": "application/json" },
    });
  }

  deletePanel(id: string): Promise<void> {
    return this.request(`/panels/${encodeURIComponent(id)}`, { method: "DELETE" });
  }

  panelOffers(): Promise<PanelOffer[]> {
    return this.request("/panels/offers");
  }

  decidePanelOffer(id: string, decision: "approve" | "reject", via: "toque" | "voz" = "toque"): Promise<PanelOffer> {
    return this.request(`/panels/offers/${encodeURIComponent(id)}/${decision}?via=${via}`, { method: "POST" });
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

  memories(): Promise<MemoryItem[]> {
    return this.request("/memory");
  }

  forgetMemory(id: string): Promise<void> {
    return this.request(`/memory/${encodeURIComponent(id)}`, { method: "DELETE" });
  }

  /** Everything remembered, as the server exports it (JSON). */
  memoryExport(): Promise<unknown> {
    return this.request("/memory/export");
  }

  quietHours(): Promise<QuietHours> {
    return this.request("/notifications/settings");
  }

  setQuietHours(hours: QuietHours): Promise<QuietHours> {
    return this.request("/notifications/settings", {
      method: "PUT", body: JSON.stringify(hours),
      headers: { "Content-Type": "application/json" },
    });
  }

  /** Model use in the last `days` days (1 = the last 24 h, not the calendar day). */
  metrics(days = 1): Promise<CognitionMetrics> {
    return this.request(`/cognition/metrics?days=${days}`);
  }

  nameRecord(): Promise<NameRecord> {
    return this.request("/identity/name");
  }

  ownerGoals(): Promise<OwnerGoals> {
    return this.request("/owner-goals");
  }

  /** Undoes the newest change to the goals; `undone` says what, or null when there was none. */
  undoOwnerGoal(): Promise<{ undone: string | null }> {
    return this.request("/owner-goals/undo", { method: "POST" });
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
