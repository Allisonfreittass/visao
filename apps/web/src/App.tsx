import { useCallback, useEffect, useMemo, useState } from "react";

import { Api, ApiError, type Conversation, type Message, type SystemStatus } from "./api";
import { ChatView } from "./components/ChatView";
import { Login } from "./components/Login";
import { Orb, STATE_LABELS } from "./orb/Orb";
import type { OrbState } from "./orb/orbModel";
import { loadToken, saveToken } from "./session";

const HEALTH_INTERVAL_MS = 15_000;
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
  const online = useHealth(api);
  const demo = new URLSearchParams(window.location.search).get("orb") === "demo";

  const [loggedIn, setLoggedIn] = useState(api.authenticated);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [memoryEnabled, setMemoryEnabled] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
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
    Promise.all([api.status(), api.memorySettings(), api.listConversations()])
      .then(([s, memory, list]) => {
        setStatus(s);
        setMemoryEnabled(memory.enabled);
        setConversations(list);
        if (list.length > 0) setCurrent((c) => c ?? list[0].id);
      })
      .catch(handleError);
  }, [api, loggedIn, handleError]);

  useEffect(() => {
    if (!current) {
      setMessages([]);
      return;
    }
    api.messages(current).then(setMessages).catch(handleError);
  }, [api, current, handleError]);

  async function newConversation() {
    setError(null);
    try {
      const conversation = await api.createConversation();
      setConversations((list) => [conversation, ...list]);
      setCurrent(conversation.id);
      setMenuOpen(false);
    } catch (e) {
      handleError(e);
    }
  }

  async function send(text: string) {
    setError(null);
    let conversationId = current;
    try {
      if (!conversationId) {
        const conversation = await api.createConversation();
        setConversations((list) => [conversation, ...list]);
        setCurrent(conversation.id);
        conversationId = conversation.id;
      }
      setSending(true);
      const turn = await api.send(conversationId, text);
      setMessages((list) => [...list, turn.user_message, turn.assistant_message]);
    } catch (e) {
      handleError(e);
      // The user message may have been stored even if the reply failed: reload the transcript.
      if (conversationId) api.messages(conversationId).then(setMessages).catch(() => undefined);
    } finally {
      setSending(false);
    }
  }

  async function toggleMemory() {
    try {
      setMemoryEnabled((await api.setMemoryEnabled(!memoryEnabled)).enabled);
    } catch (e) {
      handleError(e);
    }
  }

  function logout() {
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
      : sending
        ? "THINKING"
        : "IDLE";
  const agentName = status?.identity?.chosen_name ?? null;

  return (
    <div className="app">
      <header className="topbar">
        {loggedIn && !demo && (
          <button className="ghost" onClick={() => setMenuOpen((o) => !o)} aria-expanded={menuOpen}>
            Conversas
          </button>
        )}
        <span className="identity" title={status?.identity?.internal_id}>
          {agentName ?? "sem nome pessoal"}
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
            <button onClick={newConversation}>Nova conversa</button>
            <ul>
              {conversations.map((c) => (
                <li key={c.id}>
                  <button
                    className={c.id === current ? "active" : "ghost"}
                    onClick={() => {
                      setCurrent(c.id);
                      setMenuOpen(false);
                    }}
                  >
                    {new Date(c.created_at).toLocaleString("pt-BR", {
                      dateStyle: "short",
                      timeStyle: "short",
                    })}
                  </button>
                </li>
              ))}
            </ul>
            <label className="memory-toggle">
              <input type="checkbox" checked={memoryEnabled} onChange={toggleMemory} />
              Memória entre conversas
            </label>
            <p className="note">
              Desligada por padrão. Ligada, guarda só o que passar pela curadoria; dá para ver e
              apagar tudo pela API (/memory).
            </p>
          </aside>
        )}

        <main className="main">
          <div className="orb-wrap">
            <Orb state={orbState} level={demoLevel} />
            <p className="state-label">{STATE_LABELS[orbState]}</p>
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
            <ChatView messages={messages} sending={sending} error={error} onSend={send} />
          )}
        </main>
      </div>
      <footer className="footer">Projeto VISÃO · pesquisa experimental</footer>
    </div>
  );
}
