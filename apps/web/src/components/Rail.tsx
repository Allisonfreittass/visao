import { type Conversation, utcDate } from "../api";
import { dayLabel } from "../labels";
import { useDragToClose } from "../hooks/useDragToClose";
import { Icon, type IconName } from "./Icon";

export type WorkspaceView = "conversation" | "inbox" | "projects" | "study" | "mac" | "settings";

const NAV: { view: WorkspaceView; label: string; icon: IconName }[] = [
  { view: "conversation", label: "Conversa", icon: "chat" },
  { view: "inbox", label: "Pendências", icon: "inbox" },
  { view: "projects", label: "Projetos", icon: "folder" },
  { view: "study", label: "Caderno", icon: "notebook" },
  { view: "mac", label: "Mac", icon: "laptop" },
  { view: "settings", label: "Ajustes", icon: "sliders" },
];

interface RailProps {
  open: boolean;
  view: WorkspaceView;
  conversations: Conversation[];
  current: string | null;
  busy: boolean;
  preparing: boolean;
  online: boolean;
  pendingCount: number;
  /** null: no Mac paired yet. */
  macOnline: boolean | null;
  onView: (view: WorkspaceView) => void;
  onNewConversation: () => void;
  onSelect: (id: string) => void;
  /** Closes the drawer (dragging it left, on a phone). */
  onClose?: () => void;
}

/** Where everything is: the sections, then the conversations, then whether we're connected. */
export function Rail(props: RailProps) {
  const { view, conversations, current, onView } = props;
  const drag = useDragToClose("left", () => props.onClose?.(), 70);
  return (
    <aside
      className={`rail ${props.open ? "open" : ""}`}
      aria-label="Navegação"
      style={drag.offset ? { transform: `translateX(${-drag.offset}px)`, transition: "none" } : undefined}
      {...(props.open ? drag.handlers : {})}
    >
      <a className="brand rail-brand" href="/" aria-label="V.I.S.A.O., início">V.I.S.A.O.</a>
      <nav className="rail-nav" aria-label="Seções">
        {NAV.map((item) => (
          <button key={item.view} type="button" aria-current={view === item.view ? "page" : undefined} onClick={() => onView(item.view)}>
            <Icon name={item.icon} />
            <span>{item.label}</span>
            {item.view === "inbox" && props.pendingCount > 0 && (
              <span className="rail-badge" aria-label={`${props.pendingCount} esperando você`}>{props.pendingCount}</span>
            )}
            {item.view === "mac" && props.macOnline !== null && (
              <span className={`rail-dot ${props.macOnline ? "on" : ""}`} aria-label={props.macOnline ? "ligado" : "desligado"} />
            )}
          </button>
        ))}
      </nav>
      <div className="rail-history">
        <div className="rail-history-head">
          <span className="rotulo">Conversas</span>
          <button type="button" className="rail-new" onClick={props.onNewConversation} disabled={props.busy} aria-label="Nova conversa" title="Nova conversa">
            <Icon name="plus" size={16} />
          </button>
        </div>
        {props.preparing && <p className="note rail-preparing">Lembrando do que importa…</p>}
        <ul className="conversation-list">
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                aria-current={c.id === current && view === "conversation" ? "true" : undefined}
                onClick={() => props.onSelect(c.id)}
              >
                {dayLabel(utcDate(c.created_at))}
              </button>
            </li>
          ))}
          {conversations.length === 0 && <li className="note">Nenhuma ainda.</li>}
        </ul>
      </div>
      <div className="rail-bottom">
        <span className={`connection ${props.online ? "on" : "off"}`}>{props.online ? "Conectado" : "Sem conexão"}</span>
      </div>
    </aside>
  );
}
