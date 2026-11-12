import { useEffect, useState } from "react";

import { type Api, utcDate } from "../api";
import type { Pending } from "../hooks/usePending";
import { dayLabel } from "../labels";
import { Orb, STATE_LABELS } from "../orb/Orb";
import type { OrbState } from "../orb/orbModel";
import { Icon } from "./Icon";

export interface CallControls {
  state: OrbState;
  level: () => number;
  levelActive: boolean;
  canCall: boolean;
  speaking: boolean;
  /** Why calling is not possible here, when it is not. */
  hint: string | null;
  onCall: () => void;
  onStopSpeaking: () => void;
  onOpenSettings: () => void;
}

/** The orb, its state and the call button: compact in the conversation header on smaller screens. */
export function Presence({ call, size = 72, compact }: { call: CallControls; size?: number; compact?: boolean }) {
  return (
    <div className={`presence ${compact ? "presence--compacta" : ""}`}>
      {/* The orb's particles are drawn for a big canvas; small, it reads as a blob. */}
      {!compact && (
        <div className="orb-wrap" style={{ width: size, height: size }}>
          <Orb state={call.state} size={size} getLevel={call.levelActive ? call.level : undefined} />
        </div>
      )}
      <div className="presence-copy">
        <p className="rotulo state-label">{STATE_LABELS[call.state]}</p>
        <div className="call-start">
          <button type="button" className="rs-botao rs-botao--principal call-button" onClick={call.onCall} disabled={!call.canCall}>
            <Icon name="phone" size={16} /> Ligar
          </button>
          {call.speaking && <button type="button" className="rs-botao call-button" onClick={call.onStopSpeaking}>Parar de falar</button>}
        </div>
        {call.hint && !compact && (
          <p className="note presence-hint">
            {call.hint} <button type="button" className="link-button" onClick={call.onOpenSettings}>Abrir ajustes</button>
          </p>
        )}
      </div>
    </div>
  );
}

const THOUGHT_POLL_MS = 30_000;

function useLatestThought(api: Api): { content: string; created_at: string } | null {
  const [thought, setThought] = useState<{ content: string; created_at: string } | null>(null);
  useEffect(() => {
    let alive = true;
    const poll = () =>
      api.mind().then(
        (mind) => { if (alive) setThought(mind.enabled ? mind.thoughts[0] ?? null : null); },
        () => undefined,
      );
    void poll();
    const id = setInterval(poll, THOUGHT_POLL_MS);
    return () => { alive = false; clearInterval(id); };
  }, [api]);
  return thought;
}

interface PanelProps {
  api: Api;
  call: CallControls;
  pending: Pending;
  onOpen: (view: "inbox" | "mac") => void;
}

/** Beside the conversation on wide screens: how it is, what it is thinking, what waits for you. */
export function PresencePanel({ api, call, pending, onOpen }: PanelProps) {
  const thought = useLatestThought(api);
  const mac = pending.devices[0];
  const waiting = [
    ...pending.armProposals.map((t) => ({ key: t.id, title: `${t.prompt}`, where: t.project, approve: () => pending.decideArm(t, "approve"), reject: () => pending.decideArm(t, "reject") })),
    ...pending.googleActions.map((a) => ({ key: a.id, title: a.summary, where: a.kind === "send_email" ? "email" : "agenda", approve: () => pending.decideGoogle(a, "approve"), reject: () => pending.decideGoogle(a, "reject") })),
    ...pending.goals.map((g) => ({ key: g.id, title: g.title, where: null, approve: () => pending.decideGoal(g, "approve"), reject: () => pending.decideGoal(g, "reject") })),
  ];
  return (
    <aside className="presence-panel" aria-label="Presença">
      <Presence call={call} size={72} />
      {thought && (
        <section className="panel-block">
          <h2 className="rotulo">Pensando agora</h2>
          <p className="panel-thought">{thought.content}</p>
          <time className="panel-time">{dayLabel(utcDate(thought.created_at))}</time>
        </section>
      )}
      <section className="panel-block">
        <h2 className="rotulo">Esperando você{pending.count > 0 && ` · ${pending.count}`}</h2>
        {pending.count === 0 && <p className="note">Nada agora.</p>}
        {waiting.slice(0, 3).map((item) => (
          <div className="panel-ask" key={item.key}>
            <p>{item.where && <span className="panel-where">{item.where}</span>}{item.title}</p>
            <div className="row">
              <button type="button" onClick={() => void item.approve()}>Aprovar</button>
              <button type="button" className="ghost" onClick={() => void item.reject()}>Recusar</button>
            </div>
          </div>
        ))}
        {pending.notices.length > 0 && <p className="note">{pending.notices.length === 1 ? "1 aviso" : `${pending.notices.length} avisos`} para ler.</p>}
        {(pending.count > 3 || pending.notices.length > 0) && (
          <button type="button" className="link-button" onClick={() => onOpen("inbox")}>Ver tudo</button>
        )}
      </section>
      <section className="panel-block">
        <h2 className="rotulo">Mac</h2>
        {mac ? (
          <p className="note">
            <span className={`status-dot ${mac.online ? "on" : ""}`} aria-hidden="true" />
            {mac.online ? "Ligado" : "Desligado"}{mac.projects.length > 0 && ` · ${mac.projects.join(", ")}`}
          </p>
        ) : (
          <button type="button" className="link-button" onClick={() => onOpen("mac")}>Conectar o Mac</button>
        )}
      </section>
    </aside>
  );
}
