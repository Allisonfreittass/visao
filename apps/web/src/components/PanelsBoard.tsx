import { useCallback, useEffect, useState } from "react";

import { type Api, type Panel, type PanelItem, type PanelSuggestion, utcDate } from "../api";
import { assumedLine } from "./QuoteTable";
import { Icon } from "./Icon";

const REFRESH_MS = 60_000;

/** "R$ 5.945" from the server's decimal string; the server did the math. */
export function brl(value: string | null): string | null {
  if (value === null) return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: n % 1 === 0 ? 0 : 2 });
}

/** How often it is checked: every few hours near the goal (ADR-0016), else nothing to say. */
export function watchLabel(panel: Pick<Panel, "watch_every_hours" | "status">): string | null {
  if (panel.status === "paused" || !panel.watch_every_hours) return null;
  return `perto da meta: confiro a cada ${panel.watch_every_hours} h`;
}

/** When it was checked, never "agora" for a number from another day. */
export function checkedLabel(panel: Pick<Panel, "checked_at" | "checked_today">): string {
  if (!panel.checked_at) return "ainda não conferido";
  const at = utcDate(panel.checked_at);
  const time = at.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  if (panel.checked_today) return `conferido hoje, ${time}`;
  return `conferido em ${at.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}, ${time} · não conferido hoje`;
}

/** What is already known about a panel: the total, or the sum of the prices it has with what is
 * still missing ("R$ 164 + voo"); the amber tag for what is pending; whether data is missing. */
export function panelKnown(panel: Pick<Panel, "total" | "items">): { amount: string; tag: string | null; missingData: boolean } {
  if (panel.items.length === 0) return { amount: "—", tag: "Faltam dados", missingData: true };
  const total = brl(panel.total);
  const open = panel.items.filter((i) => i.cost === null);
  const known = panel.items.reduce((sum, i) => (i.cost === null ? sum : sum + Number(i.cost)), 0);
  const missing = [...new Set(open.map((i) => (i.kind === "flight" ? "voo" : "hospedagem")))];
  if (total && open.length === 0) return { amount: total, tag: null, missingData: false };
  const tag = missing.length === 1 ? `${missing[0] === "voo" ? "Voo" : "Hospedagem"} a confirmar` : "Preços a confirmar";
  const amount = known > 0 ? `${brl(String(known))} + ${missing.join(" + ")}` : "a confirmar";
  return { amount, tag, missingData: false };
}

function monogram(provider: string): string {
  return provider.trim().charAt(0).toUpperCase() || "?";
}

function ItemRow({ item }: { item: PanelItem }) {
  const extra = [item.dates, item.kind === "flight" && item.connections !== null ? (item.connections === 0 ? "direto" : `${item.connections} parada${item.connections > 1 ? "s" : ""}`) : null].filter(Boolean).join(" · ");
  return (
    <li className="panel-item">
      {/* No third-party logos without a clear license: the provider's initial. */}
      <span className="panel-item-mark" aria-hidden="true">{monogram(item.provider)}</span>
      <span className="panel-item-text">
        <strong>{item.provider}</strong>
        <span>{[item.kind === "flight" ? "Voo" : "Hospedagem", item.where].filter(Boolean).join(" · ")}</span>
        {extra && <span>{extra}</span>}
      </span>
      <span className="panel-item-price">{brl(item.cost) ?? "a confirmar"}</span>
    </li>
  );
}

