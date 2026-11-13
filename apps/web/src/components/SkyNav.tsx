import type { OrbState } from "../orb/orbModel";
import { STATE_LABELS } from "../orb/Orb";
import { Icon } from "./Icon";
import type { WorkspaceView } from "./Rail";

const TABS: { view: WorkspaceView; label: string }[] = [
  { view: "inbox", label: "Início" },
  { view: "conversation", label: "Chat" },
  { view: "projects", label: "Projetos" },
];

interface SkyNavProps {
  view: WorkspaceView;
  pendingCount: number;
  agentName: string | null;
  menuOpen: boolean;
  onMenu: () => void;
  onView: (view: WorkspaceView) => void;
}

/** The "Céu" top bar: the drawer on the left, the three places in a pill, settings on the right. */
export function SkyNav({ view, pendingCount, agentName, menuOpen, onMenu, onView }: SkyNavProps) {
  const initial = (agentName ?? "Visão").trim().charAt(0).toUpperCase() || "V";
  return (
    <header className="sky-nav">
      <button type="button" className="sky-round" onClick={onMenu} aria-expanded={menuOpen} aria-label="Conversas, Mac e mais">
        <Icon name="menu" size={20} />
      </button>
      <nav className="sky-tabs" aria-label="Seções">
        {TABS.map((tab) => (
          <button key={tab.view} type="button" aria-current={view === tab.view ? "page" : undefined} onClick={() => onView(tab.view)}>
            {tab.label}
            {tab.view === "inbox" && pendingCount > 0 && (
              <span className="sky-badge" aria-label={`${pendingCount} esperando você`}>{pendingCount}</span>
            )}
          </button>
        ))}
      </nav>
      <button
        type="button"
        className="sky-avatar"
        aria-current={view === "settings" ? "page" : undefined}
        onClick={() => onView("settings")}
        aria-label="Ajustes"
        title="Ajustes"
      >
        {initial}
      </button>
    </header>
  );
}

/** The round button left of the message box: Visão's core, and a tap calls it. */
export function SkyOrbButton({ state, canCall, hint, onCall }: { state: OrbState; canCall: boolean; hint: string | null; onCall: () => void }) {
  return (
    <button
      type="button"
      className="sky-orb"
      data-state={state}
      onClick={onCall}
      disabled={!canCall}
      aria-label={canCall ? `Ligar · ${STATE_LABELS[state]}` : hint ?? "Ligar"}
      title={canCall ? "Ligar" : hint ?? undefined}
    >
      <span className="sky-orb-core" aria-hidden="true" />
    </button>
  );
}
