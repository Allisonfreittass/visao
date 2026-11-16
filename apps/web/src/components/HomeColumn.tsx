import type { Api } from "../api";
import type { Pending } from "../hooks/usePending";
import { PanelsBoard } from "./PanelsBoard";
import { type CallControls, PresencePanel } from "./Presence";

interface HomeColumnProps {
  api: Api;
  call: CallControls;
  pending: Pending;
  onOpen: (view: "inbox" | "mac") => void;
  onDraft: (text: string) => void;
}

/** The left column on a computer: Início as cards (presence, what waits, the Mac, the panels). */
export function HomeColumn({ api, call, pending, onOpen, onDraft }: HomeColumnProps) {
  return (
    <div className="home-column">
      <PresencePanel api={api} call={call} pending={pending} onOpen={onOpen} />
      <div className="panel-block home-panels">
        <PanelsBoard api={api} nothingPending={pending.count === 0} onDraft={onDraft} />
      </div>
    </div>
  );
}