function PanelCard({ api, panel, onChanged, onDraft }: { api: Api; panel: Panel; onChanged: () => void; onDraft: (text: string) => void }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<Panel | null>(null);
  const known = panelKnown(panel);
  const flight = panel.items.some((i) => i.kind === "flight") || /voo|passagem/i.test(panel.title);
  const hotel = !flight && panel.items.some((i) => i.kind === "hotel");
  const below = panel.goal_gap !== null && Number(panel.goal_gap) < 0;
  const change = panel.change !== null ? Number(panel.change) : 0;

  useEffect(() => {
    if (open) api.panel(panel.id).then(setDetail, () => undefined);
  }, [api, open, panel.id, panel.checked_at]);

  return (
    <article className={`live-panel${panel.status === "paused" ? " live-panel--paused" : ""}`}>
      <button type="button" className="live-panel-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="live-panel-top">
          <span className="live-panel-icon" aria-hidden="true"><Icon name={flight ? "plane" : hotel ? "bed" : "coin"} size={18} /></span>
          <h3>{panel.title}</h3>
          {panel.status === "paused" ? <span className="tag">Pausado</span> : known.tag && <span className="tag tag--amber">{known.tag}</span>}
        </span>
        <span className="live-panel-total" key={panel.total ?? "x"}>{known.amount}</span>
        {panel.spec.travelers && panel.spec.travelers > 1 && <span className="live-panel-sub">total para {panel.spec.travelers}</span>}
        {assumedLine(panel.spec.assumed) && <span className="live-panel-sub">{assumedLine(panel.spec.assumed)}</span>}
        {panel.goal_words && <span className={`live-panel-goal${below ? " live-panel-goal--below" : ""}`}>{panel.goal_words}</span>}
        {change !== 0 && (
          <span className={`live-panel-change${change < 0 ? " live-panel-change--down" : ""}`}>
            {change < 0 ? "↓" : "↑"} {brl(String(Math.abs(change)))} desde a última conferência
          </span>
        )}
      </button>
      <ul className="panel-items">
        {panel.items.map((item, i) => <ItemRow key={`${item.kind}-${i}`} item={item} />)}
      </ul>
      {known.missingData && (
        <div className="live-panel-missing">
          <p className="note">Faltam as datas para eu procurar os preços.</p>
          <button type="button" onClick={() => onDraft(`As datas para «${panel.title}»: `)}>Informar datas</button>
        </div>
      )}
      <p className="live-panel-when">
        {checkedLabel(panel)}
        {watchLabel(panel) && <span className="live-panel-watch"> · {watchLabel(panel)}</span>}
        {panel.note && <span> · {panel.note}</span>}
      </p>
      {open && (
        <div className="live-panel-detail">
          {detail?.history && detail.history.length > 1 && (
            <ol className="live-panel-history" aria-label="Conferências anteriores">
              {detail.history.map((h) => (
                <li key={h.checked_at}>
                  <time>{utcDate(h.checked_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}</time> {brl(h.total) ?? "a confirmar"}
                </li>
              ))}
            </ol>
          )}
          <ul className="live-panel-links">
            {panel.items.filter((i) => i.url).map((i) => (
              <li key={i.url}><a href={i.url} target="_blank" rel="noopener noreferrer">{i.site || "site"}: {i.provider}</a></li>
            ))}
          </ul>
          <div className="row">
            <button type="button" className="ghost" onClick={() => void api.setPanelStatus(panel.id, panel.status === "paused" ? "active" : "paused").then(onChanged)}>
              {panel.status === "paused" ? "Retomar" : "Pausar"}
            </button>
            <button
              type="button"
              className="ghost"
              onClick={() => {
                if (!window.confirm(`Apagar o painel “${panel.title}”?`)) return;
                void api.deletePanel(panel.id).then(onChanged);
              }}
            >
              Apagar
            </button>
          </div>
        </div>
      )}
    </article>
  );
}

interface PanelsBoardProps {
  api: Api;
  /** Nothing waits for the owner: the suggestions may show. */
  nothingPending: boolean;
  /** Opens the chat with this text in the box. */
  onDraft: (text: string) => void;
  /** Only this project's panels, without suggestions (inside a project). */
  projectId?: string;
  /** Hears about the panels each time they load (Início's one-line summary). */
  onPanels?: (panels: Panel[]) => void;
}

/** The live panels on Início: native cards the server keeps up to date (docs/PAINEIS.md). */
export function PanelsBoard({ api, nothingPending, onDraft, projectId, onPanels }: PanelsBoardProps) {
  const [panels, setPanels] = useState<Panel[] | null>(null);
  const [suggested, setSuggested] = useState<PanelSuggestion[]>([]);
  const load = useCallback(() => {
    api.panels().then(
      (all) => setPanels(projectId ? all.filter((p) => p.project_id === projectId) : all),
      () => setPanels([]),
    );
  }, [api, projectId]);

  useEffect(() => {
    if (panels) onPanels?.(panels);
  }, [panels, onPanels]);

  useEffect(() => {
    load();
    const id = window.setInterval(load, REFRESH_MS);
    return () => window.clearInterval(id);
  }, [load]);

  useEffect(() => {
    if (panels && panels.length === 0 && nothingPending && !projectId) api.panelSuggestions().then(setSuggested, () => setSuggested([]));
  }, [api, panels, nothingPending]);

  if (panels === null || (projectId && panels.length === 0)) return null;
  return (
    <section className="list-group panels-board" aria-label="Painéis">
      <h2 className="rotulo">Painéis</h2>
      {panels.map((panel) => <PanelCard key={panel.id} api={api} panel={panel} onChanged={load} onDraft={onDraft} />)}
      {panels.length === 0 && nothingPending && suggested.length > 0 && (
        <>
        <p className="note panel-suggestions-hint">Sugestões: tocar escreve o pedido na conversa, e nada roda antes de você mandar.</p>
        <ul className="panel-suggestions">
          {suggested.map((s) => (
            <li key={s.text}><button type="button" className="ghost" onClick={() => onDraft(s.draft)}>{s.text}</button></li>
          ))}
        </ul>
        </>
      )}
      <button type="button" className="panel-new" onClick={() => onDraft("Quero acompanhar ")}>+ Criar um novo painel</button>
    </section>
  );
}
