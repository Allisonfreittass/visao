import { useEffect, useState } from "react";

import type { Api, RoutingMode, RoutingState } from "../api";

const MODES: { value: RoutingMode; label: string }[] = [
  { value: "fixa", label: "Ordem fixa" },
  { value: "por_tarefa", label: "Por tarefa" },
];

function list(names: string[]): string {
  return names.join(", ");
}

/** What the chosen mode does with the providers configured on the server. */
export function routingNote(state: RoutingState): string {
  if (state.configured.length === 0) return "Nenhum provedor configurado no servidor.";
  if (state.configured.length === 1) {
    return `Só o ${state.configured[0]} está configurado, então a ordem não muda nada.`;
  }
  if (state.mode === "por_tarefa") {
    return (
      `A conversa e tudo que leva algo seu vão primeiro em ${list(state.personal)}. ` +
      `A revisão do estudo, só com texto público, vai primeiro em ${list(state.public)}. ` +
      "Passa para o próximo só se um falhar."
    );
  }
  return `Sempre ${list(state.configured)}, nessa ordem. Passa para o próximo só se um falhar.`;
}

/** Ajustes: which cloud provider goes first for each task (docs/decisions/0022). */
export function RoutingSettings({ api, onError }: { api: Api; onError: (e: unknown) => void }) {
  const [state, setState] = useState<RoutingState | null>(null);

  useEffect(() => {
    api.routing().then(setState).catch(onError);
  }, [api, onError]);

  async function choose(mode: RoutingMode) {
    if (!state || mode === state.mode) return;
    const before = state;
    setState({ ...state, mode });
    try {
      setState(await api.setRouting(mode));
    } catch (e) {
      setState(before);
      onError(e);
    }
  }

  return (
    <div className="setting">
      <div className="setting-text">
        <span id="routing-title" className="setting-title">Escolha do provedor</span>
        <p className="note">{state ? routingNote(state) : "Carregando…"}</p>
      </div>
      <div className="segmented" role="radiogroup" aria-labelledby="routing-title">
        {MODES.map((m) => (
          <button
            key={m.value}
            type="button"
            role="radio"
            aria-checked={state?.mode === m.value}
            disabled={!state}
            onClick={() => choose(m.value)}
          >
            {m.label}
          </button>
        ))}
      </div>
    </div>
  );
}
