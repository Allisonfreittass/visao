// The assistant's state machine, as the app derives it (App.tsx: orbState) and as the Ciclope
// shows it. The names on the left come from the voice and connection logic and do not change.
export type AssistantState =
  | "IDLE"
  | "LISTENING"
  | "THINKING"
  | "SPEAKING"
  | "INTERRUPTED"
  | "DISCONNECTED";

/** What the Ciclope does. "interrupted" is the listening pose after one quick blink. */
export type CiclopeState =
  | "idle"
  | "listening"
  | "thinking"
  | "speaking"
  | "working"
  | "error"
  | "offline"
  | "interrupted";

export const STATE_LABELS: Record<AssistantState, string> = {
  IDLE: "ocioso",
  LISTENING: "ouvindo",
  THINKING: "pensando",
  SPEAKING: "falando",
  INTERRUPTED: "interrompido",
  DISCONNECTED: "desconectado",
};

export const CICLOPE_LABELS: Record<CiclopeState, string> = {
  idle: "à toa",
  listening: "ouvindo",
  thinking: "pensando",
  speaking: "falando",
  working: "agindo no Mac",
  error: "algo deu errado",
  offline: "desconectado",
  interrupted: "interrompido",
};

interface Signals {
  state: AssistantState;
  /** A task is running on the Mac right now (an arm task with status "running"). */
  macWorking?: boolean;
  /** An error is on screen. */
  error?: boolean;
}

/** Maps the app's state to the Ciclope's. Only a resting assistant shows "working" or "error":
 * listening, thinking and speaking always win, and so does being offline. */
export function ciclopeState({ state, macWorking = false, error = false }: Signals): CiclopeState {
  switch (state) {
    case "DISCONNECTED":
      return "offline";
    case "LISTENING":
      return "listening";
    case "THINKING":
      return "thinking";
    case "SPEAKING":
      return "speaking";
    case "INTERRUPTED":
      return "interrupted";
    case "IDLE":
      if (macWorking) return "working";
      if (error) return "error";
      return "idle";
  }
}
