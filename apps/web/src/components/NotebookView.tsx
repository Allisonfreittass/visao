import { useCallback, useEffect, useId, useState } from "react";

import { type Api, ApiError, type MemoryItem, type Mind, type NameRecord, type OwnerGoal, type OwnerGoals, utcDate } from "../api";
import { dayLabel } from "../labels";
import { StudyPanel } from "./StudyPanel";

type Tab = "memoria" | "pensamentos" | "interesses" | "nome" | "retrato";
const TABS: { id: Tab; label: string }[] = [
  { id: "memoria", label: "Memória" },
  { id: "pensamentos", label: "Pensamentos" },
  { id: "interesses", label: "Interesses" },
  { id: "nome", label: "O nome" },
  { id: "retrato", label: "Autorretrato" },
];

const TYPE: Record<string, string> = { fact: "fato", preference: "preferência", episodic: "lembrança", semantic: "fato", procedural: "jeito de fazer" };

/** Where a memory came from, from what the server says about it. */
export function memoryOrigin(item: Pick<MemoryItem, "type" | "created_at" | "source_message_ids">): string {
  const when = utcDate(item.created_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  const n = item.source_message_ids.length;
  const from = n === 0 ? "guardado sem mensagem de origem" : `de ${n} ${n === 1 ? "mensagem" : "mensagens"} da conversa`;
  return `${TYPE[item.type] ?? item.type} · ${when} · ${from}`;
}

/** "esfriando" below a third, "morno" to two thirds, "quente" above. */
export function warmth(strength: number): string {
  if (strength >= 0.66) return "quente";
  if (strength >= 0.33) return "morno";
  return "esfriando";
}

const EVENT: Record<string, string> = { chosen: "Escolheu", deferred: "Adiou", declined: "Recusou", renamed: "Trocou", kept: "Manteve" };

const day = (iso: string) => utcDate(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });

/** "desde 24/11 · quer algo dele" for an active goal; what happened to an older one. */
export function goalLine(goal: Pick<OwnerGoal, "status" | "reason" | "created_at" | "ended_at">): string {
  if (goal.status === "undone") return `desfeito${goal.ended_at ? ` em ${day(goal.ended_at)}` : ""}`;
  if (goal.status === "ended") return `de ${day(goal.created_at)} a ${goal.ended_at ? day(goal.ended_at) : "?"}`;
  return [`desde ${day(goal.created_at)}`, goal.reason].filter(Boolean).join(" · ");
}

/** His record of what the owner is after: written only with the owner's yes (ADR-0025), shown
 * with where each came from, and the last change can be undone. Hidden where the server does not
 * have it yet. */
