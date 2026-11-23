import { type FormEvent, type KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";

import { type Api, type Panel, utcDate } from "../api";
import { homeGreeting } from "../brand/copy";
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

/** "2 painéis" (a non-breaking space between the number and the word). */
export function watchCount(panels: Pick<Panel, "status">[] | null): string | null {
  const watched = (panels ?? []).filter((p) => p.status !== "paused").length;
  if (watched === 0) return null;
  return `${watched}\u00a0${watched === 1 ? "painel" : "painéis"}`;
}

interface StatusSignals {
  online: boolean;
  /** null: no Mac paired. */
  macOnline: boolean | null;
  pendingCount: number;
  panels: Pick<Panel, "items">[] | null;
}

/** The status line under the greeting, from real data: "Sistemas prontos · Mac conectado ·
 * 1 voo aguardando preço". */
export function statusLine({ online, macOnline, pendingCount, panels }: StatusSignals): string {
  if (!online) return "Sem conexão com o servidor.";
  const parts = ["Sistemas prontos"];
  if (macOnline === true) parts.push("Mac conectado");
  if (macOnline === false) parts.push("Sem conexão com o Mac");
  const items = (panels ?? []).flatMap((p) => p.items).filter((i) => i.cost === null);
  const flights = items.filter((i) => i.kind === "flight").length;
  const hotels = items.length - flights;
  if (flights) parts.push(`${flights} ${flights === 1 ? "voo aguardando" : "voos aguardando"} preço`);
  if (hotels) parts.push(`${hotels} ${hotels === 1 ? "hospedagem aguardando" : "hospedagens aguardando"} preço`);
  if (pendingCount) parts.push(`${pendingCount} ${pendingCount === 1 ? "pedido esperando" : "pedidos esperando"} você`);
  return parts.join(" · ");
}

interface Suggestion {
  label: string;
  draft?: string;
  open?: () => void;
}

/** The chips over the message box, from what is there: always the day's report; watching the
 * flights when a panel has one; opening the first project. */
export function homeSuggestions(panels: Pick<Panel, "title" | "items">[] | null, project: { id: string; name: string } | null, openProject: (id: string) => void): Suggestion[] {
  const list: Suggestion[] = [{ label: "Relatório do dia", draft: "Me dá o relatório do dia" }];
  const flight = (panels ?? []).find((p) => p.items.some((i) => i.kind === "flight"));
  if (flight) list.push({ label: "Vigiar preço dos voos", draft: `Vigie o preço dos voos de «${flight.title}» e me avise se cair` });
  else list.push({ label: "Vigiar um preço", draft: "Quero acompanhar " });
  if (project) list.push({ label: `Abrir projeto ${project.name}`, open: () => openProject(project.id) });
  else list.push({ label: "Pedir ao Mac", draft: "/mac " });
  return list;
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
  online: boolean;
  /** null: no Mac paired. */
  macOnline: boolean | null;
  /** A project to offer in the chips (the first one), if any. */
  project: { id: string; name: string } | null;
  onOpenProject: (id: string) => void;
}

/** Início: the Ciclope and the greeting, a line about the day, the live panels, everything that
 * waits for a yes, a no or a read, and the message box at the bottom. */
export function InboxView({ api, call, onDraft, onSend, pending, current, onReplied, online, macOnline, project, onOpenProject }: InboxViewProps) {
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
            <span>{hello}</span> {watchCount(panels) ? <>Estou de olho em <em>{watchCount(panels)}</em>.</> : "Nada sob vigilância ainda."}
          </h1>
          <p className="home-summary">{statusLine({ online, macOnline, pendingCount: pending.count, panels })}</p>
          {call.speaking && (
            <button type="button" className="rs-botao rs-botao--compacto" onClick={call.onStopSpeaking}>Parar de falar</button>
          )}
        </header>

        {thought && (
          <section className="home-card home-thought" aria-labelledby="home-thought">
            <h2 id="home-thought" className="rotulo">Em análise</h2>
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
        {empty && <p className="note page-empty">Nada esperando você. O que eu quiser fazer por conta própria aparece aqui antes.</p>}
      </div>

      <HomeComposer call={call} onSend={onSend} suggestions={homeSuggestions(panels, project, onOpenProject)} />
    </section>
  );
}

/** Início's message box: suggestions above, the microphone on the left, send on the right. */
function HomeComposer({ call, onSend, suggestions }: { call: CallControls; onSend: (text: string) => void; suggestions: Suggestion[] }) {
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
        {suggestions.map((s) => (
          <li key={s.label}>
            <button
              type="button"
              className="chip-button"
              onClick={() => {
                if (s.open) return s.open();
                setDraft(s.draft ?? "");
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
            placeholder="Dê uma ordem ao Visão"
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
