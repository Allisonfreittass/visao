import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  Api,
  ApiError,
  utcDate,
  type Conversation,
  type Message,
  type OnboardingStatus,
  type SystemStatus,
  type VoiceStatus,
} from "./api";
import { CallView } from "./components/CallView";
import { ChatView } from "./components/ChatView";
import { Login } from "./components/Login";
import { MindPanel } from "./components/MindPanel";
import { InboxView } from "./components/InboxView";
import { MacView } from "./components/MacView";
import { Onboarding } from "./components/Onboarding";
import { type CallControls, Presence, PresencePanel } from "./components/Presence";
import { Rail, type WorkspaceView } from "./components/Rail";
import { SettingsView } from "./components/SettingsView";
import { StudyPanel } from "./components/StudyPanel";
import { usePending } from "./hooks/usePending";
import { type SpokenTiming, useVoice } from "./hooks/useVoice";
import { dayLabel } from "./labels";
import { Orb, STATE_LABELS } from "./orb/Orb";
import type { OrbState } from "./orb/orbModel";
import { parseMacCommand } from "./arm";
import { registerWorker } from "./push";
import { loadPreference, loadToken, savePreference, saveToken } from "./session";

interface TurnLatency {
  sttMs: number;
  llmMs: number;
  ttsFirstAudioMs: number | null;
  /** End of the user's speech to the first audio of the reply. */
  totalMs: number | null;
}

