import { Lockup } from "../brand/Lockup";
import { OWNER_NAME } from "../brand/copy";
import type { AnelEstado } from "../anel/state";
import { Icon } from "./Icon";
import type { WorkspaceView } from "./Rail";

interface MobileBarProps {
  view: WorkspaceView;
  pendingCount: number;
  anel: AnelEstado;
  menuOpen: boolean;
  onMenu: () => void;
  onView: (view: WorkspaceView) => void;
}

/** Below 900 px: the drawer button, the logo, and the avatar that opens Ajustes. */
export function MobileBar({ view, pendingCount, anel, menuOpen, onMenu, onView }: MobileBarProps) {
  return (
    <header className="mobile-bar">
      <button type="button" className="mobile-bar-button" onClick={onMenu} aria-expanded={menuOpen} aria-label="Abrir o menu">
        <Icon name="menu" size={22} />
        {pendingCount > 0 && <span className="mobile-bar-badge" aria-label={`${pendingCount} esperando você`}>{pendingCount}</span>}
      </button>
      <button type="button" className="mobile-bar-brand" onClick={() => onView("inbox")} aria-label="V.I.S.A.O., Início">
        <Lockup estado={anel} size={26} animated />
      </button>
      <button
        type="button"
        className="mobile-bar-avatar"
        aria-current={view === "settings" ? "page" : undefined}
        onClick={() => onView("settings")}
        aria-label="Ajustes"
        title="Ajustes"
      >
        {OWNER_NAME.charAt(0)}
      </button>
    </header>
  );
}

/** The microphone left of the message box: a tap starts a voice call (the ring listens). */
export function MicButton({ canCall, hint, onCall, live }: { canCall: boolean; hint: string | null; onCall: () => void; live?: boolean }) {
  return (
    <button
      type="button"
      className={`mic-button${live ? " mic-button--live" : ""}`}
      onClick={onCall}
      disabled={!canCall}
      aria-label={canCall ? "Falar (ligar por voz)" : hint ?? "Falar"}
      title={canCall ? "Falar" : hint ?? undefined}
    >
      <Icon name="mic" size={22} />
    </button>
  );
}
