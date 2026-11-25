import { Corvo } from "../brand/Corvo";
import { Icon, type IconName } from "./Icon";
import type { WorkspaceView } from "./Rail";

interface MobileBarProps {
  title: string;
  online: boolean;
  pendingCount: number;
  menuOpen: boolean;
  onMenu: () => void;
  onHome: () => void;
}

/** Below 900 px: the crow and where you are, whether the server answers, and the menu with the
 * other places. */
export function MobileBar({ title, online, pendingCount, menuOpen, onMenu, onHome }: MobileBarProps) {
  return (
    <header className="mobile-bar">
      <button type="button" className="mobile-bar-brand" onClick={onHome} aria-label="VISAO, Início">
        <Corvo size={26} />
      </button>
      <span className="mobile-bar-title">{title}</span>
      <span className={`mobile-bar-status${online ? " on" : ""}`}>{online ? "ok" : "sem conexão"}</span>
      <button type="button" className="mobile-bar-button" onClick={onMenu} aria-expanded={menuOpen} aria-label="Abrir o menu">
        <Icon name="menu" size={22} />
        {pendingCount > 0 && <span className="mobile-bar-badge" aria-label={`${pendingCount} esperando você`}>{pendingCount}</span>}
      </button>
    </header>
  );
}

const TABS: { view: WorkspaceView; label: string; icon: IconName }[] = [
  { view: "inbox", label: "Início", icon: "home" },
  { view: "conversation", label: "Chat", icon: "chat" },
  { view: "study", label: "Caderno", icon: "notebook" },
  { view: "routines", label: "Rotinas", icon: "clock" },
];

/** Below 900 px: the four places at the bottom of the screen. */
export function MobileTabs({ view, onView }: { view: WorkspaceView; onView: (view: WorkspaceView) => void }) {
  return (
    <nav className="mobile-tabs" aria-label="Lugares principais">
      {TABS.map((t) => (
        <button key={t.view} type="button" aria-current={view === t.view ? "page" : undefined} onClick={() => onView(t.view)}>
          <Icon name={t.icon} size={20} />
          <span>{t.label}</span>
        </button>
      ))}
    </nav>
  );
}

/** The microphone left of the message box: a tap starts a voice call (the ring listens). */
export function MicButton({ canCall, hint, onCall, live, onExplain }: { canCall: boolean; hint: string | null; onCall: () => void; live?: boolean; onExplain?: () => void }) {
  // When a call is not possible here, a tap says why and opens the voice settings, instead of a
  // dead button (the sentence about it no longer sits under the box on a phone).
  const explains = !canCall && !!onExplain;
  return (
    <button
      type="button"
      className={`mic-button${live ? " mic-button--live" : ""}${explains ? " mic-button--off" : ""}`}
      onClick={explains ? onExplain : onCall}
      disabled={!canCall && !explains}
      aria-label={canCall ? "Falar (ligar por voz)" : hint ?? "Falar"}
      title={canCall ? "Falar" : hint ?? undefined}
    >
      <Icon name="mic" size={22} />
    </button>
  );
}