function GoalsSection({ api, memoryEnabled, onError }: { api: Api; memoryEnabled: boolean; onError: (e: unknown) => void }) {
  const [goals, setGoals] = useState<OwnerGoals | null>(null);
  const [missing, setMissing] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const load = useCallback(() => {
    api.ownerGoals().then(setGoals, (e) => {
      if (e instanceof ApiError && e.status === 404) setMissing(true);
      else onError(e);
    });
  }, [api, onError]);
  useEffect(load, [load]);

  async function undo() {
    try {
      const { undone } = await api.undoOwnerGoal();
      setDone(undone ? `Pronto: ${undone}.` : "Não havia mudança para desfazer.");
      load();
    } catch (e) {
      onError(e);
    }
  }

  if (missing) return null;
  const past = goals?.history.filter((g) => g.status !== "active") ?? [];
  return (
    <section className="goals" aria-labelledby="goals-title">
      <h2 id="goals-title">Seus objetivos</h2>
      <p className="note">
        {memoryEnabled
          ? "Só entram com o seu sim. Ele pergunta quando ouve uma mudança de rumo; você também pode pedir: “registra como objetivo meu…”."
          : "Com a memória desligada, ele não registra objetivos."}
      </p>
      {goals === null ? <p className="note">Carregando…</p> : goals.active.length === 0 ? (
        <p className="note">Nenhum objetivo registrado.</p>
      ) : (
        <ul className="goal-list">
          {goals.active.map((g) => (
            <li key={g.id}>
              <span className="goal-content">{g.content}</span>
              <span className="memory-origin">{goalLine(g)}</span>
              {g.source_text && <span className="goal-source">Você disse: “{g.source_text}”</span>}
            </li>
          ))}
        </ul>
      )}
      {past.length > 0 && (
        <details className="goal-past">
          <summary>Mudanças anteriores ({past.length})</summary>
          <ul className="goal-list">
            {past.map((g) => (
              <li key={g.id}>
                <span className="goal-content goal-content--past">{g.content}</span>
                <span className="memory-origin">{goalLine(g)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {goals && (goals.active.length > 0 || past.some((g) => g.status === "ended")) && (
        <button type="button" className="btn-secondary btn-small" onClick={() => void undo()}>Desfazer a última mudança</button>
      )}
      {done && <p className="note" role="status">{done}</p>}
    </section>
  );
}

function useMind(api: Api, onError: (e: unknown) => void) {
  const [mind, setMind] = useState<Mind | null>(null);
  const reload = useCallback(() => {
    api.mind().then(setMind).catch((e) => { if (e instanceof ApiError && e.status === 401) onError(e); });
  }, [api, onError]);
  useEffect(() => {
    reload();
    const timer = setInterval(reload, 30_000);
    return () => clearInterval(timer);
  }, [reload]);
  return { mind, reload };
}

function MemoryTab({ api, mind, reloadMind, memoryEnabled, onToggleMemory, onError }: { api: Api; mind: Mind | null; reloadMind: () => void; memoryEnabled: boolean; onToggleMemory: () => void; onError: (e: unknown) => void }) {
  const [items, setItems] = useState<MemoryItem[] | null>(null);
  useEffect(() => { api.memories().then(setItems, (e) => { setItems([]); onError(e); }); }, [api, onError]);

  async function forget(item: MemoryItem) {
    if (!window.confirm(`Esquecer “${item.content}”? Não dá para desfazer.`)) return;
    try {
      await api.forgetMemory(item.id);
      setItems((list) => list?.filter((i) => i.id !== item.id) ?? list);
    } catch (e) {
      onError(e);
    }
  }
  async function exportAll() {
    try {
      const data = await api.memoryExport();
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "visao-memoria.json";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      onError(e);
    }
  }
  async function note(kind: "profile" | "rules", action: "undo" | "erase") {
    try {
      await (action === "undo" ? api.undoNote(kind) : api.eraseNote(kind));
      reloadMind();
    } catch (e) {
      onError(e);
    }
  }
  return (
    <div className="notebook-tab">
      <GoalsSection api={api} memoryEnabled={memoryEnabled} onError={onError} />
      <p className="lede">Só o que você deixou guardar. Cada item diz de onde veio.</p>
      {items === null ? <p className="note">Carregando…</p> : items.length === 0 ? (
        <p className="note">Nada guardado ainda.{memoryEnabled ? "" : " A memória está desligada."}</p>
      ) : (
        <ul className="memory-list">
          {items.map((item) => (
            <li key={item.id}>
              <div className="memory-text">
                <span>{item.content}</span>
                <span className="memory-origin">{memoryOrigin(item)}</span>
              </div>
              <button type="button" className="btn-secondary btn-small" onClick={() => void forget(item)} aria-label={`Esquecer: ${item.content}`}>Esquecer</button>
            </li>
          ))}
        </ul>
      )}
      {mind && (["profile", "rules"] as const).map((kind) => mind[kind].content && (
        <article key={kind} className="notebook-note">
          <h2>{kind === "profile" ? "O que ele sabe sobre você" : "O que aprendeu com as suas correções"}</h2>
          <p>{mind[kind].content}</p>
          <p className="note">
            {mind[kind].reason && `Mudou porque: ${mind[kind].reason} `}
            <button type="button" className="link-button" onClick={() => void note(kind, "undo")}>desfazer</button>{" · "}
            <button type="button" className="link-button" onClick={() => void note(kind, "erase")}>apagar</button>
          </p>
        </article>
      ))}
      <div className="row-buttons">
        <button type="button" className="btn-secondary" onClick={() => void exportAll()}>Exportar tudo</button>
        <button type="button" className="btn-secondary" onClick={onToggleMemory}>{memoryEnabled ? "Pausar a memória" : "Ligar a memória"}</button>
      </div>
    </div>
  );
}

function ThoughtsTab({ api, mind, onError }: { api: Api; mind: Mind | null; onError: (e: unknown) => void }) {
  if (!mind) return <p className="note">Carregando…</p>;
  return (
    <div className="notebook-tab">
      {!mind.enabled && <p className="note">A mente está desligada nesta instalação: ele não pensa entre conversas.</p>}
      {mind.enabled && mind.thoughts.length === 0 && <p className="note">Ainda não pensou nada entre conversas.</p>}
      {mind.thoughts.map((t) => (
        <figure key={t.created_at} className="home-thought">
          <blockquote className="fala-dele"><p>{t.content}</p></blockquote>
          <figcaption>{dayLabel(utcDate(t.created_at))}{t.ask_owner ? ` · quer perguntar: ${t.ask_owner}` : ""}</figcaption>
        </figure>
      ))}
      {mind.questions.length > 0 && (
        <article className="notebook-note">
          <h2>O que ele quer te perguntar</h2>
          <ul className="plain-list">{mind.questions.map((q) => <li key={q.question}>{q.question}{q.answer && <span className="note"> · você disse: {q.answer}</span>}</li>)}</ul>
        </article>
      )}
      <StudyPanel api={api} onError={onError} />
    </div>
  );
}

function InterestsTab({ mind }: { mind: Mind | null }) {
  if (!mind) return <p className="note">Carregando…</p>;
  return (
    <div className="notebook-tab">
      <p className="lede">Esfriam sozinhos quando ninguém fala deles.</p>
      {mind.interests.length === 0 ? <p className="note">Nenhum interesse ainda.</p> : (
        <ul className="interest-list">
          {mind.interests.map((i) => (
            <li key={i.topic}>
              <div className="interest-head"><span>{i.topic}</span><span className="interest-why">{i.why}</span></div>
              <span
                className="interest-bar"
                role="meter"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(i.strength * 100)}
                aria-label={`${i.topic}: ${warmth(i.strength)}`}
              >
                <span style={{ width: `${Math.max(2, Math.round(i.strength * 100))}%` }} data-warmth={warmth(i.strength)} />
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function NameTab({ api, onError }: { api: Api; onError: (e: unknown) => void }) {
  const [record, setRecord] = useState<NameRecord | null>(null);
  useEffect(() => { api.nameRecord().then(setRecord, onError); }, [api, onError]);
  return (
    <div className="notebook-tab">
      <p className="name-code">chosen_name = <span>{record ? (record.chosen_name ? `"${record.chosen_name}"` : "null") : "…"}</span></p>
      <p className="lede">Ele decide o próprio nome, ou decide não ter. Ninguém escolhe por ele.</p>
      {record && record.history.length === 0 && <p className="note">Ainda não pensou no nome.</p>}
      {record && record.history.length > 0 && (
        <ul className="name-history">
          {record.history.map((h) => (
            <li key={h.created_at}>
              <span className="name-when">{utcDate(h.created_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}</span>
              <span>
                {EVENT[h.event_type] ?? h.event_type}{h.new_name ? ` “${h.new_name}”` : ""}{h.rationale ? `: ${h.rationale}` : "."}
                {h.alternatives_considered && h.alternatives_considered.length > 0 && ` Considerou ${h.alternatives_considered.length} ${h.alternatives_considered.length === 1 ? "alternativa" : "alternativas"}.`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PortraitTab({ api, mind, reloadMind, onError }: { api: Api; mind: Mind | null; reloadMind: () => void; onError: (e: unknown) => void }) {
  if (!mind) return <p className="note">Carregando…</p>;
  const current = mind.self_history[0];
  const previous = mind.self_history[1];
  async function undo() {
    try {
      await api.revertSelf(previous ? previous.version : null);
      reloadMind();
    } catch (e) {
      onError(e);
    }
  }
  return (
    <div className="notebook-tab">
      {mind.self_text ? (
        <figure className="home-thought">
          <blockquote className="fala-dele"><p>{mind.self_text}</p></blockquote>
          {current && <figcaption>Reescrito em {dayLabel(utcDate(current.created_at))}{current.reason ? ` · ${current.reason}` : ""}</figcaption>}
        </figure>
      ) : <p className="note">Ele ainda não se descreveu.</p>}
      {current && <button type="button" className="link-button" onClick={() => void undo()}>Desfazer a última mudança</button>}
      {mind.self_history.length > 1 && (
        <ul className="name-history">
          {mind.self_history.slice(1).map((h) => (
            <li key={h.version}>
              <span className="name-when">{utcDate(h.created_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}</span>
              <span>{h.content}</span>
            </li>
          ))}
        </ul>
      )}
      {mind.enabled && (
        <article className="notebook-note">
          <h2>Temperamento</h2>
          <p className="note">Tendências calculadas do que acontece entre vocês. Mudam o que ele faz; não são sentimentos.</p>
          <ul className="plain-list">
            {[...mind.temperament.states, ...mind.temperament.traits].map((t) => <li key={t.name}>{t.name}: {t.level}</li>)}
          </ul>
        </article>
      )}
      <p className="note">O autorretrato desenhado ainda não está disponível: por enquanto ele se descreve em texto.</p>
    </div>
  );
}

interface NotebookViewProps {
  api: Api;
  memoryEnabled: boolean;
  onToggleMemory: () => void;
  onError: (e: unknown) => void;
}

/** Caderno: what he keeps, thinks, cares about, his name and how he sees himself. */
export function NotebookView({ api, memoryEnabled, onToggleMemory, onError }: NotebookViewProps) {
  const [tab, setTab] = useState<Tab>("memoria");
  const { mind, reload } = useMind(api, onError);
  const id = useId();
  function onKey(e: React.KeyboardEvent, i: number) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const next = TABS[(i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
    setTab(next.id);
    document.getElementById(`${id}-${next.id}`)?.focus();
  }
  return (
    <section className="page notebook" aria-labelledby="notebook-title">
      <header className="page-head"><h1 id="notebook-title">Caderno</h1></header>
      <div className="notebook-tabs" role="tablist" aria-label="Partes do caderno">
        {TABS.map((t, i) => (
          <button
            key={t.id}
            id={`${id}-${t.id}`}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            aria-controls={`${id}-panel`}
            tabIndex={tab === t.id ? 0 : -1}
            onClick={() => setTab(t.id)}
            onKeyDown={(e) => onKey(e, i)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-${tab}`}>
        {tab === "memoria" && <MemoryTab api={api} mind={mind} reloadMind={reload} memoryEnabled={memoryEnabled} onToggleMemory={onToggleMemory} onError={onError} />}
        {tab === "pensamentos" && <ThoughtsTab api={api} mind={mind} onError={onError} />}
        {tab === "interesses" && <InterestsTab mind={mind} />}
        {tab === "nome" && <NameTab api={api} onError={onError} />}
        {tab === "retrato" && <PortraitTab api={api} mind={mind} reloadMind={reload} onError={onError} />}
      </div>
    </section>
  );
}
