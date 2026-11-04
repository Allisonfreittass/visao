import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  Api,
  ApiError,
  utcDate,
  type Conversation,
  type Message,
  type SystemStatus,
  type VoiceStatus,
} from "./api";
import { ChatView } from "./components/ChatView";
import { InitiativesPanel } from "./components/InitiativesPanel";
import { MindPanel } from "./components/MindPanel";
import { StudyPanel } from "./components/StudyPanel";
import { NotificationFeed } from "./components/NotificationFeed";
import { Login } from "./components/Login";
import { Orb, STATE_LABELS } from "./orb/Orb";
import type { OrbState } from "./orb/orbModel";
import { loadPreference, loadToken, savePreference, saveToken } from "./session";
import { Speaker } from "./speech/speaker";
import { Microphone, type Utterance } from "./voice/microphone";

interface TurnLatency {
  sttMs: number;
  llmMs: number;
  ttsFirstAudioMs: number | null;
  /** End of the user's speech to the first audio of the reply. */
  totalMs: number | null;
}

const HEALTH_INTERVAL_MS = 15_000;
const INITIATIVE_POLL_MS = 15_000;
const DEMO_STATES: OrbState[] = [
  "IDLE",
  "LISTENING",
  "THINKING",
  "SPEAKING",
  "INTERRUPTED",
  "DISCONNECTED",
];

