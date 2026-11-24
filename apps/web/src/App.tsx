import { positionFor } from "./location";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  Api,
  ApiError,
  utcDate,
  type ArtifactSummary,
  type Attachment,
  type Bench as BenchData,
  type Conversation,
  type ProgressStep,
  type Segment,
  type Message,
  type OnboardingStatus,
  type SystemStatus,
  type VoiceStatus,
} from "./api";
import { useCallCamera } from "./call/camera";
import { CallView } from "./components/CallView";
import { type Ask, ChatView } from "./components/ChatView";
import { Intro, introAfterLogin, introDue } from "./components/Intro";
import { Login } from "./components/Login";
import { MuninnEntrance } from "./muninn/MuninnEntrance";
import { MindPanel } from "./components/MindPanel";
import { InboxView } from "./components/InboxView";
import { MacView } from "./components/MacView";
import { ProjectsView } from "./components/ProjectsView";
import { ArtifactViewer } from "./components/ArtifactCard";
import { Bench } from "./components/Bench";
import { ProjectColumn } from "./components/ProjectColumn";
import { ProjectHeader } from "./components/ProjectHeader";
import { useWide } from "./hooks/useWide";
import { useBackClose } from "./hooks/useBackClose";
import { Onboarding } from "./components/Onboarding";
import { type CallControls } from "./components/InboxView";
import { Lockup } from "./brand/Lockup";
import { Icon } from "./components/Icon";
import { PageBar, pageTitle } from "./components/PageBar";
import { Rail, type WorkspaceView } from "./components/Rail";
import { SettingsView } from "./components/SettingsView";
import { StatusBar } from "./components/StatusBar";
import { CommandPalette, type PaletteItem } from "./components/CommandPalette";
import { NotYetView } from "./components/NotYetView";
import { RoutinesView } from "./components/RoutinesView";
import { PanelView } from "./components/PanelView";
import { ShareDialog, Toast } from "./components/ShareDialog";
import type { ToolsMode } from "./components/ChatView";
import { useRoutines } from "./hooks/useRoutines";
import { saveTheme, THEMES } from "./brand/theme";
import { MicButton, MobileBar } from "./components/SkyNav";
import { StudyPanel } from "./components/StudyPanel";
import { usePending } from "./hooks/usePending";
import { type SpokenTiming, useVoice } from "./hooks/useVoice";
import { Anel } from "./anel/Anel";
import { ANEL_ESTADOS, ANEL_LABELS, type AnelEstado, type AssistantState, anelEstado } from "./anel/state";
import { parseMacCommand } from "./arm";
import { registerWorker, syncSubscription } from "./push";
import { loadPreference, loadToken, savePreference, saveToken } from "./session";
import { AmbientBackground } from "./brand/AmbientBackground";
import { heardVerdict, type SpokenAsk, spokenArm, spokenGoogle, spokenPanelOffer, VOICE_ANSWER_MS } from "./voice/approval";
import { followTurn } from "./stream";
import { MAX_FILES } from "./attachments";

interface TurnLatency {
  sttMs: number;
  llmMs: number;
  ttsFirstAudioMs: number | null;
  /** End of the user's speech to the first audio of the reply. */
  totalMs: number | null;
}

const HEALTH_INTERVAL_MS = 15_000;
// The continuous conversation loads backwards, this many messages at a time.
const MESSAGES_PAGE = 100;
// An installed app on the phone is resumed, not reloaded, so the sync also runs on return.
const PUSH_SYNC_MS = 60 * 60 * 1000;
const INITIATIVE_POLL_MS = 15_000;
const PROGRESS_POLL_MS = 900;
const ARTIFACT_POLL_MS = 3000;

function useHealth(api: Api): boolean {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    let alive = true;
    const check = () => api.health().then(() => alive && setOnline(true), () => alive && setOnline(false));
    check();
    const id = setInterval(check, HEALTH_INTERVAL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [api]);
  return online;
}

/** Fake audio level for the demo page, so LISTENING/SPEAKING can be previewed without voice. */
function useDemoLevel(active: boolean): number {
  const [level, setLevel] = useState(0);
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => {
      const t = performance.now() / 1000;
      setLevel(Math.max(0, Math.sin(t * 7) * Math.sin(t * 2.3)));
    }, 50);
    return () => clearInterval(id);
  }, [active]);
  return active ? level : 0;
}

/** A conversation id the app was opened with: from a push notification (`/?c=<id>`). */
function requestedConversation(): string | null {
  return new URLSearchParams(window.location.search).get("c");
}

/** One per message sent, so the server runs its turn once even if it arrives twice. */
function messageId(): string | null {
  return typeof crypto !== "undefined" && typeof crypto.randomUUID === "function" ? crypto.randomUUID() : null;
}

type LiveAsk = Ask & {
  spoken: SpokenAsk;
  decide: (decision: "approve" | "reject", via: "toque" | "voz") => Promise<boolean>;
};

