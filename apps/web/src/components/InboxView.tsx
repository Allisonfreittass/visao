import { type FormEvent, type KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";

import { type Api, type Panel, moneyWords, utcDate } from "../api";
import { homeGreeting } from "../brand/copy";
import { Corvo } from "../brand/Corvo";
import type { AnelEstado, AssistantState } from "../anel/state";
import type { Pending } from "../hooks/usePending";
import { dayLabel } from "../labels";
import { Icon } from "./Icon";
import { brl, panelKnown } from "./PanelsBoard";
import { MicButton } from "./SkyNav";
import { argumentLines, cardText } from "../apps";

export interface CallControls {
  state: AssistantState;
  /** What the ring shows (the state above, plus Mac work, a yes waiting, the pause). */
  anel: AnelEstado;
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

/** The status line under the greeting, from real data: "Acompanhando 1 painel · 1 pedido esperando
 * você · Mac conectado". Empty when there is nothing to say (DESIGN.md §7: no "systems ready"). */
export function statusLine({ online, macOnline, pendingCount, panels }: StatusSignals & { panels: Pick<Panel, "items" | "status">[] | null }): string {
  if (!online) return "Sem conexão com o servidor.";
  const parts: string[] = [];
  const watched = watchCount(panels);
  if (watched) parts.push(`Acompanhando ${watched}`);
  if (pendingCount) parts.push(`${pendingCount} ${pendingCount === 1 ? "pedido esperando" : "pedidos esperando"} você`);
  if (macOnline === true) parts.push("Mac conectado");
  if (macOnline === false) parts.push("Sem conexão com o Mac");
  const items = (panels ?? []).flatMap((p) => p.items).filter((i) => i.cost === null);
  const flights = items.filter((i) => i.kind === "flight").length;
  const hotels = items.length - flights;
  if (flights) parts.push(`${flights} ${flights === 1 ? "voo aguardando" : "voos aguardando"} preço`);
  if (hotels) parts.push(`${hotels} ${hotels === 1 ? "hospedagem aguardando" : "hospedagens aguardando"} preço`);
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
  if (flight) list.push({ label: "Acompanhar preço dos voos", draft: `Acompanha o preço dos voos de «${flight.title}» e me avisa se cair` });
  else list.push({ label: "Acompanhar um preço", draft: "Quero acompanhar " });
  if (project) list.push({ label: `Abrir projeto ${project.name}`, open: () => openProject(project.id) });
  else list.push({ label: "Pedir ao Mac", draft: "/mac " });
  return list;
}

/** "PENSADO HOJE, 08:45" / "PENSADO ONTEM, 22:10" / "PENSADO EM 12/11, 09:00". */
export function thoughtWhen(date: Date, now = new Date()): string {
  const label = dayLabel(date, now);
  return /^(Hoje|Ontem)/.test(label) ? `Pensado ${label.toLowerCase()}` : `Pensado em ${label}`;
}

/** "há 25 min", "há 3 h", "há 2 dias". */
export function ago(date: Date, now = new Date()): string {
  const min = Math.max(0, Math.round((now.getTime() - date.getTime()) / 60_000));
  if (min < 1) return "agora";
  if (min < 60) return `há ${min} min`;
  const h = Math.round(min / 60);
  if (h < 24) return `há ${h} h`;
  const d = Math.round(h / 24);
  return `há ${d} ${d === 1 ? "dia" : "dias"}`;
}

/** The first thing waiting for a yes, for the card at the top of Início. */
interface Ask {
  key: string;
  where: string;
  question: string;
  meta: string;
  after: string;
  approve: () => Promise<boolean>;
  reject: () => Promise<boolean>;
}

function firstAsk(pending: Pending): Ask | null {
  const t = pending.armProposals[0];
  if (t) {
    return {
      key: `arm-${t.id}`, where: "no Mac", question: t.prompt, meta: `projeto ${t.project} · pedido ${ago(utcDate(t.created_at))}`,
      after: "rodando no Mac agora",
      approve: () => pending.decideArm(t, "approve"), reject: () => pending.decideArm(t, "reject"),
    };
  }
  const a = pending.googleActions[0];
  if (a) {
    return {
      key: `g-${a.id}`, where: a.kind === "send_email" ? "no e-mail" : "na agenda",
      question: a.kind === "send_email" ? `Posso mandar este e-mail? ${a.summary}` : `Posso marcar isto? ${a.summary}`,
      meta: `pedido ${ago(utcDate(a.created_at))}`, after: a.kind === "send_email" ? "enviando agora" : "marcando agora",
      approve: () => pending.decideGoogle(a, "approve"), reject: () => pending.decideGoogle(a, "reject"),
    };
  }
  const w = pending.toolActions[0];
  if (w) {
    return {
      key: `app-${w.id}`, where: `no ${w.app}`,
      question: w.money ? `Posso pagar ${moneyWords(w.money)}?` : `Posso fazer isto? ${w.summary}`,
      meta: `pedido ${ago(utcDate(w.created_at))}`, after: "fazendo agora",
      approve: () => pending.decideApp(w, "approve"), reject: () => pending.decideApp(w, "reject"),
    };
  }
  const g = pending.goals[0];
  if (g) {
    return {
      key: `goal-${g.id}`, where: "uma meta", question: g.title, meta: g.rationale, after: "anotado como meta",
      approve: () => pending.decideGoal(g, "approve"), reject: () => pending.decideGoal(g, "reject"),
    };
  }
  const o = pending.panelOffers[0];
  if (o) {
    return {
      key: `offer-${o.id}`, where: "um painel", question: `Deixo isto no Início? ${o.summary}`, meta: "painel novo", after: "no Início a partir de agora",
      approve: () => pending.decidePanelOffer(o, "approve"), reject: () => pending.decidePanelOffer(o, "reject"),
    };
  }
  return null;
}

/** The approval card: amber border (it is his), the question in his voice, Aprovar or Recusar.
 * Approved, it keeps an "APROVADO" stamp for a few seconds before the list moves on. */
function AskCard({ ask }: { ask: Ask }) {
  const [stamp, setStamp] = useState<{ key: string; after: string } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!stamp) return;
    const id = setTimeout(() => setStamp(null), 6000);
    return () => clearTimeout(id);
  }, [stamp]);
  async function approve() {
    setBusy(true);
    const ok = await ask.approve();
    setBusy(false);
    if (ok) setStamp({ key: ask.key, after: ask.after });
  }
  return (
    <article className="ask-card" aria-labelledby={`ask-${ask.key}`}>
      <div className="ask-card-kicker"><Corvo size={20} /><span>Pede aprovação · {ask.where}</span></div>
      <p id={`ask-${ask.key}`} className="ask-card-question">{ask.question}</p>
      <span className="ask-card-meta">{ask.meta}</span>
      {stamp ? (
        <div className="ask-card-done" role="status">
          <span className="stamp">✓ Aprovado</span>
          <span className="ask-card-meta">{stamp.after}</span>
        </div>
      ) : (
        <div className="ask-card-buttons">
          <button type="button" className="btn-primary" disabled={busy} onClick={() => void approve()}>Aprovar</button>
          <button type="button" className="btn-secondary" disabled={busy} onClick={() => void ask.reject()}>Recusar</button>
        </div>
      )}
    </article>
  );
}

