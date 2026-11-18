import { type FormEvent, type KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";

import { type Api, type Panel, utcDate } from "../api";
import { HOME_SUGGESTIONS, homeGreeting } from "../brand/copy";
import { Ciclope } from "../ciclope/Ciclope";
import type { AssistantState, CiclopeState } from "../ciclope/state";
import type { Pending } from "../hooks/usePending";
import { dayLabel } from "../labels";
import { Icon } from "./Icon";
import { PanelsBoard } from "./PanelsBoard";
import { MicButton } from "./SkyNav";

export interface CallControls {
  state: AssistantState;
  /** What the Ciclope shows (the state above, plus Mac at work and errors). */
  ciclope: CiclopeState;
  level: () => number;
  levelActive: boolean;
  canCall: boolean;
  speaking: boolean;
  inCall: boolean;
  /** Why calling is not possible here, when it is not. */
  hint: string | null;
  onCall: () => void;
  onStopSpeaking: () => void;
  onOpenSettings: () => void;
}

/** The line under the greeting, from what is really there: what waits and the panels. */
export function homeSummary(pendingCount: number, panels: Pick<Panel, "total">[] | null): string {
  const parts: string[] = [];
  if (pendingCount > 0) parts.push(pendingCount === 1 ? "1 coisa esperando você" : `${pendingCount} coisas esperando você`);
  if (panels && panels.length > 0) {
    const open = panels.filter((p) => p.total === null).length;
    if (open > 0) parts.push(open === 1 ? "1 painel com preço a confirmar" : `${open} painéis com preço a confirmar`);
    else parts.push(panels.length === 1 ? "1 painel em dia" : `${panels.length} painéis em dia`);
  }
  return parts.length ? `${parts.join(" · ")}.` : "Nada esperando por você agora.";
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

interface InboxViewProps {
  api: Api;
  call: CallControls;
  /** Opens the chat with this text in the box (a suggestion, "Criar um novo painel"). */
  onDraft: (text: string) => void;
  /** Sends from Início's box: the chat opens with the message on its way. */
  onSend: (text: string) => void;
  pending: Pending;
  current: string | null;
  onReplied: (conversationId: string) => void;
}

/** Início: the Ciclope and the greeting, a line about the day, the live panels, everything that
 * waits for a yes, a no or a read, and the message box at the bottom. */
export function InboxView({ api, call, onDraft, onSend, pending, current, onReplied }: InboxViewProps) {
  const empty = pending.count === 0;
  const [panels, setPanels] = useState<Panel[] | null>(null);
  const [hello, setHello] = useState(() => homeGreeting());
  const thought = useLatestThought(api);
  const onPanels = useCallback((list: Panel[]) => setPanels(list), []);
  useEffect(() => {
    // The greeting follows the hour while the page stays open.
    const id = setInterval(() => setHello(homeGreeting()), 60_000);
    return () => clearInterval(id);
  }, []);

  return (
    <section className="home" aria-labelledby="home-title">
      <div className="home-scroll">
        <header className="home-hero">
          <Ciclope state={call.ciclope} size={96} level={call.levelActive ? call.level : undefined} lookAt="pointer" />
          <h1 id="home-title" className="home-greeting">
            <span>{hello}</span> O que a gente <em>resolve</em> hoje?
          </h1>
          <p className="home-summary">{homeSummary(pending.count, panels)}</p>
          {call.speaking && (
            <button type="button" className="rs-botao rs-botao--compacto" onClick={call.onStopSpeaking}>Parar de falar</button>
          )}
        </header>

        {thought && (
          <section className="home-card home-thought" aria-labelledby="home-thought">
            <h2 id="home-thought" className="rotulo">Pensando agora</h2>
            <p>{thought.content}</p>
            <time>{dayLabel(utcDate(thought.created_at))}</time>
          </section>
        )}

        <PanelsBoard api={api} nothingPending={empty} onDraft={onDraft} onPanels={onPanels} />

        {pending.panelOffers.length > 0 && (
          <section className="list-group">
            <h2 className="rotulo">Painéis para aprovar</h2>
            {pending.panelOffers.map((o) => (
              <article className="list-item" key={o.id}>
                <div className="list-item-text">
                  <strong>Deixo isto no Início?</strong>
                  <p className="note">{o.summary}</p>
                </div>
                <div className="row">
                  <button type="button" className="primary" onClick={() => void pending.decidePanelOffer(o, "approve")}>Aprovar</button>
                  <button type="button" className="ghost" onClick={() => void pending.decidePanelOffer(o, "reject")}>Recusar</button>
                </div>
              </article>
            ))}
          </section>
        )}
        {pending.armProposals.length > 0 && (
          <section className="list-group">
            <h2 className="rotulo">No Mac</h2>
            {pending.armProposals.map((t) => (
              <article className="list-item" key={t.id}>
                <div className="list-item-text">
                  <strong>Posso fazer em {t.project}?</strong>
                  <p className="note pre">{t.prompt}</p>
                  <time className="panel-time">{dayLabel(utcDate(t.created_at))}</time>
                </div>
                <div className="row">
                  <button type="button" className="primary" onClick={() => void pending.decideArm(t, "approve")}>Aprovar</button>
                  <button type="button" className="ghost" onClick={() => void pending.decideArm(t, "reject")}>Recusar</button>
                </div>
              </article>
            ))}
          </section>
        )}
        {pending.googleActions.length > 0 && (
          <section className="list-group">
            <h2 className="rotulo">Email e agenda</h2>
            {pending.googleActions.map((a) => (
              <article className="list-item" key={a.id}>
                <div className="list-item-text">
                  <strong>{a.kind === "send_email" ? "Posso mandar este email?" : "Posso marcar isto?"}</strong>
                  <p className="note">{a.summary}</p>
                  {a.kind === "send_email" && a.payload.body && <p className="note pre google-body">{a.payload.body}</p>}
                  {a.kind === "create_event" && a.payload.location && <p className="note">Local: {a.payload.location}</p>}
                  <time className="panel-time">{dayLabel(utcDate(a.created_at))}</time>
                </div>
                <div className="row">
                  <button type="button" className="primary" onClick={() => void pending.decideGoogle(a, "approve")}>Aprovar</button>
                  <button type="button" className="ghost" onClick={() => void pending.decideGoogle(a, "reject")}>Recusar</button>
                </div>
              </article>
            ))}
          </section>
        )}
        {pending.goals.length > 0 && (
          <section className="list-group">
            <h2 className="rotulo">Metas que eu quero seguir</h2>
            {pending.goals.map((g) => (
              <article className="list-item" key={g.id}>
                <div className="list-item-text">
                  <strong>{g.title}</strong>
                  <p className="note">{g.rationale}</p>
                  {g.required_permissions.length > 0 && <p className="note">Preciso de: {g.required_permissions.join(", ")}</p>}
                </div>
                <div className="row">
                  <button type="button" className="primary" onClick={() => void pending.decideGoal(g, "approve")}>Aprovar</button>
                  <button type="button" className="ghost" onClick={() => void pending.decideGoal(g, "reject")}>Recusar</button>
                </div>
              </article>
            ))}
          </section>
        )}
        {pending.notices.length > 0 && (
          <section className="list-group">
            <h2 className="rotulo">Avisos</h2>
            {pending.notices.map((n) => (
              <article className="list-item" key={n.id}>
                <div className="list-item-text">
                  <strong>{n.title}</strong>
                  <p className="note pre">{n.body}</p>
                  <time className="panel-time">{dayLabel(utcDate(n.created_at))}</time>
                </div>
                <div className="row">
                  <button
                    type="button"
                    className="primary"
                    onClick={() => void pending.reply(n, current).then((id) => { if (id) onReplied(id); })}
                  >
                    Responder
                  </button>
                  <button type="button" className="ghost" onClick={() => void pending.dismiss(n)}>Dispensar</button>
                </div>
              </article>
            ))}
          </section>
        )}
        {empty && <p className="note page-empty">Eu só proponho: quando eu quiser fazer algo por conta própria, aparece aqui primeiro.</p>}
      </div>

      <HomeComposer call={call} onSend={onSend} />
    </section>
  );
}

/** Início's message box: suggestions above, the microphone on the left, send on the right. */
function HomeComposer({ call, onSend }: { call: CallControls; onSend: (text: string) => void }) {
  const [draft, setDraft] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const text = draft.trim();
    if (!text) return;
    onSend(text);
    setDraft("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="home-dock">
      <ul className="suggestion-chips" aria-label="Sugestões">
        {HOME_SUGGESTIONS.map((s) => (
          <li key={s.label}>
            <button
              type="button"
              className="chip-button"
              onClick={() => {
                setDraft(s.draft);
                box.current?.focus();
              }}
            >
              {s.label}
            </button>
          </li>
        ))}
      </ul>
      <form className="composer composer--home" onSubmit={submit}>
        <div className="composer-row">
          <MicButton canCall={call.canCall} hint={call.hint} onCall={call.onCall} live={call.inCall} />
          <textarea
            ref={box}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Escreva ou toque no microfone…"
            rows={1}
            maxLength={8000}
            aria-label="Mensagem"
          />
          <button type="submit" className="composer-send" aria-label="Enviar mensagem" disabled={!draft.trim()}>
            <Icon name="send" size={20} />
          </button>
        </div>
      </form>
      {call.hint && !call.canCall && (
        <p className="note home-hint">
          {call.hint} <button type="button" className="link-button" onClick={call.onOpenSettings}>Abrir ajustes</button>
        </p>
      )}
    </div>
  );
}
