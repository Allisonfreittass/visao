import { useCallback, useEffect, useRef, useState } from "react";

import type { Api, BrainMode, BrainState, CognitionMetrics, QuietHours, RoutingState } from "../api";
import { shortHour } from "../hooks/useRoutines";

const USAGE_MS = 5 * 60_000;

/** Tokens and dollars in the window the server measured (the last 24 h). */
export function usageLine(metrics: CognitionMetrics | null): string | null {
  if (!metrics) return null;
  let tokens = 0;
  let cost = 0;
  for (const u of Object.values(metrics.llm_usage ?? {})) {
    tokens += u.tokens || 0;
    cost += Number(u.cost_usd) || 0;
  }
  const t = tokens >= 1000
    ? `${(tokens / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil tokens`
    : `${tokens} tokens`;
  return `24 h: ${t} · US$ ${cost.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** "Claude · nuvem", "qwen3:4b · no Mac", "automático". */
export function modelLabel(brain: BrainState | null, routing: RoutingState | null): string {
  if (!brain) return "…";
  if (brain.mode === "local") return `${brain.local_model ?? "modelo do Mac"} · no Mac`;
  const cloud = routing?.personal[0] ?? routing?.configured[0] ?? "nuvem";
  if (brain.mode === "auto") return `${cloud} · automático`;
  return `${cloud} · nuvem`;
}

/** "Braço: 1 tarefa rodando", or why it is idle. */
export function armLine(running: number, macOnline: boolean | null): string {
  if (macOnline === null) return "Braço: Mac não pareado";
  if (running > 0) return `Braço: ${running} ${running === 1 ? "tarefa rodando" : "tarefas rodando"}`;
  return macOnline ? "Braço: parado" : "Braço: Mac desligado";
}

const MODES: { value: BrainMode; label: string; note: string }[] = [
  { value: "nuvem", label: "Nuvem", note: "Só a nuvem responde." },
  { value: "local", label: "No Mac", note: "O modelo do Mac responde; volta para a nuvem se ele dormir." },
  { value: "auto", label: "Automático", note: "Nuvem, e o Mac se ela falhar." },
];

interface StatusBarProps {
  api: Api;
  online: boolean;
  running: number;
  macOnline: boolean | null;
  routines: number;
  quiet: QuietHours | null;
  onError: (e: unknown) => void;
}

/** The 28 px bar at the bottom of the window (computer only), in Geist Mono: server, Braço,
 * routines, quiet hours, model use in the last 24 h and the model, which opens the switch. */
export function StatusBar({ api, online, running, macOnline, routines, quiet, onError }: StatusBarProps) {
  const [metrics, setMetrics] = useState<CognitionMetrics | null>(null);
  const [brain, setBrain] = useState<BrainState | null>(null);
  const [routing, setRouting] = useState<RoutingState | null>(null);
  const [open, setOpen] = useState(false);
  const popRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let alive = true;
    const load = () => api.metrics(1).then((m) => alive && setMetrics(m), () => undefined);
    void load();
    const timer = setInterval(load, USAGE_MS);
    api.brain().then((b) => alive && setBrain(b), () => undefined);
    api.routing().then((r) => alive && setRouting(r), () => undefined);
    return () => { alive = false; clearInterval(timer); };
  }, [api]);

  const close = useCallback(() => {
    setOpen(false);
    buttonRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    const onDown = (e: MouseEvent) => {
      if (!popRef.current?.contains(e.target as Node) && !buttonRef.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDown);
    popRef.current?.querySelector<HTMLButtonElement>("[aria-checked='true'], button")?.focus();
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("mousedown", onDown); };
  }, [open, close]);

  async function choose(mode: BrainMode) {
    if (!brain) return;
    const before = brain;
    setBrain({ ...brain, mode });
    close();
    try {
      setBrain(await api.setBrain(mode));
    } catch (e) {
      setBrain(before);
      onError(e);
    }
  }

  const usage = usageLine(metrics);
  return (
    <footer className="status-bar" aria-label="Estado">
      <span className="status-bar-item">
        <span className={`status-bar-dot${online ? " on" : ""}`} aria-hidden="true" />
        {online ? "servidor ok" : "sem conexão com o servidor"}
      </span>
      <span className="status-bar-item">{armLine(running, macOnline)}</span>
      <span className="status-bar-item">{routines} {routines === 1 ? "rotina" : "rotinas"}</span>
      {quiet && <span className="status-bar-item">silêncio {shortHour(quiet.quiet_start)}–{shortHour(quiet.quiet_end)}</span>}
      <span className="status-bar-gap" />
      {usage && <span className="status-bar-item" title="Uso de modelos medido pelo servidor nas últimas 24 horas">{usage}</span>}
      <button
        ref={buttonRef}
        type="button"
        className="status-bar-model"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        modelo: <span>{modelLabel(brain, routing)}</span>
      </button>
      {open && (
        <div ref={popRef} className="model-pop" role="dialog" aria-label="Trocar o modelo">
          <p className="model-pop-title">Quem responde</p>
          <div role="radiogroup" aria-label="Quem responde" className="model-pop-list">
            {MODES.map((m) => {
              const unavailable = m.value === "local" && !brain?.mac_online;
              return (
                <button
                  key={m.value}
                  type="button"
                  role="radio"
                  aria-checked={brain?.mode === m.value}
                  disabled={unavailable}
                  onClick={() => void choose(m.value)}
                >
                  <span className="model-pop-label">{m.label}</span>
                  <span className="model-pop-note">{unavailable ? "O Mac não está oferecendo modelo agora." : m.note}</span>
                </button>
              );
            })}
          </div>
          {routing && routing.configured.length > 0 && (
            <p className="model-pop-foot">Na nuvem, nesta ordem: {routing.personal.join(", ")}.</p>
          )}
        </div>
      )}
    </footer>
  );
}