/** The first live panel, summed up; a click opens Painel. */
function PanelSummary({ panel, onOpen }: { panel: Panel; onOpen: () => void }) {
  const known = panelKnown(panel);
  const checked = panel.checked_at ? utcDate(panel.checked_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : null;
  const foot = [panel.change, panel.goal ? `meta ${brl(panel.goal)}` : null].filter(Boolean).join(" · ");
  return (
    <button type="button" className="panel-summary" onClick={onOpen} aria-label={`Abrir o painel ${panel.title}`}>
      <span className="panel-summary-kicker">Painel · {checked ? `${panel.checked_today ? "conferido hoje" : "conferido"} ${checked}` : "ainda não conferido"}</span>
      <span className="panel-summary-head"><span className="panel-summary-title">{panel.title}</span><span className="panel-summary-total">{known.amount}</span></span>
      {panel.items.slice(0, 4).map((item, i) => (
        <span key={`${item.provider}-${i}`} className="panel-summary-row">
          <span>{item.provider}{item.where && <span className="muted"> · {item.where}</span>}</span>
          <span className="panel-summary-price">{brl(item.cost) ?? "a confirmar"}</span>
        </span>
      ))}
      {foot && <span className="panel-summary-foot">{foot}</span>}
    </button>
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
  onOpenPanel: () => void;
  /** He is working right now (a reply or a task on the Mac): the amber dot in the box. */
  working: boolean;
}

/** Início: the ring and the greeting, a line about the day, the live panels, everything that
 * waits for a yes, a no or a read, and the message box at the bottom. */
export function InboxView({ api, call, onSend, pending, current, onReplied, online, macOnline, project, onOpenProject, onOpenPanel, working }: InboxViewProps) {
  const empty = pending.count === 0;
  const [panels, setPanels] = useState<Panel[] | null>(null);
  const [hello, setHello] = useState(() => homeGreeting());
  const thought = useLatestThought(api);
  const ask = firstAsk(pending);
  const loadPanels = useCallback(() => { api.panels().then(setPanels, () => setPanels([])); }, [api]);
  useEffect(() => {
    loadPanels();
    const id = setInterval(loadPanels, 60_000);
    return () => clearInterval(id);
  }, [loadPanels]);
  const livePanel = (panels ?? []).find((p) => p.status === "active" && p.items.length > 0) ?? null;
  useEffect(() => {
    // The greeting follows the hour while the page stays open.
    const id = setInterval(() => setHello(homeGreeting()), 60_000);
    return () => clearInterval(id);
  }, []);

  const summary = statusLine({ online, macOnline, pendingCount: pending.count, panels });
  return (
    <section className="home" aria-labelledby="home-title">
      <div className="home-scroll">
        <header className="home-hero">
          <Corvo size={92} className="home-corvo" />
          <div>
            <h1 id="home-title" className="home-greeting">{hello}</h1>
            {summary && <p className="home-summary">{summary}</p>}
          </div>
          {call.speaking && (
            <button type="button" className="btn-secondary" onClick={call.onStopSpeaking}>Parar de falar</button>
          )}
        </header>

        {thought && (
          // What he is thinking, in his own voice (DESIGN.md §3): Newsreader italic, a 2 px amber rule.
          <figure className="home-thought" aria-label="O que ele está pensando">
            <blockquote className="fala-dele"><p>{thought.content}</p></blockquote>
            <figcaption><time>{thoughtWhen(utcDate(thought.created_at))}</time></figcaption>
          </figure>
        )}

        {(ask || livePanel) && (
          <div className="home-cards">
            {ask && <AskCard key={ask.key} ask={ask} />}
            {livePanel && <PanelSummary panel={livePanel} onOpen={onOpenPanel} />}
          </div>
        )}

        {pending.panelOffers.filter((o) => ask?.key !== `offer-${o.id}`).length > 0 && (
          <section className="list-group">
            <h2 className="rotulo">Painéis para aprovar</h2>
            {pending.panelOffers.filter((o) => ask?.key !== `offer-${o.id}`).map((o) => (
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
        {pending.armProposals.filter((t) => ask?.key !== `arm-${t.id}`).length > 0 && (
          <section className="list-group">
            <h2 className="rotulo">No Mac</h2>
            {pending.armProposals.filter((t) => ask?.key !== `arm-${t.id}`).map((t) => (
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
        {pending.googleActions.filter((a) => ask?.key !== `g-${a.id}`).length > 0 && (
          <section className="list-group">
            <h2 className="rotulo">Email e agenda</h2>
            {pending.googleActions.filter((a) => ask?.key !== `g-${a.id}`).map((a) => (
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
        {pending.toolActions.filter((a) => ask?.key !== `app-${a.id}`).length > 0 && (
          <section className="list-group">
            <h2 className="rotulo">Outros apps</h2>
            {pending.toolActions.filter((a) => ask?.key !== `app-${a.id}`).map((a) => (
              <article className="list-item" key={a.id}>
                <div className="list-item-text">
                  <strong>{a.money ? `Posso pagar ${moneyWords(a.money)} pelo ${a.app}?` : `Posso fazer isto no ${a.app}?`}</strong>
                  <p className="note">{cardText(a)}</p>
                  <p className="note pre google-body">{argumentLines(a.arguments)}</p>
                  <time className="panel-time">{dayLabel(utcDate(a.created_at))}</time>
                </div>
                <div className="row">
                  <button type="button" className="primary" onClick={() => void pending.decideApp(a, "approve")}>{a.money ? "Pagar" : "Aprovar"}</button>
                  <button type="button" className="ghost" onClick={() => void pending.decideApp(a, "reject")}>Recusar</button>
                </div>
              </article>
            ))}
          </section>
        )}
        {pending.goals.filter((g) => ask?.key !== `goal-${g.id}`).length > 0 && (
          <section className="list-group">
            <h2 className="rotulo">Metas que eu quero seguir</h2>
            {pending.goals.filter((g) => ask?.key !== `goal-${g.id}`).map((g) => (
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
        {empty && !livePanel && <p className="note page-empty">Nada esperando você. O que ele quiser fazer por conta própria aparece aqui antes.</p>}
      </div>

      <HomeComposer call={call} onSend={onSend} working={working} suggestions={homeSuggestions(panels, project, onOpenProject)} />
    </section>
  );
}

/** Início's message box: suggestions above, the microphone on the left, send on the right. */
function HomeComposer({ call, onSend, suggestions, working }: { call: CallControls; onSend: (text: string) => void; suggestions: Suggestion[]; working: boolean }) {
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
          <MicButton canCall={call.canCall} hint={call.hint} onCall={call.onCall} live={call.inCall} onExplain={call.onOpenSettings} />
          <textarea
            ref={box}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Fala comigo…"
            rows={1}
            maxLength={8000}
            aria-label="Mensagem"
          />
          {working && <span className="atividade" role="img" aria-label="Ele está trabalhando" title="Ele está trabalhando" />}
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
