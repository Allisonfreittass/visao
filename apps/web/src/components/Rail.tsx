import { useDragToClose } from "../hooks/useDragToClose";
import { Icon, type IconName } from "./Icon";

export type WorkspaceView = "conversation" | "inbox" | "projects" | "study" | "mac" | "settings";

const NAV: { view: WorkspaceView; label: string; icon: IconName }[] = [
  { view: "inbox", label: "Início", icon: "inbox" },
  { view: "conversation", label: "Chat", icon: "chat" },
  { view: "projects", label: "Projetos", icon: "folder" },
  { view: "study", label: "Caderno", icon: "notebook" },
  { view: "mac", label: "Mac", icon: "laptop" },
  { view: "settings", label: "Ajustes", icon: "sliders" },
];

interface RailProps {
  open: boolean;
  view: WorkspaceView;
  preparing: boolean;
  online: boolean;
  pendingCount: number;
  /** null: no Mac paired yet. */
  macOnline: boolean | null;
  /** Sections already in the pill at the top: the drawer leaves them out (same names, one place). */
  inPill?: WorkspaceView[];
  onView: (view: WorkspaceView) => void;
  /** Closes the drawer (dragging it left, on a phone). */
  onClose?: () => void;
}

/** Where everything is: the sections ("Chat" is the continuous one), then the connection. */
export function Rail(props: RailProps) {
  const { view, onView } = props;
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
        {NAV.filter((item) => !props.inPill?.includes(item.view)).map((item) => (
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
      {props.preparing && <p className="note rail-preparing">Lembrando do que importa…</p>}
      <div className="rail-bottom">
        <span className={`connection ${props.online ? "on" : "off"}`}>{props.online ? "Conectado" : "Sem conexão"}</span>
      </div>
    </aside>
  );
}
