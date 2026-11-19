import { useEffect, useState } from "react";

import type { Api, BrainMode, BrainState } from "../api";

const MODES: { value: BrainMode; label: string }[] = [
  { value: "nuvem", label: "Nuvem" },
  { value: "local", label: "Local" },
  { value: "auto", label: "Automático" },
];

/** One sentence on what the chosen mode does with the Mac as it is now. */
export function brainNote(state: BrainState): string {
  const mac = state.local_model
    ? `O Mac oferece o ${state.local_model}.`
    : state.mac_online
      ? "O Mac está ligado, mas sem modelo local configurado."
      : "O Mac não está oferecendo modelo local agora.";
  if (state.mode === "local") {
    return `${mac} Responde com o modelo do Mac e volta para a nuvem se ele dormir. O trabalho de fundo fica pausado.`;
  }
  if (state.mode === "auto") return `${mac} Usa a nuvem e passa para o modelo do Mac se ela falhar.`;
  return `${mac} Usa só a nuvem. Você também pode pedir no chat: “usa o modelo local”.`;
}

/** Ajustes: which model the Visão thinks with (docs/MODELO_LOCAL.md). */
export function BrainSettings({ api, onError }: { api: Api; onError: (e: unknown) => void }) {
  const [state, setState] = useState<BrainState | null>(null);

  useEffect(() => {
    api.brain().then(setState).catch(onError);
  }, [api, onError]);

  async function choose(mode: BrainMode) {
    if (!state || mode === state.mode) return;
    const before = state;
    setState({ ...state, mode });
    try {
      setState(await api.setBrain(mode));
    } catch (e) {
      setState(before);
      onError(e);
    }
  }

  return (
    <div className="setting">
      <div className="setting-text">
        <span id="brain-title" className="setting-title">Quem responde</span>
        <p className="note">{state ? brainNote(state) : "Carregando…"}</p>
      </div>
      <div className="segmented" role="radiogroup" aria-labelledby="brain-title">
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
