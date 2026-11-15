import { useCallback, useEffect, useState } from "react";

import { type Api, type Panel, type PanelItem, type PanelSuggestion, utcDate } from "../api";

const REFRESH_MS = 60_000;

/** "R$ 5.945" from the server's decimal string; the server did the math. */
export function brl(value: string | null): string | null {
  if (value === null) return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: n % 1 === 0 ? 0 : 2 });
}

/** When it was checked, never "agora" for a number from another day. */
export function checkedLabel(panel: Pick<Panel, "checked_at" | "checked_today">): string {
  if (!panel.checked_at) return "ainda não conferido";
  const at = utcDate(panel.checked_at);
  const time = at.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  if (panel.checked_today) return `conferido hoje, ${time}`;
  return `conferido em ${at.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}, ${time} · não conferido hoje`;
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

function PanelCard({ api, panel, onChanged }: { api: Api; panel: Panel; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<Panel | null>(null);
  const total = brl(panel.total);
  const below = panel.goal_gap !== null && Number(panel.goal_gap) < 0;
  const change = panel.change !== null ? Number(panel.change) : 0;

  useEffect(() => {
    if (open) api.panel(panel.id).then(setDetail, () => undefined);
  }, [api, open, panel.id, panel.checked_at]);

  return (
    <article className={`live-panel${panel.status === "paused" ? " live-panel--paused" : ""}`}>
      <button type="button" className="live-panel-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="rotulo">{panel.status === "paused" ? "Pausado" : "Painel"}</span>
        <h3>{panel.title}</h3>
        <span className="live-panel-total" key={panel.total ?? "x"}>{total ?? "a confirmar"}</span>
        {panel.spec.travelers && panel.spec.travelers > 1 && <span className="live-panel-sub">total para {panel.spec.travelers}</span>}
        {panel.goal_words && <span className={`live-panel-goal${below ? " live-panel-goal--below" : ""}`}>{panel.goal_words}</span>}
        {change !== 0 && (
          <span className={`live-panel-change${change < 0 ? " live-panel-change--down" : ""}`}>
            {change < 0 ? "↓" : "↑"} {brl(String(Math.abs(change)))} desde a última conferência
          </span>
        )}
      </button>
      <ul className="panel-items">
        {panel.items.map((item, i) => <ItemRow key={`${item.kind}-${i}`} item={item} />)}
        {panel.items.length === 0 && <li className="note">Os preços ainda estão a confirmar.</li>}
      </ul>
      <p className="live-panel-when">
        {checkedLabel(panel)}
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
}

/** The live panels on Início: native cards the server keeps up to date (docs/PAINEIS.md). */
export function PanelsBoard({ api, nothingPending, onDraft }: PanelsBoardProps) {
  const [panels, setPanels] = useState<Panel[] | null>(null);
  const [suggested, setSuggested] = useState<PanelSuggestion[]>([]);
  const load = useCallback(() => {
    api.panels().then(setPanels, () => setPanels([]));
  }, [api]);

  useEffect(() => {
    load();
    const id = window.setInterval(load, REFRESH_MS);
    return () => window.clearInterval(id);
  }, [load]);

  useEffect(() => {
    if (panels && panels.length === 0 && nothingPending) api.panelSuggestions().then(setSuggested, () => setSuggested([]));
  }, [api, panels, nothingPending]);

  if (panels === null) return null;
  return (
    <section className="list-group panels-board" aria-label="Painéis">
      <h2 className="rotulo">Painéis</h2>
      {panels.map((panel) => <PanelCard key={panel.id} api={api} panel={panel} onChanged={load} />)}
      {panels.length === 0 && nothingPending && suggested.length > 0 && (
        <ul className="panel-suggestions">
          {suggested.map((s) => (
            <li key={s.text}><button type="button" className="ghost" onClick={() => onDraft(s.draft)}>{s.text}</button></li>
          ))}
        </ul>
      )}
      <button type="button" className="panel-new ghost" onClick={() => onDraft("Quero acompanhar ")}>+ Criar um novo painel</button>
    </section>
  );
}
