// The assistant's state machine, as the app derives it (App.tsx: orbState), and the ring's states
// (DESIGN.md §6) it shows. The names of AssistantState come from the voice and connection logic.
export type AssistantState =
  | "IDLE"
  | "LISTENING"
  | "THINKING"
  | "SPEAKING"
  | "INTERRUPTED"
  | "DISCONNECTED";

export const STATE_LABELS: Record<AssistantState, string> = {
  IDLE: "ocioso",
  LISTENING: "ouvindo",
  THINKING: "pensando",
  SPEAKING: "falando",
  INTERRUPTED: "interrompido",
  DISCONNECTED: "desconectado",
};

/** What the ring shows (DESIGN.md §6). */
export type AnelEstado = "ocioso" | "ouvindo" | "pensando" | "fala" | "aprovacao" | "pausado" | "silencio";

export const ANEL_ESTADOS: AnelEstado[] = ["ocioso", "ouvindo", "pensando", "fala", "aprovacao", "pausado", "silencio"];

export const ANEL_LABELS: Record<AnelEstado, string> = {
  ocioso: "ocioso",
  ouvindo: "ouvindo",
  pensando: "pensando",
  fala: "abriu uma conversa",
  aprovacao: "esperando seu sim",
  pausado: "pausado",
  silencio: "em silêncio",
};

interface Signals {
  state: AssistantState;
  /** A task is running on the Mac right now: he is working, the ring thinks. */
  macWorking?: boolean;
  /** Something he prepared waits for a yes (Mac, e-mail, agenda, panel offer, goal). */
  approvals?: number;
  /** He opened a conversation and it has not been read yet: the only thing that shows "fala". */
  opening?: boolean;
  /** The owner paused his autonomy in Ajustes. */
  paused?: boolean;
}

/** Maps the app's signals to the ring. What happens now (voice, a reply being written) wins over
 * what waits; without the server the ring goes silent. */
export function anelEstado({ state, macWorking = false, approvals = 0, opening = false, paused = false }: Signals): AnelEstado {
  switch (state) {
    case "DISCONNECTED":
      return "silencio";
    // His voice playing is the same wave, pulled by his own volume; "fala" is only an opening.
    case "LISTENING":
    case "INTERRUPTED":
    case "SPEAKING":
      return "ouvindo";
    case "THINKING":
      return "pensando";
    case "IDLE":
      if (macWorking) return "pensando";
      if (approvals > 0) return "aprovacao";
      if (paused) return "pausado";
      if (opening) return "fala";
      return "ocioso";
  }
}
