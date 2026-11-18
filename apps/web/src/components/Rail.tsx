import { Ciclope } from "../ciclope/Ciclope";
import { Critter } from "../ciclope/Family";
import { Lockup } from "../brand/Lockup";
import { OWNER_NAME } from "../brand/copy";
import { useDragToClose } from "../hooks/useDragToClose";
import { Icon, type IconName } from "./Icon";

export type WorkspaceView = "conversation" | "inbox" | "projects" | "study" | "mac" | "settings";

const NAV: { view: WorkspaceView; label: string; icon: IconName }[] = [
  { view: "inbox", label: "Início", icon: "home" },
  { view: "conversation", label: "Chat", icon: "chat" },
  { view: "projects", label: "Projetos", icon: "folder" },
  { view: "study", label: "Caderno", icon: "notebook" },
  { view: "mac", label: "Mac", icon: "laptop" },
];

interface RailProps {
  open: boolean;
  view: WorkspaceView;
  preparing: boolean;
  online: boolean;
  pendingCount: number;
  /** null: no Mac paired yet. */
  macOnline: boolean | null;
  onView: (view: WorkspaceView) => void;
  /** Closes the drawer (dragging it left, on a phone). */
  onClose?: () => void;
}

/** The side bar: the logo, the places, and at the bottom the connection, you and Ajustes. Fixed
 * on a computer; a drawer below 900 px. */
export function Rail(props: RailProps) {
  const { view, onView } = props;
  const drag = useDragToClose("left", () => props.onClose?.(), 70);
  const status = !props.online
    ? { text: "Sem conexão", sleeping: "ciclope" as const }
    : props.macOnline === false
      ? { text: "Mac offline", sleeping: "mac" as const }
      : { text: "Conectado", sleeping: null };
  return (
    <aside
      className={`rail ${props.open ? "open" : ""}`}
      aria-label="Navegação"
      style={drag.offset ? { transform: `translateX(${-drag.offset}px)`, transition: "none" } : undefined}
      {...(props.open ? drag.handlers : {})}
    >
      <a className="rail-brand" href="/" aria-label="V.I.S.A.O., início">
        <Lockup />
      </a>
      <nav className="rail-nav" aria-label="Seções">
        {NAV.map((item) => (
          <button key={item.view} type="button" aria-current={view === item.view ? "page" : undefined} onClick={() => onView(item.view)}>
            <Icon name={item.icon} size={20} />
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
      {props.preparing && <p className="note rail-preparing">Lembrando do que importa…</p>}
      <div className="rail-bottom">
        <span className={`rail-status${status.sleeping ? " rail-status--off" : ""}`} role="status">
          {status.sleeping === "ciclope" && <Ciclope state="offline" size={18} animated={false} decorative />}
          {status.sleeping === "mac" && <Critter kind="mac" size={18} asleep />}
          {!status.sleeping && <span className="rail-status-dot" aria-hidden="true" />}
          {status.text}
        </span>
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
            <Icon name="gear" size={20} />
          </button>
        </div>
      </div>
    </aside>
  );
}
