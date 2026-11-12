import { type Api, type Conversation, utcDate } from "../api";
import { InitiativesPanel } from "./InitiativesPanel";
import { PushToggle } from "./PushToggle";

export type WorkspaceView = "conversation" | "study";

interface SidebarProps {
  api: Api;
  open: boolean;
  view: WorkspaceView;
  conversations: Conversation[];
  current: string | null;
  busy: boolean;
  preparing: boolean;
  online: boolean;
  memoryEnabled: boolean;
  speakReplies: boolean;
  canSpeak: boolean;
  speakerKind: "server" | "device" | null;
  deviceListening: boolean;
  deviceCouldListen: boolean;
  serverListening: boolean;
  onView: (view: WorkspaceView) => void;
  onNewConversation: () => void;
  onSelect: (id: string) => void;
  onToggleMemory: () => void;
  onToggleSpeak: () => void;
  onToggleDeviceListening: () => void;
  onError: (e: unknown) => void;
}

function label(c: Conversation): string {
  return utcDate(c.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function Sidebar(props: SidebarProps) {
  const { api, open, view, conversations, current, busy, preparing, online, onView, onError } = props;
  return (
    <aside className={`sidebar ${open ? "open" : ""}`} aria-label="Conversas e preferências">
      <nav className="workspace-nav" aria-label="Navegação principal">
        <button type="button" aria-current={view === "conversation" ? "page" : undefined} onClick={() => onView("conversation")}>Conversa</button>
        <button type="button" aria-current={view === "study" ? "page" : undefined} onClick={() => onView("study")}>Caderno</button>
      </nav>
      <button type="button" className="rs-botao new-conversation" onClick={props.onNewConversation} disabled={busy}>
        {preparing ? "Lembrando do que importa…" : "Nova conversa"}
      </button>
      <p className="rotulo history-label">Conversas</p>
      <ul className="conversation-list">
        {conversations.map((c) => (
          <li key={c.id}>
            <button type="button" aria-current={c.id === current ? "true" : undefined} onClick={() => props.onSelect(c.id)}>
              {label(c)}
            </button>
          </li>
        ))}
        {conversations.length === 0 && <li className="note">Nenhuma ainda.</li>}
      </ul>
      <details className="preferences">
        <summary>Preferências e autonomia <span aria-hidden="true">+</span></summary>
        <div className="preferences-content">
          <InitiativesPanel api={api} onError={onError} />
          <PushToggle api={api} onError={onError} />
          <div className="preference">
            <label className="memory-toggle">
              <input type="checkbox" checked={props.memoryEnabled} onChange={props.onToggleMemory} />
              Memória entre conversas
            </label>
            <p className="note">Guardo o que você escolher para continuar de onde paramos.</p>
          </div>
          <div className="preference">
            <label className="memory-toggle">
              <input type="checkbox" checked={props.speakReplies} onChange={props.onToggleSpeak} disabled={!props.canSpeak} />
              Falar as respostas
            </label>
            <p className="note">
              {!props.canSpeak
                ? "Sem voz neste aparelho."
                : props.speakerKind === "device"
                  ? "Uso a voz do aparelho: o servidor não tem modelos de voz."
                  : "Leio as respostas com a voz que escolhi."}
            </p>
          </div>
          {!props.serverListening && props.deviceCouldListen && (
            <div className="preference">
              <label className="memory-toggle">
                <input type="checkbox" checked={props.deviceListening} onChange={props.onToggleDeviceListening} />
                Ouvir pelo navegador
              </label>
              <p className="note">
                Para ligar sem os modelos de voz do servidor. O navegador pode enviar o áudio ao
                fabricante dele (Google no Chrome, Apple no Safari).
              </p>
            </div>
          )}
        </div>
      </details>
      <div className="sidebar-bottom">
        <span className={`connection ${online ? "on" : "off"}`}>{online ? "✓ Conectado" : "× Sem conexão"}</span>
        <span className="rotulo">Projeto experimental</span>
      </div>
    </aside>
  );
}
