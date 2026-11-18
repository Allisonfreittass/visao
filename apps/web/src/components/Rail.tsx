import { useEffect, useState } from "react";

import type { Api } from "../api";
import { Lockup } from "../brand/Lockup";
import { OWNER_NAME } from "../brand/copy";
import type { CiclopeState } from "../ciclope/state";
import { Critter, type CritterKind } from "../ciclope/Family";
import { useDragToClose } from "../hooks/useDragToClose";
import { Icon, type IconName } from "./Icon";

export type WorkspaceView = "conversation" | "inbox" | "projects" | "study" | "mac" | "settings";

// The Mac is not here: it lives under Integrações.
const NAV: { view: WorkspaceView; label: string; icon: IconName }[] = [
  { view: "inbox", label: "Início", icon: "home" },
  { view: "conversation", label: "Chat", icon: "chat" },
  { view: "projects", label: "Projetos", icon: "folder" },
  { view: "study", label: "Caderno", icon: "notebook" },
];

interface RailProps {
  api: Api;
  open: boolean;
  view: WorkspaceView;
  preparing: boolean;
  online: boolean;
  pendingCount: number;
  /** null: no Mac paired yet. */
  macOnline: boolean | null;
  /** The mascot's live state, for the logo. */
  ciclope?: CiclopeState;
  onView: (view: WorkspaceView) => void;
  /** Closes the drawer (dragging it left, on a phone). */
  onClose?: () => void;
}

/** Whether Google (e-mail and calendar) is connected; null until known. Read only. */
function useGoogleConnected(api: Api): boolean | null {
  const [connected, setConnected] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    api.google().then((g) => alive && setConnected(g.connected), () => alive && setConnected(null));
    return () => { alive = false; };
  }, [api]);
  return connected;
}

/** The side bar: the logo, the places, the integrations with their real status, and you with
 * Ajustes at the bottom. Fixed on a computer; a drawer below 900 px. */
export function Rail(props: RailProps) {
  const { view, onView } = props;
  const drag = useDragToClose("left", () => props.onClose?.(), 70);
  const google = useGoogleConnected(props.api);
  const integrations: { kind: CritterKind; label: string; on: boolean | null; open: WorkspaceView; idle: string }[] = [
    { kind: "mac", label: "Mac", on: props.online ? props.macOnline : false, open: "mac", idle: "Não pareado" },
    { kind: "email", label: "E-mail", on: props.online ? google : false, open: "settings", idle: "Não conectado" },
  ];
  return (
    <aside
      className={`rail ${props.open ? "open" : ""}`}
      aria-label="Navegação"
      style={drag.offset ? { transform: `translateX(${-drag.offset}px)`, transition: "none" } : undefined}
      {...(props.open ? drag.handlers : {})}
    >
      <a className="rail-brand" href="/" aria-label="V.I.S.A.O., início">
        <Lockup state={props.ciclope} />
      </a>
      <nav className="rail-nav" aria-label="Seções">
        {NAV.map((item) => (
          <button key={item.view} type="button" aria-current={view === item.view ? "page" : undefined} onClick={() => onView(item.view)}>
            <Icon name={item.icon} size={20} />
            <span>{item.label}</span>
            {item.view === "inbox" && props.pendingCount > 0 && (
              <span className="rail-badge" aria-label={`${props.pendingCount} esperando você`}>{props.pendingCount}</span>
            )}
          </button>
        ))}
      </nav>
      <section className="rail-section" aria-labelledby="rail-integrations">
        <h2 id="rail-integrations" className="rail-heading">Integrações</h2>
        <ul className="rail-integrations">
          {integrations.map((i) => (
            <li key={i.kind}>
              <button type="button" aria-current={view === i.open && i.kind === "mac" ? "page" : undefined} onClick={() => onView(i.open)}>
                <Critter kind={i.kind} size={28} asleep={i.on !== true} />
                <span className="rail-integration-text">
                  <span>{i.label}</span>
                  <small className={i.on ? "on" : ""}>
                    {i.on ? "● Conectado" : !props.online ? "Sem conexão" : i.on === false ? "Desconectado" : i.idle}
                  </small>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>
      {props.preparing && <p className="note rail-preparing">Lembrando do que importa…</p>}
      <div className="rail-bottom">
        {!props.online && <p className="rail-offline" role="status">Sem conexão com o servidor.</p>}
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
