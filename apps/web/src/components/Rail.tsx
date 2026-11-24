import type { ReactNode } from "react";

import type { Conversation } from "../api";
import { Corvo } from "../brand/Corvo";
import { OWNER_NAME } from "../brand/copy";
import { useDragToClose } from "../hooks/useDragToClose";
import { Icon, type IconName } from "./Icon";

export type WorkspaceView =
  | "inbox"
  | "conversation"
  | "projects"
  | "study"
  | "routines"
  | "mac"
  | "agents"
  | "channels"
  | "skills"
  | "settings"
  | "panel";

/** The places, in the mockup's order (docs/design/telas-visao). */
export const NAV: { view: WorkspaceView; label: string; icon: IconName }[] = [
  { view: "inbox", label: "Início", icon: "home" },
  { view: "conversation", label: "Chat", icon: "chat" },
  { view: "projects", label: "Projetos", icon: "folder" },
  { view: "study", label: "Caderno", icon: "notebook" },
  { view: "routines", label: "Rotinas", icon: "clock" },
  { view: "mac", label: "Mac", icon: "laptop" },
  { view: "agents", label: "Agentes", icon: "agents" },
  { view: "channels", label: "Canais", icon: "plug" },
  { view: "skills", label: "Habilidades", icon: "sparkle" },
];

/** The conversations listed under "Recentes": the ones with a title, newest first. The continuous
 * conversation is "Chat" itself, so it is not repeated here. */
export function recentConversations(list: Conversation[], max = 6): Conversation[] {
  return list
    .filter((c) => !c.continuous && c.title?.trim())
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, max);
}

interface RailProps {
  open: boolean;
  view: WorkspaceView;
  online: boolean;
  pendingCount: number;
  conversations: Conversation[];
  currentConversation: string | null;
  preparing: boolean;
  onView: (view: WorkspaceView) => void;
  onNewChat: () => void;
  onSearch: () => void;
  onOpenConversation: (conversation: Conversation) => void;
  /** The "new version" card, when there is one. */
  update?: ReactNode;
  /** Closes the drawer (dragging it left, on a phone). */
  onClose?: () => void;
}

/** The side bar: the crow and VISAO, a new chat and the search, the places, the recent
 * conversations, the update card and you with Ajustes. Fixed on a computer; a drawer below 900 px. */
export function Rail(props: RailProps) {
  const { view, onView } = props;
  const drag = useDragToClose("left", () => props.onClose?.(), 70);
  const recent = recentConversations(props.conversations);
  return (
    <aside
      className={`rail ${props.open ? "open" : ""}`}
      aria-label="Navegação"
      style={drag.offset ? { transform: `translateX(${-drag.offset}px)`, transition: "none" } : undefined}
      {...(props.open ? drag.handlers : {})}
    >
      <a className="rail-brand" href="/" aria-label="VISAO, início">
        <Corvo size={30} />
        <span className="rail-wordmark" aria-hidden="true">VISAO</span>
      </a>
      <div className="rail-actions">
        <button type="button" className="rail-new" onClick={props.onNewChat}>
          <Icon name="plus" size={16} />
          Nova conversa
        </button>
        <button type="button" className="rail-search" onClick={props.onSearch} aria-label="Buscar e comandos (Ctrl K)" title="Buscar e comandos (Ctrl K)">
          <Icon name="search" size={16} />
        </button>
      </div>
      <nav className="rail-nav" aria-label="Lugares">
        {NAV.map((item) => (
          <button
            key={item.view}
            type="button"
            aria-current={view === item.view || (item.view === "inbox" && view === "panel") ? "page" : undefined}
            onClick={() => onView(item.view)}
          >
            <Icon name={item.icon} size={18} />
            <span>{item.label}</span>
            {item.view === "inbox" && props.pendingCount > 0 && (
              <span className="rail-badge" aria-label={`${props.pendingCount} esperando você`}>{props.pendingCount}</span>
            )}
          </button>
        ))}
      </nav>
      {recent.length > 0 && (
        <section className="rail-section" aria-labelledby="rail-recent">
          <h2 id="rail-recent" className="rail-heading">Recentes</h2>
          <ul className="rail-chats">
            {recent.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  aria-current={view === "conversation" && props.currentConversation === c.id ? "page" : undefined}
                  onClick={() => props.onOpenConversation(c)}
                >
                  <span className="rail-chat-dot" aria-hidden="true" />
                  <span className="rail-chat-title">{c.title}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {props.preparing && <p className="note rail-preparing">Lembrando do que importa…</p>}
      <div className="rail-bottom">
        {!props.online && <p className="rail-offline" role="status">Sem conexão com o servidor.</p>}
        {props.update}
        <div className="rail-me">
          <span className="rail-avatar" aria-hidden="true">{OWNER_NAME.charAt(0)}</span>
          <span className="rail-name">{OWNER_NAME}</span>
          <button
            type="button"
            className="rail-settings"
            aria-label="Ajustes"
            title="Ajustes"
            aria-current={view === "settings" ? "page" : undefined}
            onClick={() => onView("settings")}
          >
            <Icon name="gear" size={18} />
          </button>
        </div>
      </div>
    </aside>
  );
}