function useHealth(api: Api): boolean {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    let alive = true;
    const check = () =>
      api.health().then(
        () => alive && setOnline(true),
        () => alive && setOnline(false),
      );
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

export function App() {
  const api = useMemo(() => {
    const instance = new Api();
    instance.setToken(loadToken());
    return instance;
  }, []);
  const speaker = useMemo(() => new Speaker(api), [api]);
  const online = useHealth(api);
  const demo = new URLSearchParams(window.location.search).get("orb") === "demo";

  const [loggedIn, setLoggedIn] = useState(api.authenticated);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [memoryEnabled, setMemoryEnabled] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sending, setSending] = useState(false);
  const [composerFocus, setComposerFocus] = useState(0);
  const sendingRef = useRef(false);
  const messagesRef = useRef<Message[]>([]);
  const speakRef = useRef<((text: string) => void) | null>(null);
  sendingRef.current = sending;
  messagesRef.current = messages;
  const [preparing, setPreparing] = useState(false);
  const [memoryWarning, setMemoryWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [workspaceView, setWorkspaceView] = useState<"conversation" | "study">("conversation");
  const [voice, setVoice] = useState<VoiceStatus | null>(null);
  const [speakReplies, setSpeakReplies] = useState(() => loadPreference("speak") === "1");
  const [speaking, setSpeaking] = useState(false);
  const [interrupted, setInterrupted] = useState(false);
  const [voiceSession, setVoiceSession] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [latency, setLatency] = useState<TurnLatency | null>(null);
  const micRef = useRef<Microphone | null>(null);
  const busyRef = useRef(false);
  const [demoState, setDemoState] = useState<OrbState>("IDLE");
  const demoLevel = useDemoLevel(demo && (demoState === "LISTENING" || demoState === "SPEAKING"));

  const handleError = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401) {
      saveToken(null);
      setLoggedIn(false);
      return;
    }
    setError(e instanceof Error ? e.message : String(e));
  }, []);

  useEffect(() => {
    if (!loggedIn) return;
    api.voiceStatus().then(setVoice, () => setVoice(null));
    Promise.all([api.status(), api.memorySettings(), api.listConversations()])
      .then(([s, memory, list]) => {
        setStatus(s);
        setMemoryEnabled(memory.enabled);
        setConversations(list);
        if (list.length > 0) setCurrent((c) => c ?? list[0].id);
      })
      .catch(handleError);
  }, [api, loggedIn, handleError]);

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
    if (!current) {
      setMessages([]);
      return;
    }
    api.messages(current).then(setMessages).catch(handleError);
  }, [api, current, handleError]);

  // The agent can speak first: pick up what it said on its own, and say it aloud if replies are.
  useEffect(() => {
    if (!current || !loggedIn || demo) return;
    let alive = true;
    const timer = setInterval(() => {
      if (sendingRef.current) return;
      api.messages(current).then((next) => {
        if (!alive || sendingRef.current) return;
        const known = new Set(messagesRef.current.map((m) => m.id));
        const fresh = next.filter((m) => m.origin === "initiative" && !known.has(m.id));
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
        ? "A memória anterior não pôde ser preparada. Você pode conversar, mas alguns detalhes podem faltar."
        : null,
    );
  }

  async function newConversation() {
    if (preparing || sending) return;
    setError(null);
    setPreparing(true);
    try {
      const conversation = await api.createConversation();
      checkMemoryPreparation(conversation);
      setConversations((list) => [conversation, ...list]);
      setCurrent(conversation.id);
      setMenuOpen(false);
    } catch (e) {
      handleError(e);
    } finally {
      setPreparing(false);
    }
  }

  function stopSpeaking() {
    if (!speaker.speaking) return;
    speaker.stop();
    setSpeaking(false);
    setInterrupted(true);
    setTimeout(() => setInterrupted(false), 700);
  }

  speakRef.current = speakReplies && voice?.enabled ? (text) => speak(text) : null;

  function speak(text: string, onFirstAudio?: (ms: number) => void) {
    setSpeaking(true);
    speaker
      .speak(text, (ms) => {
        onFirstAudio?.(ms);
      })
      .catch((e) => setError(`Voz indisponível (${e instanceof Error ? e.message : e}); a resposta segue em texto.`))
      .finally(() => setSpeaking(false));
  }

  async function send(
    text: string,
    spoken?: { endedAt: number; sttMs: number },
  ): Promise<void> {
    setError(null);
    // Barge-in by text: a new message cuts whatever is being spoken.
    stopSpeaking();
    // In a voice session replies are always spoken; otherwise it follows the toggle.
    const willSpeak = (spoken !== undefined || speakReplies) && voice?.enabled === true;
    // Audio must be unlocked inside the user gesture, before any await.
    if (willSpeak) speaker.unlock();
    let conversationId = current;
    setSending(true);
    try {
      if (!conversationId) {
        const conversation = await api.createConversation();
        checkMemoryPreparation(conversation);
        setConversations((list) => [conversation, ...list]);
        setCurrent(conversation.id);
        conversationId = conversation.id;
      }
      const llmStarted = performance.now();
      const turn = await api.send(conversationId, text, spoken ? "voice" : "text");
      const llmMs = performance.now() - llmStarted;
      setMessages((list) => [
        ...list,
        turn.user_message,
        { ...turn.assistant_message, sources: turn.sources },
      ]);
      if (spoken) {
        setLatency({ sttMs: spoken.sttMs, llmMs, ttsFirstAudioMs: null, totalMs: null });
      }
      if (willSpeak) {
        const ttsStarted = performance.now();
        speak(turn.assistant_message.content, () => {
          if (!spoken) return;
          const now = performance.now();
          const measured = {
            sttMs: spoken.sttMs,
            llmMs,
            ttsFirstAudioMs: now - ttsStarted,
            totalMs: now - spoken.endedAt,
          };
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

  async function onUtterance(utterance: Utterance) {
    // One turn at a time: speech that arrives while a turn is in flight is dropped.
    if (busyRef.current) return;
    busyRef.current = true;
    setTranscribing(true);
    try {
      const transcript = await api.stt(utterance.wav);
      const sttMs = performance.now() - utterance.endedAt;
      setTranscribing(false);
      const text = transcript.text.trim();
      if (text.length < 2) return; // noise or a cough, not a turn
      await send(text, { endedAt: utterance.endedAt, sttMs });
    } catch (e) {
      handleError(e);
    } finally {
      setTranscribing(false);
      busyRef.current = false;
    }
  }

  function endVoiceSession() {
    micRef.current?.stop();
    micRef.current = null;
    setVoiceSession(false);
  }

  async function startVoiceSession() {
    setError(null);
    speaker.unlock(); // inside the click: lets replies play
    const microphone = new Microphone({
      agentSpeaking: () => speaker.speaking,
      // Barge-in by voice: starting to talk cuts the agent off.
      onSpeechStart: () => stopSpeaking(),
      onUtterance: (u) => void onUtterance(u),
    });
    try {
      await microphone.start();
      micRef.current = microphone;
      setVoiceSession(true);
    } catch (e) {
      microphone.stop();
      setError(
        `Microfone indisponível (${e instanceof Error ? e.message : e}). A conversa continua por texto.`,
      );
    }
  }

  // No listening in the background: hiding the page ends the voice session.
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "hidden") endVoiceSession();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      micRef.current?.stop();
    };
  }, []);

  async function sendFeedback(
    messageId: string,
    rating: 1 | -1,
    tags: string[],
  ): Promise<string | null> {
    try {
      const result = await api.feedback(messageId, rating, tags);
      return result.state_changed
        ? "Obrigado. Ajustei a comunicação com base no seu retorno."
        : "Obrigado.";
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
    if (next) speaker.unlock();
    else stopSpeaking();
  }

  function logout() {
    endVoiceSession();
    stopSpeaking();
    api.setToken(null);
    saveToken(null);
    setLoggedIn(false);
    setConversations([]);
    setCurrent(null);
  }

  const orbState: OrbState = demo
    ? demoState
    : !online
      ? "DISCONNECTED"
      : sending || transcribing
        ? "THINKING"
        : interrupted
          ? "INTERRUPTED"
          : speaking
            ? "SPEAKING"
            : voiceSession
              ? "LISTENING"
              : "IDLE";
  const agentName = status?.identity?.chosen_name ?? null;

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="/" aria-label="VISÃO, início"><span className="brand-mark">◉</span><span>VISÃO<span className="brand-dot">.</span></span></a>
        {loggedIn && !demo && (
          <button className="ghost" onClick={() => setMenuOpen((o) => !o)} aria-expanded={menuOpen}>
            Menu
          </button>
        )}
        <span className="identity" title={status?.identity?.internal_id}>
          <span className="identity-dot" />{agentName ?? "Identidade em construção"}
        </span>
        {loggedIn && !demo && (
          <button className="ghost" onClick={logout}>
            Sair
          </button>
        )}
      </header>

      <div className="layout">
        {loggedIn && !demo && (
          <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
            <p className="sidebar-label">SEU ESPAÇO</p>
            <nav className="workspace-nav" aria-label="Navegação principal">
              <button className={workspaceView === "conversation" ? "nav-active" : "ghost"} onClick={() => { setWorkspaceView("conversation"); setMenuOpen(false); }}><span>↗</span> Conversa</button>
              <button className={workspaceView === "study" ? "nav-active" : "ghost"} onClick={() => { setWorkspaceView("study"); setMenuOpen(false); }}><span>⌘</span> Caderno de estudos</button>
            </nav>
            <button className="new-conversation" onClick={() => { setWorkspaceView("conversation"); void newConversation(); }} disabled={preparing || sending}>
              {preparing ? "Preparando memórias…" : "Nova conversa"}
            </button>
            <p className="sidebar-label history-label">CONVERSAS RECENTES</p>
            <ul className="conversation-list">
              {conversations.map((c) => (
                <li key={c.id}>
                  <button
                    className={c.id === current ? "active" : "ghost"}
                    onClick={() => {
                      setCurrent(c.id);
                      setWorkspaceView("conversation");
                      setMenuOpen(false);
                    }}
                  >
                    {utcDate(c.created_at).toLocaleString("pt-BR", {
                      dateStyle: "short",
                      timeStyle: "short",
                    })}
                  </button>
                </li>
              ))}
            </ul>
            <details className="preferences"><summary>Preferências e autonomia <span>+</span></summary><div className="preferences-content">
            <InitiativesPanel api={api} onError={handleError} />
            <label className="memory-toggle">
              <input type="checkbox" checked={memoryEnabled} onChange={toggleMemory} />
              Memória entre conversas
            </label>
            <p className="note">
              Guarda informações selecionadas para dar continuidade às próximas conversas.
            </p>
            <label className="memory-toggle">
              <input
                type="checkbox"
                checked={speakReplies}
                onChange={toggleSpeak}
                disabled={!voice?.enabled}
              />
              Falar respostas
            </label>
            <p className="note">
              {!voice?.enabled
                ? "A voz está indisponível neste momento."
                : "Quando ligada, as respostas também são lidas em voz alta."}

            </p>
            </div></details>
            <div className="sidebar-bottom"><span className="status-dot" /> {online ? "Conectado" : "Sem conexão"}<span>Projeto experimental</span></div>
          </aside>
        )}

        <main className={`main ${!loggedIn ? "auth-main" : ""}`}>
          {loggedIn && !demo && <>
            <div className="workspace-heading"><div><span className="eyebrow">{workspaceView === "conversation" ? "PRESENÇA & CONTINUIDADE" : "CURIOSIDADE EM MOVIMENTO"}</span><h1>{workspaceView === "conversation" ? "Toda ideia pode ser um começo." : "Um caderno em construção."}</h1><p>{workspaceView === "conversation" ? "Um espaço para conversar, explorar e retomar." : "Perguntas escolhidas, fontes consultadas e caminhos que continuam."}</p></div></div>
            <nav className="workspace-tabs" aria-label="Área de trabalho"><button className={workspaceView === "conversation" ? "selected" : "ghost"} onClick={() => setWorkspaceView("conversation")}>Conversa</button><button className={workspaceView === "study" ? "selected" : "ghost"} onClick={() => setWorkspaceView("study")}>Estudos</button></nav>
          </>}
          <div className={`presence ${workspaceView === "study" && loggedIn ? "study-presence" : ""}`}>
          <div className="orb-wrap">
            <Orb
              state={orbState}
              size={loggedIn && !demo ? 100 : 240}
              level={demoLevel}
              getLevel={
                speaking
                  ? () => speaker.level()
                  : voiceSession
                    ? () => micRef.current?.level() ?? 0
                    : undefined
              }
            />
          </div>
          <div className="presence-copy"><p className="state-label">{STATE_LABELS[orbState]}</p><span>{orbState === "IDLE" ? "Por aqui, quando quiser continuar." : orbState === "THINKING" ? "Preparando uma resposta para você." : orbState === "DISCONNECTED" ? "Tentando restabelecer a conexão." : "Acompanhe a conversa no seu ritmo."}</span></div>
          </div>

          {demo ? (
            <div className="demo">
              {DEMO_STATES.map((s) => (
                <button
                  key={s}
                  className={s === demoState ? "active" : "ghost"}
                  onClick={() => setDemoState(s)}
                >
                  {STATE_LABELS[s]}
                </button>
              ))}
            </div>
          ) : !loggedIn ? (
            <Login
              api={api}
              onLoggedIn={(token) => {
                saveToken(token);
                setLoggedIn(true);
              }}
            />
          ) : status && !status.genesis_completed ? (
            <p className="error">
              Genesis ainda não foi executado. Rode <code>python -m apps.api.cli genesis</code>.
            </p>
          ) : (
            <>
              {(workspaceView === "conversation" || voiceSession) && <div className="voice-bar">
                {voice?.listening && voice.enabled && (
                  <button
                    className={voiceSession ? "active" : "ghost"}
                    onClick={voiceSession ? endVoiceSession : () => void startVoiceSession()}
                    aria-pressed={voiceSession}
                  >
                    {voiceSession ? "Encerrar conversa por voz" : "Conversa por voz"}
                  </button>
                )}
                {speaking && (
                  <button className="ghost stop" onClick={stopSpeaking}>
                    Parar de falar
                  </button>
                )}
              </div>}
              {latency && (
                <p className="latency">
                  Último turno: transcrição {Math.round(latency.sttMs)} ms · resposta{" "}
                  {Math.round(latency.llmMs)} ms
                  {latency.ttsFirstAudioMs !== null &&
                    ` · 1º áudio ${Math.round(latency.ttsFirstAudioMs)} ms`}
                  {latency.totalMs !== null &&
                    ` · total fim da fala → voz ${Math.round(latency.totalMs)} ms`}
                </p>
              )}
              <NotificationFeed
                api={api}
                current={current}
                onError={handleError}
                onReply={(conversationId) => {
                  setWorkspaceView("conversation");
                  setCurrent(conversationId);
                  api.messages(conversationId).then(setMessages).catch(handleError);
                  setComposerFocus((value) => value + 1);
                }}
              />
              {workspaceView === "study" && <MindPanel api={api} onError={handleError} />}
              {workspaceView === "study" && <StudyPanel api={api} onError={handleError} />}
              {memoryWarning && <p className="note" role="status">{memoryWarning}</p>}
              <ChatView
                hidden={workspaceView !== "conversation"}
                focusRequest={composerFocus}
                agentName={agentName}
                messages={messages}
                sending={sending || preparing}
                error={error}
                onSend={send}
                onFeedback={sendFeedback}
              />
            </>
          )}
        </main>
      </div>
      <footer className="footer">VISÃO <span>·</span> Um projeto em descoberta</footer>
    </div>
  );
}
