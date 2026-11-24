import { useCallback, useEffect, useState } from "react";

import type { Api, Panel, QuietHours } from "../api";

const POLL_MS = 60_000;

/** One thing he does on his own, built from what the server already has (there is no routines
 * table): the morning summary, studying, researching on his own, and each watched panel. */
export interface Routine {
  id: string;
  title: string;
  /** When it runs, as the server knows it. */
  when: string;
  /** Where the result shows up. */
  delivery: string;
  on: boolean;
  kind: "briefing" | "study" | "research" | "panel";
}

export interface Routines {
  list: Routine[];
  quiet: QuietHours | null;
  /** How many are on. */
  active: number;
  loaded: boolean;
  toggle: (routine: Routine) => Promise<void>;
  refresh: () => void;
}

/** "22:00" → "22h"; "07:30" stays "7h30". */
export function shortHour(hhmm: string): string {
  const [h, m] = hhmm.split(":");
  const hour = String(Number(h));
  return m && m !== "00" ? `${hour}h${m}` : `${hour}h`;
}

function panelWhen(panel: Panel): string {
  if (panel.watch_every_hours) return `a cada ${panel.watch_every_hours} h perto da meta`;
  return "uma vez por dia";
}

export function buildRoutines(input: {
  briefing: boolean | undefined;
  research: boolean;
  study: { enabled: boolean; interval_hours: number } | null;
  panels: Panel[];
  quiet: QuietHours | null;
}): Routine[] {
  const briefingAt = input.quiet ? (input.quiet.quiet_start === input.quiet.quiet_end ? "08:00" : input.quiet.quiet_end) : null;
  const list: Routine[] = [];
  if (input.briefing !== undefined) {
    list.push({
      id: "briefing",
      kind: "briefing",
      title: "Resumo da manhã",
      when: briefingAt ? `todo dia · ${briefingAt}, no fim do silêncio` : "todo dia, no fim do silêncio",
      delivery: "entrega: Início e notificação",
      on: input.briefing,
    });
  }
  if (input.study) {
    list.push({
      id: "study",
      kind: "study",
      title: "Estudar entre conversas",
      when: `a cada ${input.study.interval_hours} h, fora do silêncio`,
      delivery: "entrega: Caderno",
      on: input.study.enabled,
    });
  }
  list.push({
    id: "research",
    kind: "research",
    title: "Pesquisar sozinho",
    when: "quando um assunto pede, fora do silêncio",
    delivery: "entrega: Caderno, com fontes",
    on: input.research,
  });
  for (const panel of input.panels) {
    if (panel.status !== "active" && panel.status !== "paused") continue;
    list.push({
      id: `panel:${panel.id}`,
      kind: "panel",
      title: `Conferir: ${panel.title}`,
      when: panelWhen(panel),
      delivery: "entrega: painel",
      on: panel.status === "active",
    });
  }
  return list;
}

/** The routines, shared by Rotinas and the status bar. Read again every minute. */
export function useRoutines(api: Api, enabled: boolean, onError: (e: unknown) => void): Routines {
  const [list, setList] = useState<Routine[]>([]);
  const [quiet, setQuiet] = useState<QuietHours | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [tick, setTick] = useState(0);
  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    const load = () =>
      Promise.all([
        api.permissions().catch(() => null),
        api.study().catch(() => null),
        api.panels().catch(() => [] as Panel[]),
        api.quietHours().catch(() => null),
      ]).then(([perms, study, panels, hours]) => {
        if (!alive) return;
        setQuiet(hours);
        setList(buildRoutines({
          briefing: perms?.morning_briefing,
          research: !!perms?.auto_research,
          study: study ? { enabled: study.enabled, interval_hours: study.interval_hours } : null,
          panels,
          quiet: hours,
        }));
        setLoaded(true);
      });
    void load();
    const timer = setInterval(load, POLL_MS);
    return () => { alive = false; clearInterval(timer); };
  }, [api, enabled, tick]);

  const toggle = useCallback(async (routine: Routine) => {
    const next = !routine.on;
    setList((l) => l.map((r) => (r.id === routine.id ? { ...r, on: next } : r)));
    try {
      if (routine.kind === "briefing") await api.setMorningBriefing(next);
      else if (routine.kind === "study") await api.setStudyEnabled(next);
      else if (routine.kind === "research") await api.setAutoResearch(next);
      else await api.setPanelStatus(routine.id.slice("panel:".length), next ? "active" : "paused");
    } catch (e) {
      setList((l) => l.map((r) => (r.id === routine.id ? { ...r, on: routine.on } : r)));
      onError(e);
    }
  }, [api, onError]);

  return { list, quiet, active: list.filter((r) => r.on).length, loaded, toggle, refresh };
}
