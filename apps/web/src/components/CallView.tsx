import { useEffect, useState } from "react";

import type { Message } from "../api";
import { Orb, STATE_LABELS } from "../orb/Orb";
import type { OrbState } from "../orb/orbModel";
import { speakableText } from "../speech/speakable";

interface CallViewProps {
  agentName: string | null;
  state: OrbState;
  level: () => number;
  messages: Message[];
  engine: "server" | "device" | null;
  speaking: boolean;
  error: string | null;
  onInterrupt: () => void;
  onHangUp: () => void;
}

function clock(ms: number): string {
  const total = Math.floor(ms / 1000);
  const minutes = Math.floor(total / 60).toString().padStart(2, "0");
  return `${minutes}:${(total % 60).toString().padStart(2, "0")}`;
}

const HINTS: Partial<Record<OrbState, string>> = {
  LISTENING: "Pode falar. Eu espero você terminar.",
  THINKING: "Pensando no que você disse.",
  SPEAKING: "Fale por cima para me interromper.",
  INTERRUPTED: "Parei. Continue.",
  DISCONNECTED: "Perdi a conexão. Tentando voltar.",
};

/** A call: the whole screen is the conversation, hands free, the screen kept on. */
export function CallView({ agentName, state, level, messages, engine, speaking, error, onInterrupt, onHangUp }: CallViewProps) {
  const [started] = useState(() => Date.now());
  const [now, setNow] = useState(started);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onHangUp();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onHangUp]);

  const lastUser = [...messages].reverse().find((m) => m.role === "user");
  const lastReply = [...messages].reverse().find((m) => m.role === "assistant");
  const size = Math.min(300, Math.round(window.innerWidth * 0.7));

  return (
    <div className="call" role="dialog" aria-modal="true" aria-label="Ligação">
      <header className="call-top">
        <span className="rs-status"><span className="rs-ponto" aria-hidden="true" />Em ligação · {clock(now - started)}</span>
        <span className="call-engine">{engine === "device" ? "Voz do aparelho" : "Voz própria"}</span>
      </header>
      <div className="call-center">
        <Orb state={state} size={size} getLevel={level} />
        <h1 className="call-name">{agentName ?? <em>Sem nome ainda</em>}</h1>
        <p className="call-state" aria-live="polite">{STATE_LABELS[state]}</p>
        <p className="call-hint">{HINTS[state] ?? "Estou aqui."}</p>
      </div>
      <div className="call-transcript" aria-live="polite">
        {lastUser && <p><span>Você</span>{lastUser.content}</p>}
        {lastReply && <p><span>{agentName ?? "Ele"}</span>{speakableText(lastReply.content).slice(0, 280)}</p>}
        {error && <p className="error" role="alert">{error}</p>}
      </div>
      <footer className="call-actions">
        {speaking && <button type="button" className="rs-botao" onClick={onInterrupt}>Interromper</button>}
        <button type="button" className="rs-botao rs-botao--principal call-hangup" onClick={onHangUp}>Desligar</button>
      </footer>
    </div>
  );
}
