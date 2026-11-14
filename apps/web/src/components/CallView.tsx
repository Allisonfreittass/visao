import { useEffect, useState } from "react";

import type { Message } from "../api";
import { type CallCamera, cameraSupported } from "../call/camera";
import { Icon } from "./Icon";
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
  /** Something waiting for a yes (an email, an event, Mac work), shown big in the call. */
  ask?: { label: string; text: string; detail?: string; onApprove: () => void; onReject: () => void } | null;
  /** Whether a spoken "pode mandar" / "não" answers it. */
  voiceApproval?: boolean;
  /** The camera: while on, what it shows goes with each sentence you say. */
  camera?: CallCamera;
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
export function CallView({ agentName, state, level, messages, engine, speaking, error, onInterrupt, onHangUp, ask, voiceApproval, camera }: CallViewProps) {
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

  const stream = camera?.stream ?? null;
  const videoRef = camera?.videoRef;
  useEffect(() => {
    if (videoRef?.current) videoRef.current.srcObject = stream;
  }, [stream, videoRef]);

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
        {camera?.error && <p className="error" role="alert">{camera.error}</p>}
      </div>
      {camera?.on && (
        <figure className="call-camera" aria-label="O que a câmera está mostrando">
          {/* What he will see with your next sentence. */}
          <video ref={camera.videoRef} autoPlay playsInline muted className={camera.facing === "user" ? "is-mirrored" : undefined} />
          <button type="button" className="call-camera-flip" onClick={camera.flip} aria-label="Trocar de câmera">
            <Icon name="flip" size={18} />
          </button>
        </figure>
      )}
      {ask && (
        <section className="call-ask" role="group" aria-label={`${ask.label}: ${ask.text}, esperando você`}>
          <span className="call-ask-label">{ask.label}</span>
          <p className="call-ask-text">{ask.text}</p>
          {ask.detail && <p className="call-ask-detail">{ask.detail.slice(0, 280)}</p>}
          <div className="call-ask-buttons">
            <button type="button" className="call-ask-no" onClick={ask.onReject}>Recusar</button>
            <button type="button" className="call-ask-yes" onClick={ask.onApprove}>Aprovar</button>
          </div>
          {voiceApproval && <p className="call-ask-voice">Ou diga “pode mandar” para aprovar, ou “não”.</p>}
        </section>
      )}
      <footer className="call-actions">
        {camera && cameraSupported() && (
          <button
            type="button"
            className={`call-camera-toggle${camera.on ? " is-on" : ""}`}
            onClick={camera.toggle}
            aria-pressed={camera.on}
            aria-label={camera.on ? "Desligar a câmera" : "Ligar a câmera: ele vê o que ela mostra quando você fala"}
          >
            <Icon name="camera" size={20} />
          </button>
        )}
        {speaking && <button type="button" className="rs-botao" onClick={onInterrupt}>Interromper</button>}
        <button type="button" className="rs-botao rs-botao--principal call-hangup" onClick={onHangUp}>Desligar</button>
      </footer>
    </div>
  );
}