export function App() {
  const api = useMemo(() => {
    const instance = new Api();
    instance.setToken(loadToken());
    return instance;
  }, []);
  const online = useHealth(api);
  const demo = new URLSearchParams(window.location.search).get("orb") === "demo";

  const [loggedIn, setLoggedIn] = useState(api.authenticated);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [memoryEnabled, setMemoryEnabled] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [current, setCurrent] = useState<string | null>(requestedConversation);
  const [messages, setMessages] = useState<Message[]>([]);
  // The continuous conversation (docs/CONVERSA_CONTINUA.md): its stretches, and older pages.
  const [segments, setSegments] = useState<Segment[]>([]);
  const [olderLeft, setOlderLeft] = useState(false);
  const [sending, setSending] = useState(false);
  const [composerFocus, setComposerFocus] = useState(0);
  const [preparing, setPreparing] = useState(false);
  const [memoryWarning, setMemoryWarning] = useState<string | null>(null);
  const [onboarding, setOnboarding] = useState<OnboardingStatus | "checking" | "done">("checking");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  /** The command palette (Ctrl/⌘+K). */
  const [palette, setPalette] = useState(false);
  /** The share dialog of the conversation in front. */
  const [share, setShare] = useState(false);
  /** The short confirmation at the bottom (an export, a copied link). */
  const [toast, setToast] = useState<string | null>(null);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 3200);
    return () => clearTimeout(timer);
  }, [toast]);
  /** How the tool steps show in the chat (Ajustes › Aparência). */
  const [toolsMode, setToolsMode] = useState<ToolsMode>(() => (loadPreference("tools") === "tecnico" ? "tecnico" : "resumo"));
  /** The "Agora / O que fiz de verdade" column beside the chat. */
  const [benchOpen, setBenchOpen] = useState(() => loadPreference("bench") !== "0");
  // The opening animation, once a day (components/Intro.tsx).
  // `?intro` in the address plays it again on demand (to see it).
  const [intro, setIntro] = useState(() => introDue() || new URLSearchParams(window.location.search).has("intro"));
  const endIntro = useCallback(() => setIntro(false), []);
  // A notification about Mac work opens the list of what waits for a yes (`/?mac=1`).
  const [view, setView] = useState<WorkspaceView>(() =>
    new URLSearchParams(window.location.search).get("mac") ? "inbox" : "conversation",
  );
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null);
  const [speakReplies, setSpeakReplies] = useState(() => loadPreference("speak") === "1");
  const [deviceListening, setDeviceListening] = useState(() => loadPreference("device-listening") === "1");
  // Measured each turn; shown in no screen of this brand (kept for whoever reads it later).
  const [, setLatency] = useState<TurnLatency | null>(null);
  const [demoState, setDemoState] = useState<AnelEstado>("ocioso");
  // The login is checking the credentials: the ring on the entrance shows "pensando".
  const [loginBusy, setLoginBusy] = useState(false);
  const demoLevel = useDemoLevel(demo && demoState === "ouvindo");
  const sendingRef = useRef(false);
  const queueRef = useRef<{ id: string; text: string; files: Attachment[]; replyTo: Message | null }[]>([]);
  // What the turn in flight is doing now, shown in place of "Pensando".
  const [liveStep, setLiveStep] = useState<ProgressStep | null>(null);
  /** The reply as the stream has written it so far (null: no reply on the way). */
  const [liveText, setLiveText] = useState<string | null>(null);
  /** The reply that arrived while its text is still coming in on screen. */
  const [settling, setSettling] = useState<string | null>(null);
  /** Text a suggestion or "Criar um novo painel" puts in the message box. */
  const [draftRequest, setDraftRequest] = useState<{ text: string; n: number } | null>(null);
  const draftInChat = (text: string) => {
    setDraftRequest((d) => ({ text, n: (d?.n ?? 0) + 1 }));
    setView("conversation");
  };
  const [liveSteps, setLiveSteps] = useState<ProgressStep[]>([]);
  // On a computer: three columns, and pages open beside the chat instead of over it.
  const wide = useWide(1280);
  useBackClose(menuOpen, () => setMenuOpen(false));
  const [bench, setBench] = useState<BenchData | null>(null);
  const [sidePage, setSidePage] = useState<ArtifactSummary | null>(null);
  const turnRef = useRef<{ conversationId: string; controller: AbortController } | null>(null);
  const messagesRef = useRef<Message[]>([]);
  sendingRef.current = sending;
  messagesRef.current = messages;
  const conversationsRef = useRef<Conversation[]>([]);
  // Project names for the bar on top of a project's chat.
  const [projectNames, setProjectNames] = useState<Record<string, string>>({});
  const [projectsKey, setProjectsKey] = useState(0);
  const [lastProject, setLastProject] = useState<string | null>(null);
  conversationsRef.current = conversations;

  // The continuous conversation loads only its last page (and as many as are already shown);
  // the others load whole, as before.
  const loadMessages = useCallback((id: string): Promise<Message[]> => {
    const continuous = conversationsRef.current.find((c) => c.id === id)?.continuous;
    if (!continuous) return loadMessages(id);
    const shown = messagesRef.current.filter((m) => !m.local).length;
    return api.messages(id, { limit: Math.max(MESSAGES_PAGE, shown) });
  }, [api]);

  const handleError = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401) {
      saveToken(null);
      setLoggedIn(false);
      return;
    }
    setError(e instanceof Error ? e.message : String(e));
  }, []);

  const sendRef = useRef<(text: string, spoken?: SpokenTiming, files?: Attachment[], replyTo?: Message | null) => Promise<void>>(async () => undefined);
  const reloadRef = useRef<() => void>(() => undefined);
  const heardRef = useRef<(text: string, spoken: SpokenTiming) => Promise<void>>(async () => undefined);
  const voice = useVoice({
    api,
    status: voiceStatus,
    deviceListening,
    // In a call, a clear "pode mandar" or "não" answers the action it just read aloud.
    onTranscript: (text, timing) => heardRef.current(text, timing),
    onError: setError,
  });

  const camera = useCallCamera(voice.inCall);

  const firstRun = loggedIn && !demo && onboarding !== "done";
  const ready = loggedIn && !demo && !firstRun && status?.genesis_completed !== false;
  const pending = usePending(api, ready, handleError, ready && view === "conversation");
  const routines = useRoutines(api, ready, handleError);

  // Ctrl/⌘+K opens the palette anywhere in the app.
  useEffect(() => {
    if (!ready) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ready]);

  useEffect(() => {
    void registerWorker();
    // A tap on a notification while the app is open: jump to that conversation.
    const onMessage = (event: MessageEvent) => {
      if (event.data?.type !== "visao.open") return;
      const params = new URL(event.data.url, window.location.origin).searchParams;
      if (params.get("mac")) setView("inbox");
      const id = params.get("c");
      if (id) {
        setView("conversation");
        setCurrent(id);
      }
    };
    navigator.serviceWorker?.addEventListener("message", onMessage);
    return () => navigator.serviceWorker?.removeEventListener("message", onMessage);
  }, []);

  // Keeps this device's avisos alive on the server (see syncSubscription). Silent on failure:
  // the switch in Ajustes shows what happened to the last aviso.
  useEffect(() => {
    if (!loggedIn || demo) return;
    let last = 0;
    const sync = () => {
      if (document.visibilityState !== "visible" || Date.now() - last < PUSH_SYNC_MS) return;
      last = Date.now();
      syncSubscription(api).catch(() => undefined);
    };
    sync();
    document.addEventListener("visibilitychange", sync);
    return () => document.removeEventListener("visibilitychange", sync);
  }, [api, loggedIn, demo]);

  useEffect(() => {
    if (!loggedIn) return;
    api.voiceStatus().then(setVoiceStatus, () => setVoiceStatus(null));
    // The continuous conversation is made the first time it is asked for, then opened by default.
    Promise.all([api.status(), api.memorySettings(), api.continuousConversation().catch(() => null)])
      .then(async ([s, memory, continuous]) => {
        const list = await api.listConversations();
        setStatus(s);
        setMemoryEnabled(memory.enabled);
        setConversations(list);
        conversationsRef.current = list;
        setCurrent((c) => (c && list.some((x) => x.id === c) ? c : continuous?.id ?? list[0]?.id ?? null));
      })
      .catch(handleError);
  }, [api, loggedIn, handleError]);

  // Whoever has not finished or skipped the first run sees it instead of the workspace. If this
  // check fails the app still opens, with the error visible, and asks again on the next login.
  useEffect(() => {
    if (!loggedIn || demo) return;
    let alive = true;
    api.onboarding().then(
      (next) => { if (alive) setOnboarding(next.completed ? "done" : next); },
      (e) => { if (alive) { handleError(e); setOnboarding("done"); } },
    );
    return () => { alive = false; setOnboarding("checking"); };
  }, [api, loggedIn, demo, handleError]);

  // Identity decisions happen in the background; reflect them without reloading the page.
  useEffect(() => {
    if (!loggedIn || demo) return;
    let alive = true;
    const timer = setInterval(() => {
      api.status().then((next) => { if (alive) setStatus(next); }).catch(() => undefined);
    }, HEALTH_INTERVAL_MS);
    return () => { alive = false; clearInterval(timer); };
  }, [api, loggedIn, demo]);

  useEffect(() => {
    if (!current || !loggedIn) {
      setMessages([]);
      return;
    }
    // A conversation opened by sending its first message is filled by that send, not by this
    // load (which would race it and hide the message that is showing).
    if (sendingRef.current) return;
    const continuous = conversationsRef.current.find((c) => c.id === current)?.continuous;
    (continuous ? api.messages(current, { limit: MESSAGES_PAGE }) : api.messages(current))
      .then((list) => {
        setMessages(list);
        setOlderLeft(!!continuous && list.length >= MESSAGES_PAGE);
      })
      .catch(handleError);
    if (continuous) api.segments(current).then(setSegments, () => setSegments([]));
    else setSegments([]);
  }, [api, current, loggedIn, handleError, conversations.length]);

  async function loadOlder() {
    const first = messagesRef.current.find((m) => !m.local);
    if (!current || !first) return;
    try {
      const page = await api.messages(current, { before: first.id, limit: MESSAGES_PAGE });
      setMessages((list) => [...page.filter((m) => !list.some((x) => x.id === m.id)), ...list]);
      setOlderLeft(page.length >= MESSAGES_PAGE);
    } catch (e) {
      handleError(e);
    }
  }

  const loadAttachment = useCallback((id: string) => api.attachmentBlob(id), [api]);

  // A page being written: ask about it until it is ready (only while you look, so the server
  // knows to notify you otherwise).
  // What waits for a yes in this conversation: cards in the chat, and read aloud in a call.
  const liveAsks: LiveAsk[] = [
    ...pending.armProposals
      .filter((t) => t.conversation_id === current)
      .map((t) => ({
        id: t.id,
        label: `Mac · ${t.project}`,
        text: t.prompt,
        onApprove: () => void pending.decideArm(t, "approve"),
        onReject: () => void pending.decideArm(t, "reject"),
        spoken: spokenArm(t),
        decide: (d: "approve" | "reject", via: "toque" | "voz") => pending.decideArm(t, d, via),
      })),
    ...pending.googleActions
      .filter((a) => a.conversation_id === current)
      .map((a) => ({
        id: a.id,
        label: a.kind === "send_email" ? "Email" : "Agenda",
        text: a.summary,
        detail: a.kind === "send_email" ? a.payload.body : undefined,
        onApprove: () => void pending.decideGoogle(a, "approve").then(() => reloadRef.current()),
        onReject: () => void pending.decideGoogle(a, "reject"),
        spoken: spokenGoogle(a),
        decide: (d: "approve" | "reject", via: "toque" | "voz") =>
          pending.decideGoogle(a, d, via).then((ok) => {
            if (ok && d === "approve") reloadRef.current();
            return ok;
          }),
      })),
    ...pending.panelOffers
      .filter((o) => o.conversation_id === current)
      .map((o) => ({
        id: o.id,
        label: "Painel no Início",
        text: o.summary,
        onApprove: () => void pending.decidePanelOffer(o, "approve").then(() => reloadRef.current()),
        onReject: () => void pending.decidePanelOffer(o, "reject"),
        spoken: spokenPanelOffer(o),
        decide: (d: "approve" | "reject", via: "toque" | "voz") =>
          pending.decidePanelOffer(o, d, via).then((ok) => {
            if (ok && d === "approve") reloadRef.current();
            return ok;
          }),
      })),
  ];
  const liveAsksRef = useRef(liveAsks);
  liveAsksRef.current = liveAsks;
  const askedRef = useRef<{ ask: LiveAsk; at: number } | null>(null);
  const announcedRef = useRef(new Set<string>());
  const [voiceApproval, setVoiceApproval] = useState(() => loadPreference("voice-approval") !== "0");
  const askIds = liveAsks.map((a) => a.id).join(",");
  // In a call, once it stops talking, it reads each new action aloud and waits for a yes.
  useEffect(() => {
    if (!voice.inCall) {
      askedRef.current = null;
      return;
    }
    if (!voiceApproval || sending || voice.speaking) return;
    const next = liveAsksRef.current.find((a) => !announcedRef.current.has(a.id));
    if (!next) return;
    announcedRef.current.add(next.id);
    askedRef.current = { ask: next, at: Date.now() };
    voice.speak(next.spoken.question);
  }, [voice.inCall, voice.speaking, voiceApproval, sending, askIds]);
  heardRef.current = async (text, timing) => {
    const asked = askedRef.current;
    const stillWaiting = asked && liveAsksRef.current.some((a) => a.id === asked.ask.id);
    if (asked && stillWaiting && voice.inCall && voiceApproval && Date.now() - asked.at < VOICE_ANSWER_MS) {
      const verdict = heardVerdict(text);
      if (verdict) {
        askedRef.current = null;
        const ok = await asked.ask.decide(verdict, "voz");
        voice.speak(!ok ? "Não consegui agora. Ficou esperando você na tela." : verdict === "approve" ? asked.ask.spoken.done : "Tudo bem, não fiz.");
        return;
      }
    }
    // Camera on: the picture of this moment goes with the sentence (the words still go without it).
    const photo = camera.on ? await camera.snapshot() : null;
    let files: Attachment[] = [];
    if (photo) {
      try {
        files = [await api.uploadAttachment(photo, `camera-${Date.now()}.jpg`)];
      } catch {
        files = [];
      }
    }
    await sendRef.current(text, timing, files);
  };

  const pendingPages = messages.filter((m) => m.artifact?.status === "pending").map((m) => m.artifact!.id).join(",");
  useEffect(() => {
    if (!pendingPages) return;
    const ids = pendingPages.split(",");
    const check = () => {
      if (document.hidden) return;
      ids.forEach((id) => {
        api.artifact(id).then((fresh) => {
          if (fresh.status === "pending") return;
          setMessages((list) => list.map((m) => (m.artifact?.id === id ? { ...m, artifact: fresh } : m)));
        }).catch(() => undefined);
      });
    };
    const timer = window.setInterval(check, ARTIFACT_POLL_MS);
    return () => clearInterval(timer);
  }, [api, pendingPages]);

  // The Bancada follows the open conversation: after each turn and when a page gets ready.
  const desk = wide;
  const pageStates = messages.map((m) => m.artifact?.status ?? "").join(",");
  useEffect(() => {
    if (!desk || !current || sending) return;
    let alive = true;
    api.bench(current).then((b) => { if (alive) setBench(b); }).catch(() => undefined);
    return () => { alive = false; };
  }, [api, desk, current, sending, pageStates]);
  useEffect(() => setSidePage(null), [current]);

  async function deleteArtifact(artifact: ArtifactSummary) {
    try {
      await api.deleteArtifact(artifact.id);
      setMessages((list) => list.map((m) => (m.artifact?.id === artifact.id ? { ...m, artifact: null } : m)));
      setSidePage((page) => (page?.id === artifact.id ? null : page));
    } catch (e) {
      handleError(e);
    }
  }

  const speakAloud = speakReplies || voice.inCall;
  const speakRef = useRef<((text: string) => void) | null>(null);
  speakRef.current = speakAloud && voice.speakerKind ? (text) => voice.speak(text) : null;

  // It can speak first: pick up what it said on its own, and say it aloud in a call.
  useEffect(() => {
    if (!current || !loggedIn || demo) return;
    let alive = true;
    const timer = setInterval(() => {
      if (sendingRef.current) return;
      loadMessages(current).then((next) => {
        if (!alive || sendingRef.current) return;
        const known = new Set(messagesRef.current.map((m) => m.id));
        // What it says on its own, and the arm's reports, are read aloud in a call.
        const fresh = next.filter((m) => m.role === "assistant" && (m.origin === "initiative" || m.origin === "arm") && !known.has(m.id));
        const unsent = messagesRef.current.filter((m) => m.local === "failed" || m.local === "queued");
        if (next.length !== messagesRef.current.length - unsent.length) setMessages([...next, ...unsent]);
        const last = fresh[fresh.length - 1];
        if (last && known.size > 0 && speakRef.current) speakRef.current(last.content);
      }).catch(() => undefined);
    }, INITIATIVE_POLL_MS);
    return () => { alive = false; clearInterval(timer); };
  }, [api, current, loggedIn, demo]);

  function checkMemoryPreparation(conversation: Conversation) {
    setMemoryWarning(
      conversation.memory_status === "failed" || conversation.memory_status === "unavailable"
        ? "Não consegui preparar a memória desta vez. Dá para conversar, mas posso esquecer detalhes."
        : null,
    );
  }

  /** A project's new conversation; without a project, the continuous one (there is no other). */
  async function openConversation(projectId?: string | null): Promise<string> {
    if (!projectId) {
      const continuous = await api.continuousConversation();
      setConversations((list) => (list.some((c) => c.id === continuous.id) ? list : [continuous, ...list]));
      setCurrent(continuous.id);
      return continuous.id;
    }
    const conversation = await api.createConversation(projectId);
    checkMemoryPreparation(conversation);
    setConversations((list) => [conversation, ...list]);
    setCurrent(conversation.id);
    return conversation.id;
  }

  async function askMac(command: { project: string; prompt: string }): Promise<void> {
    setSending(true);
    try {
      const conversationId = current ?? (await openConversation());
      await api.askArm(command.project, command.prompt, conversationId);
      setMessages(await loadMessages(conversationId));
    } catch (e) {
      handleError(e);
    } finally {
      setSending(false);
    }
  }

  async function send(text: string, spoken?: SpokenTiming, files: Attachment[] = [], replyTo: Message | null = null): Promise<void> {
    setError(null);
    const quote = replyTo ? { id: replyTo.id, role: replyTo.role, excerpt: replyTo.content.replace(/\s+/g, " ").slice(0, 160) } : null;
    if (sendingRef.current) {
      // Still answering: what you add now shows at once, dimmed, and goes with the next turn.
      const queuedId = `queued-${Date.now()}-${queueRef.current.length}`;
      queueRef.current.push({ id: queuedId, text, files, replyTo });
      setMessages((list) => [
        ...list,
        { id: queuedId, role: "user", content: text, created_at: new Date().toISOString(), attachments: files, reply_to: quote, local: "queued" },
      ]);
      return;
    }
    const mac = spoken || files.length ? null : parseMacCommand(text);
    if (mac === "usage") {
      setError("Use assim: /mac projeto o que fazer (ex.: /mac visao rode os testes).");
      return;
    }
    if (mac) {
      await askMac(mac);
      return;
    }
    voice.stopSpeaking(); // barge-in by text
    const willSpeak = (spoken !== undefined || speakAloud) && voice.speakerKind !== null;
    if (willSpeak) voice.unlock(); // inside the gesture, before any await
    let conversationId = current;
    // What you sent shows at once, before the reply; the server's copy replaces it.
    const localId = `local-${Date.now()}`;
    const optimistic: Message = {
      id: localId,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
      attachments: files,
      reply_to: quote,
      local: "sending",
    };
    setMessages((list) => [...list, optimistic]);
    setSending(true);
    navigator.vibrate?.(6);
    let watch = 0;
    let streamStop: AbortController | null = null;
    let hidden: (() => void) | null = null;
    try {
      conversationId ??= await openConversation();
      const watching = conversationId;
      // Polled only while you look, and only when the stream is not there: when the phone
      // locks, the server sees it and also sends the reply as a notification.
      const look = () => {
        if (document.hidden) return;
        api.progress(watching).then((p) => {
          const last = p.steps[p.steps.length - 1];
          if (p.active && last) setLiveStep(last);
          if (p.active) setLiveSteps(p.steps);
        }).catch(() => undefined);
      };
      const poll = () => {
        if (watch) return;
        look();
        watch = window.setInterval(look, PROGRESS_POLL_MS);
      };
      // The reply as it is written (docs/decisions/0011). A tab going to the background drops
      // it (so the server knows nobody is looking) and the polling above takes over.
      streamStop = new AbortController();
      const stop = streamStop;
      const steps: ProgressStep[] = [];
      let written = "";
      setLiveText("");
      followTurn(
        (last, signal) => api.openStream(watching, last, signal),
        (event) => {
          const data = (event.data ?? {}) as { label?: string; detail?: string | null; text?: string };
          if (event.kind === "step" && data.label) {
            const step = { label: data.label, detail: data.detail ?? null };
            steps.push(step);
            setLiveStep(step);
            setLiveSteps([...steps]);
          } else if (event.kind === "delta" && data.text) {
            written += data.text;
            setLiveText(written);
          } else if (event.kind === "replace" && typeof data.text === "string") {
            written = data.text;
            setLiveText(written);
          } else if (event.kind === "action") {
            pending.refresh();
          }
        },
        stop.signal,
      ).then(
        (end) => {
          if (end === "empty" && !stop.signal.aborted) poll();
        },
        () => {
          if (!stop.signal.aborted || document.hidden) poll();
        },
      );
      hidden = () => {
        if (document.hidden) stop.abort();
      };
      document.addEventListener("visibilitychange", hidden);
      const llmStarted = performance.now();
      const controller = new AbortController();
      turnRef.current = { conversationId, controller };
      // Only for "near here" questions with the switch on (docs/LOCALIZACAO.md); never stored.
      const where = await positionFor(text);
      const turn = await api.send(conversationId, text, spoken ? "voice" : "text", files.map((f) => f.id), replyTo?.id ?? null, controller.signal, where, messageId());
      const llmMs = performance.now() - llmStarted;
      streamStop?.abort();
      // The bubble that was writing becomes the reply: its text finishes coming in, then it is
      // the message itself (ChatView), without a jump.
      setLiveText(turn.assistant_message.content);
      setSettling(turn.assistant_message.id);
      setMessages((list) => [
        ...list.filter((m) => m.id !== localId && m.local !== "queued"),
        turn.user_message,
        { ...turn.assistant_message, sources: turn.sources, streamed: true },
        // What was written while it answered stays below the reply, waiting its turn.
        ...list.filter((m) => m.local === "queued"),
      ]);
      pending.refresh(); // a request for the Mac may be waiting for a tap now
      // The worker writes the conversation's title a few seconds after the first reply.
      window.setTimeout(() => api.listConversations().then(setConversations, () => undefined), 12_000);
      if (spoken) setLatency({ sttMs: spoken.sttMs, llmMs, ttsFirstAudioMs: null, totalMs: null });
      if (willSpeak) {
        const ttsStarted = performance.now();
        voice.speak(turn.assistant_message.content, () => {
          if (!spoken) return;
          const now = performance.now();
          const measured = { sttMs: spoken.sttMs, llmMs, ttsFirstAudioMs: now - ttsStarted, totalMs: now - spoken.endedAt };
          setLatency(measured);
          console.info("visao.turn_latency", JSON.stringify(measured));
        });
      }
    } catch (e) {
      const stopped = (e instanceof DOMException && e.name === "AbortError") || (e instanceof ApiError && e.status === 409 && e.message === "Parado por você");
      if (!stopped) handleError(e);
      setLiveText(null);
      setSettling(null);
      const mark: Message["local"] = stopped ? "stopped" : "failed";
      setMessages((list) => list.map((m) => (m.id === localId ? { ...m, local: mark } : m)));
      // The user message may have been stored even if the reply failed: reload the transcript,
      // keeping the one that never arrived visible so it is not silently lost.
      if (conversationId) {
        const id = conversationId;
        api
          .messages(id)
          .then((stored) => {
            const last = stored.filter((m) => m.role === "user").at(-1);
            const arrived = last !== undefined && last.content === text && utcDate(last.created_at) >= utcDate(optimistic.created_at);
            setMessages((list) => [
              ...(arrived ? stored : [...stored, { ...optimistic, local: mark }]),
              ...list.filter((m) => m.local === "queued"),
            ]);
          })
          .catch(() => undefined);
      }
    } finally {
      turnRef.current = null;
      streamStop?.abort();
      if (hidden) document.removeEventListener("visibilitychange", hidden);
      clearInterval(watch);
      setLiveStep(null);
      setLiveSteps([]);
      setSending(false);
    }
  }
  sendRef.current = send;

  /** Parar: tell the server, and stop waiting at once. */
  function stopTurn() {
    const turn = turnRef.current;
    if (!turn) return;
    api.cancel(turn.conversationId).catch(() => undefined);
    turn.controller.abort();
  }

  // When the reply arrives, everything written meanwhile goes as one message: one answer to all
  // of it, not one per line.
  useEffect(() => {
    if (sending || queueRef.current.length === 0) return;
    const batch = queueRef.current.splice(0);
    const ids = new Set(batch.map((q) => q.id));
    setMessages((list) => list.filter((m) => !ids.has(m.id)));
    const text = batch.map((q) => q.text).filter(Boolean).join("\n\n");
    const files = batch.flatMap((q) => q.files).slice(0, MAX_FILES);
    void sendRef.current?.(text, undefined, files, batch.find((q) => q.replyTo)?.replyTo ?? null);
  }, [sending]);

  // A queue belongs to the conversation it was typed in.
  useEffect(() => {
    queueRef.current = [];
  }, [current]);

  async function sendFeedback(messageId: string, rating: 1 | -1, tags: string[]): Promise<string | null> {
    try {
      const result = await api.feedback(messageId, rating, tags);
      return result.state_changed ? "Valeu. Ajustei meu jeito de responder." : "Valeu.";
    } catch (e) {
      handleError(e);
      return null;
    }
  }

  async function toggleMemory() {
    try {
      setMemoryEnabled((await api.setMemoryEnabled(!memoryEnabled)).enabled);
    } catch (e) {
      handleError(e);
    }
  }

  function toggleSpeak() {
    const next = !speakReplies;
    setSpeakReplies(next);
    savePreference("speak", next ? "1" : "0");
    if (next) voice.unlock();
    else voice.stopSpeaking();
  }

  function toggleDeviceListening() {
    const next = !deviceListening;
    setDeviceListening(next);
    savePreference("device-listening", next ? "1" : "0");
  }

  function logout() {
    voice.endCall();
    voice.stopSpeaking();
    api.setToken(null);
    saveToken(null);
    setLoggedIn(false);
    setConversations([]);
    setCurrent(null);
  }

  function showView(next: WorkspaceView) {
    setView(next);
    setMenuOpen(false);
  }

  /** A project's own chat (made the first time), from the project page. */
  async function openProjectChat(projectId: string) {
    if (preparing) return;
    setPreparing(true);
    try {
      const chat = await api.projectChat(projectId);
      setConversations((list) => (list.some((c) => c.id === chat.id) ? list : [chat, ...list]));
      setCurrent(chat.id);
      setLastProject(projectId);
      showView("conversation");
    } catch (e) {
      handleError(e);
    } finally {
      setPreparing(false);
    }
  }

  /** "Conversa" in the menu: the continuous conversation (a project's chats open from Projetos). */
  function openChat() {
    const continuous = conversationsRef.current.find((c) => c.continuous);
    if (continuous) setCurrent(continuous.id);
    showView("conversation");
  }

  const orbState: AssistantState = demo
    ? "IDLE"
    : !online
      ? "DISCONNECTED"
      : sending || voice.transcribing
        ? "THINKING"
        : voice.interrupted
          ? "INTERRUPTED"
          : voice.speaking
            ? "SPEAKING"
            : voice.inCall
              ? "LISTENING"
              : "IDLE";
  // What the ring shows (DESIGN.md §6): the state above, plus Mac work, a yes waiting, the pause
  // and an unread opening.
  const macWorking = pending.tasks.some((t) => t.status === "running");
  const anel: AnelEstado = demo
    ? demoState
    : anelEstado({ state: orbState, macWorking, approvals: pending.approvals, opening: pending.opening, paused: pending.paused });
  const agentName = status?.identity?.chosen_name ?? null;
  const callHint = voice.listenerKind
    ? null
    : voice.deviceCouldListen
      ? "Para ligar daqui, ligue Ouvir pelo navegador."
      : "Este navegador não consegue me ouvir. Dá para escrever.";

  const call: CallControls = {
    state: orbState,
    anel,
    level: voice.level,
    levelActive: voice.speaking || voice.inCall,
    canCall: voice.listenerKind !== null && online,
    speaking: voice.speaking,
    inCall: voice.inCall,
    hint: callHint,
    onCall: () => { setError(null); void voice.startCall(); },
    onStopSpeaking: voice.stopSpeaking,
    onOpenSettings: () => showView("settings"),
  };
  const currentConversation = conversations.find((c) => c.id === current);
  const currentProjectId = currentConversation?.project_id ?? null;
  // Names for "abrir o projeto «…»", listed again when a reply points to one not known yet.
  const linkedUnknown = messages.some((m) => m.project_id && !projectNames[m.project_id]);
  useEffect(() => {
    if (!loggedIn) return;
    api.projects().then(
      (list) => setProjectNames(Object.fromEntries(list.map((p) => [p.id, p.name]))),
      () => undefined,
    );
  }, [api, loggedIn, projectsKey, linkedUnknown]);
  // In a project's chat: its card on top (name, notes, panels, files) and the way back.
  const inProject = view === "conversation" ? currentProjectId : null;
  const projectBar = inProject ? (
    <ProjectHeader
      api={api}
      projectId={inProject}
      refreshKey={messages.length + projectsKey}
      showBack={!desk}
      onBack={() => showView("projects")}
      onDeleted={() => {
        setConversations((list) => list.map((c) => (c.project_id === inProject ? { ...c, project_id: null } : c)));
        setLastProject(null);
        setProjectsKey((k) => k + 1);
        openChat();
      }}
      onRenamed={(name) => {
        setProjectNames((names) => ({ ...names, [inProject]: name }));
        setProjectsKey((k) => k + 1);
      }}
      onError={handleError}
    />
  ) : null;
  /** The pill and the menu: "Chat" is the main conversation; "Projetos" on a computer goes back
   * to the last project's chat (the list is beside it), on a phone to the list. */
  function go(next: WorkspaceView) {
    if (next === "conversation") return openChat();
    if (next === "projects" && desk && lastProject) return void openProjectChat(lastProject);
    showView(next);
  }

  const paletteItems: PaletteItem[] = [
    { id: "go-inbox", group: "Ações", icon: "home", label: "Ir para o Início", run: () => go("inbox") },
    { id: "new-chat", group: "Ações", icon: "plus", label: "Nova conversa", keywords: "chat", run: openChat },
    ...(call.canCall ? [{ id: "call", group: "Ações" as const, icon: "phone" as const, label: "Ligar para ele", keywords: "voz", run: call.onCall }] : []),
    { id: "mac", group: "Ações", icon: "laptop", label: "Pedir ao Mac…", keywords: "braço", run: () => go("mac") },
    { id: "study", group: "Ações", icon: "notebook", label: "Caderno", keywords: "memória pensamentos interesses nome autorretrato", run: () => go("study") },
    { id: "routines", group: "Ações", icon: "clock", label: "Rotinas", run: () => go("routines") },
    { id: "panel", group: "Ações", icon: "coin", label: "Painel", keywords: "preço meta gráfico", run: () => go("panel") },
    { id: "agents", group: "Ações", icon: "agents", label: "Ver agentes em paralelo", run: () => go("agents") },
    { id: "channels", group: "Ações", icon: "plug", label: "Canais: Telegram, e-mail…", keywords: "whatsapp discord", run: () => go("channels") },
    { id: "skills", group: "Ações", icon: "sparkle", label: "Habilidades", run: () => go("skills") },
    ...(view === "conversation" && current ? [{ id: "share", group: "Ações" as const, icon: "share" as const, label: "Compartilhar esta conversa", keywords: "exportar markdown pdf", run: () => setShare(true) }] : []),
    ...THEMES.map((t) => ({ id: `theme-${t.value}`, group: "Ações" as const, icon: "sliders" as const, label: `Tema ${t.label}`, keywords: "aparência cor", run: () => { saveTheme(t.value); } })),
    {
      id: "pause", group: "Ações", icon: "gear",
      label: pending.paused ? "Retomar o que ele faz sozinho" : "Pausar tudo que ele faz sozinho",
      keywords: "autonomia",
      run: () => {
        const next = !pending.paused;
        pending.setPaused(next);
        api.setAutonomyPaused(next).catch((e) => { pending.setPaused(!next); handleError(e); });
      },
    },
    { id: "settings", group: "Ações", icon: "gear", label: "Ajustes", run: () => go("settings") },
    ...conversations
      .filter((c) => !c.continuous && c.title)
      .map((c) => ({ id: `c-${c.id}`, group: "Conversas" as const, icon: "chat" as const, label: c.title ?? "", run: () => { setCurrent(c.id); showView("conversation"); } })),
    ...Object.entries(projectNames).map(([id, name]) => ({ id: `p-${id}`, group: "Projetos" as const, icon: "folder" as const, label: name, run: () => void openProjectChat(id) })),
  ];

  const reload = () => { if (current) loadMessages(current).then(setMessages).catch(handleError); };
  reloadRef.current = reload;
  const macOnline = pending.devices.length ? pending.devices.some((d) => d.online) : null;

  return (
    <div className={`app${desk && ready && !firstRun ? " app--mesa" : ""}${!ready && !firstRun ? " app--entrada" : ""}`}>
      {(loggedIn || demo) && <AmbientBackground />}
      {intro && ready && !firstRun && !demo && <Intro onDone={endIntro} />}
      {ready && !firstRun && (
        <MobileBar
          pendingCount={pending.count}
          anel={anel}
          menuOpen={menuOpen}
          onMenu={() => setMenuOpen((o) => !o)}
          view={inProject ? "projects" : view}
          onView={go}
        />
      )}
      {(firstRun || (loggedIn && !demo && !ready)) && (
        <header className="topbar">
          <Lockup />
          {loggedIn && !demo && !ready && (
            <button type="button" className="rs-botao rs-botao--compacto" onClick={logout}>Sair</button>
          )}
        </header>
      )}

      {firstRun && (
        <main className="main onboarding-main">
          {onboarding !== "checking" && (
            <Onboarding
              api={api}
              status={onboarding}
              onMemoryChange={setMemoryEnabled}
              onError={handleError}
              onDone={(message) => {
                setNotice(message);
                setOnboarding("done");
              }}
            />
          )}
        </main>
      )}

      {!firstRun && ready && (
        <div className="layout">
          <Rail
            open={menuOpen}
            view={inProject ? "projects" : view}
            preparing={preparing}
            online={online}
            pendingCount={pending.count}
            conversations={conversations}
            currentConversation={current}
            onView={go}
            onNewChat={openChat}
            onSearch={() => setPalette(true)}
            onOpenConversation={(c) => {
              setCurrent(c.id);
              if (c.project_id) setLastProject(c.project_id);
              showView("conversation");
            }}
            onClose={() => setMenuOpen(false)}
          />
          {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} aria-hidden="true" />}
          <div className="principal">
            <PageBar
              title={pageTitle(view, conversations.find((c) => c.id === current)?.title ?? (inProject ? projectNames[inProject] : null))}
            >
              {view === "conversation" && (
                <>
                  <button
                    type="button"
                    className="page-bar-button"
                    aria-label="Ler respostas em voz alta"
                    title={voice.speakerKind ? "Ler respostas em voz alta" : "Este navegador não consegue ler em voz alta"}
                    aria-pressed={speakReplies}
                    disabled={voice.speakerKind === null}
                    onClick={toggleSpeak}
                  >
                    <Icon name="speaker" size={18} />
                  </button>
                  <button type="button" className="page-bar-button" aria-label="Compartilhar ou exportar" title="Compartilhar ou exportar" onClick={() => setShare(true)} disabled={!current}>
                    <Icon name="share" size={18} />
                  </button>
                  {desk && (
                    <button
                      type="button"
                      className="page-bar-button"
                      aria-label="Mostrar o que ele está fazendo"
                      title="Mostrar o que ele está fazendo"
                      aria-pressed={benchOpen}
                      onClick={() => setBenchOpen((o) => { savePreference("bench", o ? "0" : "1"); return !o; })}
                    >
                      <Icon name="panel" size={18} />
                    </button>
                  )}
                </>
              )}
              <button type="button" className="page-bar-button" aria-label="Comandos (Ctrl K)" title="Comandos (Ctrl K)" onClick={() => setPalette(true)}>
                <Icon name="command" size={18} />
              </button>
            </PageBar>
            <div className="principal-corpo">
              {desk && inProject && (
                <ProjectColumn api={api} current={inProject} refreshKey={projectsKey} onOpen={(id) => void openProjectChat(id)} onError={handleError} />
              )}

              <main className="main">
                {notice && (
                  <p className="note first-run-notice" role="status">
                    {notice}{" "}
                    <button type="button" className="link-button" onClick={() => setNotice(null)}>ok</button>
                  </p>
                )}
                {view === "inbox" && (
                  <InboxView
                    api={api}
                    call={call}
                    onDraft={draftInChat}
                    onSend={(text) => {
                      // To the conversation in front (as the suggestions do), shown at once.
                      setView("conversation");
                      void send(text);
                    }}
                    online={online}
                    macOnline={macOnline}
                    project={Object.entries(projectNames).map(([id, name]) => ({ id, name }))[0] ?? null}
                    onOpenProject={(id) => void openProjectChat(id)}
                    onOpenPanel={() => go("panel")}
                    working={sending || macWorking}
                    pending={pending}
                    current={current}
                    onReplied={(conversationId) => {
                      setView("conversation");
                      setCurrent(conversationId);
                      loadMessages(conversationId).then(setMessages).catch(handleError);
                      setComposerFocus((value) => value + 1);
                    }}
                  />
                )}
                {view === "projects" && (
                  <ProjectsView api={api} onOpenProject={(id) => void openProjectChat(id)} onError={handleError} />
                )}
                {view === "study" && (
                  <section className="page page--caderno" aria-labelledby="study-title">
                    <header className="page-head">
                      <span className="rotulo">Caderno</span>
                      <h1 id="study-title" className="page-voice">O que eu fiz <em>enquanto você não estava.</em></h1>
                      <p className="lede">O que pensei, estudei e o que sei de você. Tudo pode ser desfeito.</p>
                    </header>
                    <MindPanel api={api} onError={handleError} />
                    <StudyPanel api={api} onError={handleError} />
                  </section>
                )}
                {view === "mac" && <MacView api={api} pending={pending} onError={handleError} />}
            {view === "routines" && <RoutinesView routines={routines} />}
            {view === "panel" && <PanelView api={api} onBack={() => go("inbox")} onDraft={draftInChat} onError={handleError} />}
            {(view === "agents" || view === "channels" || view === "skills") && <NotYetView place={view} />}
                {view === "settings" && (
                  <SettingsView
                    api={api}
                    onPausedChange={pending.setPaused}
                    memoryEnabled={memoryEnabled}
                    onToggleMemory={() => void toggleMemory()}
                    speakReplies={speakReplies}
                    canSpeak={voice.speakerKind !== null}
                    speakerKind={voice.speakerKind}
                    onToggleSpeak={toggleSpeak}
                    deviceListening={deviceListening}
                    deviceCouldListen={voice.deviceCouldListen}
                    serverListening={voice.listenerKind === "server"}
                    onToggleDeviceListening={toggleDeviceListening}
                    onRestartOnboarding={() => {
                      api.restartOnboarding().then(() => api.onboarding()).then(setOnboarding).catch(handleError);
                    }}
                    onLogout={logout}
                    onError={handleError}
                    voiceApproval={voiceApproval}
                    toolsMode={toolsMode}
                onToolsMode={(mode) => { setToolsMode(mode); savePreference("tools", mode); }}
                onToggleVoiceApproval={() => {
                      const next = !voiceApproval;
                      setVoiceApproval(next);
                      savePreference("voice-approval", next ? "1" : "0");
                    }}
                  />
                )}
                <ChatView
                  hidden={view !== "conversation"}
                  onOpenProject={(id) => void openProjectChat(id)}
                  projectName={(id) => projectNames[id]}
                  segments={conversations.find((c) => c.id === current)?.continuous ? segments : undefined}
                  olderLeft={olderLeft}
                  onLoadOlder={() => void loadOlder()}
                  placeholder="Fala comigo…"
                  composerStart={<MicButton canCall={call.canCall} hint={call.hint} onCall={call.onCall} live={voice.inCall} />}
                  anel={anel}
                  macWorking={macWorking}
                  voiceLevel={voice.level}
                  steps={liveSteps}
              toolsMode={toolsMode}
                  header={
                    <>
                      {projectBar}
                      {memoryWarning ? <p className="note sky-warning" role="status">{memoryWarning}</p> : undefined}
                    </>
                  }
                  focusRequest={composerFocus}
                  agentName={agentName}
                  messages={messages}
                  asks={liveAsks}
                  sending={sending || preparing}
                  status={liveStep}
                  draftRequest={draftRequest}
                  liveText={liveText}
                  settlingId={settling}
                  onSettled={() => {
                    setSettling(null);
                    setLiveText(null);
                    if (!document.hidden) navigator.vibrate?.(4);
                  }}
                  onStop={stopTurn}
                  error={voice.inCall ? null : error}
                  onSend={(text, files, replyTo) => void send(text, undefined, files, replyTo)}
                  onUpload={(file, name) => api.uploadAttachment(file, name)}
                  loadAttachment={loadAttachment}
                  pageUrl={(path) => api.pageUrl(path)}
                  onOpenPage={desk ? setSidePage : undefined}
                  onDeleteArtifact={(a) => void deleteArtifact(a)}
                  onFeedback={sendFeedback}
                />
                {view !== "conversation" && error && !voice.inCall && <p className="error page-error" role="alert">× {error}</p>}
              </main>

              {desk && view === "conversation" ? (
                sidePage?.path ? (
                  <ArtifactViewer
                    docked
                    artifact={sidePage}
                    url={api.pageUrl(sidePage.path)}
                    onClose={() => setSidePage(null)}
                    onDelete={() => {
                      if (window.confirm(`Apagar “${sidePage.title}”? O link para de funcionar.`)) void deleteArtifact(sidePage);
                    }}
                  />
                ) : benchOpen ? (
                  <Bench bench={bench} steps={liveSteps} working={sending} onOpenPage={(page) => setSidePage(page)} />
                ) : null
              ) : null}
            </div>
          </div>
        </div>
      )}
      {!firstRun && ready && (
        <StatusBar
          api={api}
          online={online}
          running={pending.tasks.filter((t) => t.status === "running").length}
          macOnline={macOnline}
          routines={routines.active}
          quiet={routines.quiet}
          onError={handleError}
        />
      )}
      {palette && ready && <CommandPalette items={paletteItems} onClose={() => setPalette(false)} />}
      {share && ready && (
        <ShareDialog
          title={pageTitle("conversation", currentConversation?.title)}
          messages={messages}
          agentName={agentName}
          onClose={() => setShare(false)}
          onDone={setToast}
        />
      )}
      <Toast message={toast} />

      {!firstRun && !ready && !loggedIn && !demo && (
        <MuninnEntrance thinking={loginBusy}>
          <Login
            api={api}
            online={online}
            onBusyChange={setLoginBusy}
            onLoggedIn={(token, remember) => {
              saveToken(token, remember);
              setLoggedIn(true);
              if (introAfterLogin()) setIntro(true);
            }}
          />
        </MuninnEntrance>
      )}
      {!firstRun && !ready && (loggedIn || demo) && (
        <div className="layout">
          <main className="main auth-main">
            <div className="entrance">
              <div className="entrance-mascot">
                <Anel estado={anel} size={200} level={demo ? demoLevel : voice.speaking || voice.inCall ? voice.level : undefined} />
              </div>
              {demo && <p className="rotulo state-label">{ANEL_LABELS[anel]}</p>}
            </div>
            {demo ? (
              <div className="demo">
                {ANEL_ESTADOS.map((s) => (
                  <button key={s} type="button" className="rs-botao rs-botao--compacto" aria-pressed={s === demoState} onClick={() => setDemoState(s)}>
                    {ANEL_LABELS[s]}
                  </button>
                ))}
              </div>
            ) : status && !status.genesis_completed ? (
              <div className="rs-mensagem rs-mensagem--aviso" role="alert">
                <i aria-hidden="true">!</i><b>Aviso</b>
                <p>Ainda não nasci: rode <code>python -m apps.api.cli genesis</code> no servidor.</p>
              </div>
            ) : null}
          </main>
        </div>
      )}

      {voice.inCall && (
        <CallView
          agentName={agentName}
          state={orbState}
          level={voice.level}
          messages={messages}
          engine={voice.listenerKind}
          speaking={voice.speaking}
          error={error}
          onInterrupt={voice.stopSpeaking}
          onHangUp={voice.endCall}
          ask={liveAsks[0] ?? null}
          voiceApproval={voiceApproval}
          camera={camera}
        />
      )}
    </div>
  );
}
