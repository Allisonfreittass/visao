import { type Api, type Conversation, utcDate } from "../api";
import type { Pending } from "../hooks/usePending";
import { conversationLabel } from "../labels";
import { PanelsBoard } from "./PanelsBoard";
import { type CallControls, PresencePanel } from "./Presence";

interface HomeColumnProps {
  api: Api;
  call: CallControls;
  pending: Pending;
  conversations: Conversation[];
  current: string | null;
  busy: boolean;
  onOpen: (view: "inbox" | "mac") => void;
  onSelect: (id: string) => void;
  onNewConversation: () => void;
  onDraft: (text: string) => void;
}

/** The left column on a computer: Início as cards (presence, what waits, the Mac) and the chats. */
export function HomeColumn({ api, call, pending, conversations, current, busy, onOpen, onSelect, onNewConversation, onDraft }: HomeColumnProps) {
  return (
    <div className="home-column">
      <PresencePanel api={api} call={call} pending={pending} onOpen={onOpen} />
      <div className="panel-block home-panels">
        <PanelsBoard api={api} nothingPending={pending.count === 0} onDraft={onDraft} />
      </div>
      <section className="panel-block home-chats">
        <div className="home-chats-head">
          <h2 className="rotulo">Conversas</h2>
          <button type="button" className="home-new" onClick={onNewConversation} disabled={busy}>+ Nova</button>
        </div>
        <ul>
          {conversations.slice(0, 8).map((c) => (
            <li key={c.id}>
              <button type="button" aria-current={c.id === current ? "true" : undefined} onClick={() => onSelect(c.id)}>
                {conversationLabel(c, utcDate)}
              </button>
            </li>
          ))}
          {conversations.length === 0 && <li className="note">Nenhuma ainda.</li>}
        </ul>
      </section>
    </div>
  );
}