const HEALTH_INTERVAL_MS = 15_000;
const INITIATIVE_POLL_MS = 15_000;
const DEMO_STATES: OrbState[] = ["IDLE", "LISTENING", "THINKING", "SPEAKING", "INTERRUPTED", "DISCONNECTED"];

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
  const [sending, setSending] = useState(false);
  const [composerFocus, setComposerFocus] = useState(0);
  const [preparing, setPreparing] = useState(false);
  const [memoryWarning, setMemoryWarning] = useState<string | null>(null);
  const [onboarding, setOnboarding] = useState<OnboardingStatus | "checking" | "done">("checking");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  // A notification about Mac work opens the list of what waits for a yes (`/?mac=1`).
  const [view, setView] = useState<WorkspaceView>(() =>
    new URLSearchParams(window.location.search).get("mac") ? "inbox" : "conversation",
  );
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null);
  const [speakReplies, setSpeakReplies] = useState(() => loadPreference("speak") === "1");
  const [deviceListening, setDeviceListening] = useState(() => loadPreference("device-listening") === "1");
  const [latency, setLatency] = useState<TurnLatency | null>(null);
  const [demoState, setDemoState] = useState<OrbState>("IDLE");
  const demoLevel = useDemoLevel(demo && (demoState === "LISTENING" || demoState === "SPEAKING"));
  const sendingRef = useRef(false);
  const messagesRef = useRef<Message[]>([]);
  sendingRef.current = sending;
  messagesRef.current = messages;

  const handleError = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401) {
      saveToken(null);
      setLoggedIn(false);
      return;
    }
    setError(e instanceof Error ? e.message : String(e));
  }, []);

  const sendRef = useRef<(text: string, spoken?: SpokenTiming) => Promise<void>>(async () => undefined);
  const voice = useVoice({
    api,
    status: voiceStatus,
    deviceListening,
    onTranscript: (text, timing) => sendRef.current(text, timing),
    onError: setError,
  });

  const firstRun = loggedIn && !demo && onboarding !== "done";
  const ready = loggedIn && !demo && !firstRun && status?.genesis_completed !== false;
  const pending = usePending(api, ready, handleError, ready && view === "conversation");

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

  useEffect(() => {
    if (!loggedIn) return;
    api.voiceStatus().then(setVoiceStatus, () => setVoiceStatus(null));
    Promise.all([api.status(), api.memorySettings(), api.listConversations()])
      .then(([s, memory, list]) => {
        setStatus(s);
        setMemoryEnabled(memory.enabled);
        setConversations(list);
        setCurrent((c) => (c && list.some((x) => x.id === c) ? c : list[0]?.id ?? null));
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
    api.messages(current).then(setMessages).catch(handleError);
  }, [api, current, loggedIn, handleError]);

  const speakAloud = speakReplies || voice.inCall;
  const speakRef = useRef<((text: string) => void) | null>(null);
  speakRef.current = speakAloud && voice.speakerKind ? (text) => voice.speak(text) : null;

  // It can speak first: pick up what it said on its own, and say it aloud in a call.
  useEffect(() => {
    if (!current || !loggedIn || demo) return;
    let alive = true;
    const timer = setInterval(() => {
      if (sendingRef.current) return;
      api.messages(current).then((next) => {
        if (!alive || sendingRef.current) return;
        const known = new Set(messagesRef.current.map((m) => m.id));
        // What it says on its own, and the arm's reports, are read aloud in a call.
        const fresh = next.filter((m) => m.role === "assistant" && (m.origin === "initiative" || m.origin === "arm") && !known.has(m.id));
        if (next.length !== messagesRef.current.length) setMessages(next);
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

  async function openConversation(): Promise<string> {
    const conversation = await api.createConversation();
    checkMemoryPreparation(conversation);
    setConversations((list) => [conversation, ...list]);
    setCurrent(conversation.id);
    return conversation.id;
  }

  async function newConversation() {
    if (preparing || sending) return;
    setError(null);
    setPreparing(true);
    setView("conversation");
    try {
      await openConversation();
      setMenuOpen(false);
    } catch (e) {
      handleError(e);
    } finally {
      setPreparing(false);
    }
  }

  async function askMac(command: { project: string; prompt: string }): Promise<void> {
    setSending(true);
    try {
      const conversationId = current ?? (await openConversation());
      await api.askArm(command.project, command.prompt, conversationId);
      setMessages(await api.messages(conversationId));
    } catch (e) {
      handleError(e);
    } finally {
      setSending(false);
    }
  }

  async function send(text: string, spoken?: SpokenTiming): Promise<void> {
    setError(null);
    const mac = spoken ? null : parseMacCommand(text);
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
    setSending(true);
    try {
      conversationId ??= await openConversation();
      const llmStarted = performance.now();
      const turn = await api.send(conversationId, text, spoken ? "voice" : "text");
      const llmMs = performance.now() - llmStarted;
      setMessages((list) => [...list, turn.user_message, { ...turn.assistant_message, sources: turn.sources }]);
      pending.refresh(); // a request for the Mac may be waiting for a tap now
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
      handleError(e);
      // The user message may have been stored even if the reply failed: reload the transcript.
      if (conversationId) api.messages(conversationId).then(setMessages).catch(() => undefined);
    } finally {
      setSending(false);
    }
  }
  sendRef.current = send;

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

  const orbState: OrbState = demo
    ? demoState
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
  const agentName = status?.identity?.chosen_name ?? null;
  const callHint = voice.listenerKind
    ? null
    : voice.deviceCouldListen
      ? "Para ligar daqui, ligue Ouvir pelo navegador."
      : "Este navegador não consegue me ouvir. Dá para escrever.";

  const call: CallControls = {
    state: orbState,
    level: voice.level,
    levelActive: voice.speaking || voice.inCall,
    canCall: voice.listenerKind !== null && online,
    speaking: voice.speaking,
    hint: callHint,
    onCall: () => { setError(null); void voice.startCall(); },
    onStopSpeaking: voice.stopSpeaking,
    onOpenSettings: () => showView("settings"),
  };
  const currentConversation = conversations.find((c) => c.id === current);
  const macOnline = pending.devices.length ? pending.devices.some((d) => d.online) : null;

  return (
    <div className="app">
      <header className={`topbar ${ready ? "topbar--app" : ""}`}>
        {ready && (
          <button type="button" className="rs-botao rs-botao--compacto menu-button" onClick={() => setMenuOpen((o) => !o)} aria-expanded={menuOpen}>
            Menu{pending.count > 0 && <span className="rail-badge" aria-label={`${pending.count} esperando você`}>{pending.count}</span>}
          </button>
        )}
        <a className="brand" href="/" aria-label="Visão, início">Visão</a>
        <span className="identity" title={status?.identity?.internal_id}>
          {agentName ?? <em>sem nome ainda</em>}
        </span>
        {loggedIn && !demo && !ready && (
          <button type="button" className="rs-botao rs-botao--compacto" onClick={logout}>Sair</button>
        )}
      </header>

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
            view={view}
            conversations={conversations}
            current={current}
            busy={preparing || sending}
            preparing={preparing}
            online={online}
            pendingCount={pending.count}
            macOnline={macOnline}
            onView={showView}
            onNewConversation={() => void newConversation()}
            onSelect={(id) => { setCurrent(id); showView("conversation"); }}
          />
          {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} aria-hidden="true" />}

          <main className="main">
            {notice && (
              <p className="note first-run-notice" role="status">
                {notice}{" "}
                <button type="button" className="link-button" onClick={() => setNotice(null)}>ok</button>
              </p>
            )}
            {view === "inbox" && (
              <InboxView
                pending={pending}
                current={current}
                onReplied={(conversationId) => {
                  setView("conversation");
                  setCurrent(conversationId);
                  api.messages(conversationId).then(setMessages).catch(handleError);
                  setComposerFocus((value) => value + 1);
                }}
              />
            )}
            {view === "study" && (
              <section className="page page--caderno" aria-labelledby="study-title">
                <header className="page-head">
                  <span className="rotulo">Caderno</span>
                  <h1 id="study-title">O que eu fiz <em>enquanto você não estava.</em></h1>
                  <p className="lede">O que pensei, estudei e o que sei de você. Tudo pode ser desfeito.</p>
                </header>
                <MindPanel api={api} onError={handleError} />
                <StudyPanel api={api} onError={handleError} />
              </section>
            )}
            {view === "mac" && <MacView api={api} pending={pending} onError={handleError} />}
            {view === "settings" && (
              <SettingsView
                api={api}
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
              />
            )}
            <ChatView
              hidden={view !== "conversation"}
              header={
                <div className="chat-head">
                  <div className="chat-head-text">
                    <span className="rotulo">{currentConversation ? dayLabel(utcDate(currentConversation.created_at)) : "Conversa nova"}</span>
                    {memoryWarning && <p className="note" role="status">{memoryWarning}</p>}
                    {latency && (
                      <p className="latency">
                        Último turno: transcrição {Math.round(latency.sttMs)} ms · resposta {Math.round(latency.llmMs)} ms
                        {latency.ttsFirstAudioMs !== null && ` · 1º áudio ${Math.round(latency.ttsFirstAudioMs)} ms`}
                        {latency.totalMs !== null && ` · fim da fala → voz ${Math.round(latency.totalMs)} ms`}
                      </p>
                    )}
                  </div>
                  <Presence call={call} compact />
                </div>
              }
              focusRequest={composerFocus}
              agentName={agentName}
              messages={messages}
              proposals={pending.armProposals.filter((t) => t.conversation_id === current)}
              onDecide={(task, decision) => void pending.decideArm(task, decision)}
              sending={sending || preparing}
              error={voice.inCall ? null : error}
              onSend={(text) => void send(text)}
              onFeedback={sendFeedback}
            />
            {view !== "conversation" && error && !voice.inCall && <p className="error page-error" role="alert">× {error}</p>}
          </main>

          <PresencePanel api={api} call={call} pending={pending} onOpen={showView} />
        </div>
      )}

      {!firstRun && !ready && (
        <div className="layout">
          <main className="main auth-main rs-luz-indireta">
            <div className="entrance">
              <div className="presence">
                <div className="orb-wrap">
                  <Orb state={orbState} size={240} level={demoLevel} getLevel={voice.speaking || voice.inCall ? voice.level : undefined} />
                </div>
                <div className="presence-copy">
                  <p className="rotulo state-label">{STATE_LABELS[orbState]}</p>
                  {!demo && <p className="lede">Eu nasci sem nome e venho decidindo quem sou. Entre para conversar.</p>}
                </div>
              </div>
            </div>
            {demo ? (
              <div className="demo">
                {DEMO_STATES.map((s) => (
                  <button key={s} type="button" className="rs-botao rs-botao--compacto" aria-pressed={s === demoState} onClick={() => setDemoState(s)}>
                    {STATE_LABELS[s]}
                  </button>
                ))}
              </div>
            ) : !loggedIn ? (
              <Login
                api={api}
                onLoggedIn={(token, remember) => {
                  saveToken(token, remember);
                  setLoggedIn(true);
                }}
              />
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
        />
      )}
    </div>
  );
}
