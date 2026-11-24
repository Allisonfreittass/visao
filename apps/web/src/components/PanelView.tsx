import { useCallback, useEffect, useState } from "react";

import { type Api, type Panel, utcDate } from "../api";
import { brl, checkedLabel, panelKnown } from "./PanelsBoard";

const W = 680;
const H = 150;
const PAD = 10;

/** The chart's polyline and the goal's height, from the checks the server kept (oldest first). */
export function chartGeometry(history: { total: string | null }[], goal: string | null): { points: string; goalY: number | null; first: number; last: number } | null {
  const values = history.map((h) => Number(h.total)).filter((v) => Number.isFinite(v) && v > 0);
  if (values.length < 2) return null;
  const goalValue = goal !== null && Number.isFinite(Number(goal)) ? Number(goal) : null;
  const all = goalValue !== null ? [...values, goalValue] : values;
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;
  const y = (v: number) => PAD + (H - 2 * PAD) * (1 - (v - min) / span);
  const step = W / (values.length - 1);
  const points = values.map((v, i) => `${Math.round(i * step)},${Math.round(y(v))}`).join(" ");
  return { points, goalY: goalValue !== null ? Math.round(y(goalValue)) : null, first: values[0], last: values[values.length - 1] };
}

function PanelChart({ panel }: { panel: Panel }) {
  const history = [...(panel.history ?? [])].sort((a, b) => a.checked_at.localeCompare(b.checked_at));
  const geo = chartGeometry(history, panel.goal);
  if (!geo) return <p className="note">O gráfico aparece depois de duas conferências.</p>;
  const label = `Preço de ${brl(String(geo.first))} para ${brl(String(geo.last))} em ${history.length} conferências${panel.goal ? `; meta ${brl(panel.goal)}` : ""}`;
  return (
    <svg className="panel-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} preserveAspectRatio="none">
      {geo.goalY !== null && <line x1="0" y1={geo.goalY} x2={W} y2={geo.goalY} className="panel-chart-goal" />}
      <polyline points={geo.points} className="panel-chart-line" />
    </svg>
  );
}

interface PanelViewProps {
  api: Api;
  onBack: () => void;
  onDraft: (text: string) => void;
  onError: (e: unknown) => void;
}

/** Painel: the total, the chart with the goal line, what he says about it and each option. */
export function PanelView({ api, onBack, onDraft, onError }: PanelViewProps) {
  const [list, setList] = useState<Panel[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel | null>(null);

  useEffect(() => {
    api.panels().then((all) => {
      const live = all.filter((p) => p.status === "active" || p.status === "paused");
      setList(live);
      setSelected((s) => s ?? live.find((p) => p.status === "active")?.id ?? live[0]?.id ?? null);
    }, onError);
  }, [api, onError]);

  const load = useCallback(() => {
    if (!selected) return;
    api.panel(selected).then(setPanel, onError);
  }, [api, selected, onError]);
  useEffect(load, [load]);

  async function togglePause() {
    if (!panel) return;
    try {
      const next = await api.setPanelStatus(panel.id, panel.status === "active" ? "paused" : "active");
      setPanel({ ...panel, status: next.status });
      setList((l) => l?.map((p) => (p.id === next.id ? { ...p, status: next.status } : p)) ?? l);
    } catch (e) {
      onError(e);
    }
  }

  if (list && list.length === 0) {
    return (
      <section className="page panel-page" aria-labelledby="panel-title">
        <header className="page-head"><h1 id="panel-title">Painel</h1></header>
        <p className="lede">Nenhum painel ainda. Peça no chat para acompanhar um preço e ele aparece aqui, com o gráfico.</p>
        <div className="row-buttons">
          <button type="button" className="btn-primary" onClick={() => onDraft("Quero acompanhar ")}>Acompanhar um preço</button>
          <button type="button" className="btn-secondary" onClick={onBack}>Voltar ao Início</button>
        </div>
      </section>
    );
  }
  if (!panel) return <section className="page"><p className="note">Carregando…</p></section>;

  const known = panelKnown(panel);
  const travelers = panel.spec.travelers;
  const sub = [
    travelers ? `total para ${travelers}` : null,
    panel.spec.depart && panel.spec.back ? `${panel.spec.depart} a ${panel.spec.back}` : null,
    panel.goal ? `meta ${brl(panel.goal)}` : null,
  ].filter(Boolean).join(" · ");
  const site = panel.items.find((i) => i.site)?.site;
  return (
    <section className="page panel-page" aria-labelledby="panel-title">
      <header className="page-head"><h1 id="panel-title">Painel · {panel.title}</h1></header>
      {list && list.length > 1 && (
        <div className="panel-tabs" role="tablist" aria-label="Painéis">
          {list.map((p) => (
            <button key={p.id} type="button" role="tab" aria-selected={p.id === selected} onClick={() => setSelected(p.id)}>{p.title}</button>
          ))}
        </div>
      )}
      <div className="panel-total"><span className="panel-total-amount">{known.amount}</span>{sub && <span className="panel-total-sub">{sub}</span>}</div>
      <PanelChart panel={panel} />
      {(panel.goal_words || panel.note) && (
        <figure className="home-thought">
          <blockquote className="fala-dele"><p>{panel.goal_words || panel.note}</p></blockquote>
          <figcaption>{checkedLabel(panel)}{site ? ` · ${site}` : ""}</figcaption>
        </figure>
      )}
      {panel.items.length > 0 && (
        <ul className="panel-rows">
          {panel.items.map((item, i) => (
            <li key={`${item.provider}-${i}`}>
              <span>{item.provider}{item.where && <span className="muted"> · {item.where}</span>}</span>
              <span className="panel-summary-price">{brl(item.cost) ?? "a confirmar"}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="note">
        {panel.status === "paused" ? "Pausado: não confiro até você retomar." : panel.next_check_at ? `Próxima conferência: ${utcDate(panel.next_check_at).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}.` : ""}
      </p>
      <div className="row-buttons">
        <button type="button" className="btn-secondary" onClick={onBack}>Voltar ao Início</button>
        <button type="button" className="btn-secondary" onClick={() => void togglePause()}>{panel.status === "paused" ? "Retomar" : "Pausar"}</button>
      </div>
    </section>
  );
}
