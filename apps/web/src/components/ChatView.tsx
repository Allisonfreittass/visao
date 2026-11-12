import { type FormEvent, type KeyboardEvent, type ReactNode, useEffect, useRef, useState } from "react";

import { utcDate, type Message } from "../api";

/** Something waiting for one tap, right above where you type. */
export interface Ask {
  id: string;
  label: string;
  text: string;
  detail?: string;
  onApprove: () => void;
  onReject: () => void;
}
import { MessageContent } from "./MessageContent";
import { FeedbackBar } from "./FeedbackBar";

interface ChatViewProps {
  /** The slim bar above the messages: which conversation, and the call on smaller screens. */
  header?: ReactNode;
  messages: Message[];
  /** What it put together from this conversation (Mac work, an email, an event). */
  asks?: Ask[];
  agentName?: string | null;
  hidden?: boolean;
  /** Changes when something outside wants the person typing here, e.g. answering a notice. */
  focusRequest?: number;
  sending: boolean;
  error: string | null;
  onSend: (text: string) => void;
  onFeedback: (messageId: string, rating: 1 | -1, tags: string[]) => Promise<string | null>;
}

export function ChatView({ header, messages, asks = [], agentName, hidden, focusRequest, sending, error, onSend, onFeedback }: ChatViewProps) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, sending]);

  useEffect(() => {
    if (focusRequest) textareaRef.current?.focus();
  }, [focusRequest]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    onSend(text);
    setDraft("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends, Shift+Enter breaks the line.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <section className="chat" hidden={hidden}>
      {header}
      <div className="messages" aria-live="polite">
        {messages.length === 0 && !sending && (
          <div className="empty-conversation">
            <span className="rotulo">Conversa nova</span>
            <h2>Por onde a gente <em>começa?</em></h2>
            <p>Um bug, uma ideia pela metade, um plano. Pode escrever, colar código ou me ligar.</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={m.id} className={`bubble ${m.role}${i === messages.length - 1 ? " bubble--last" : ""}`}>
            <div className="message-meta"><span>{m.role === "user" ? "Você" : agentName ?? "Ele"}</span>{m.origin === "initiative" && <span className="initiative-tag">puxou conversa</span>}{m.origin === "arm" && <span className="initiative-tag">no Mac</span>}{m.origin === "google" && <span className="initiative-tag">no Google</span>}<time>{utcDate(m.created_at).toLocaleTimeString("pt-BR", {hour: "2-digit", minute: "2-digit"})}</time></div>
            <MessageContent text={m.content} />
            {m.sources && m.sources.length > 0 && (
              <ol className="sources" aria-label="Fontes pesquisadas">
                {m.sources.map((s) => (
                  <li key={s.url}>
                    <a href={s.url} target="_blank" rel="noopener noreferrer">
                      {s.title}
                    </a>{" "}
                    <span>· {s.source}</span>
                  </li>
                ))}
              </ol>
            )}
            {m.role === "assistant" && (
              <details className="message-feedback"><summary>Como foi essa resposta?</summary>
                <FeedbackBar onSend={(rating, tags) => onFeedback(m.id, rating, tags)} />
              </details>
            )}
          </div>
        ))}
        {sending && <div className="bubble assistant pending" role="status"><span className="thinking-dots"><i /><i /><i /></span> Pensando</div>}
        <div ref={endRef} />
      </div>
      {error && <p className="error" role="alert">× {error}</p>}
      {asks.map((ask) => (
        <div key={ask.id} className="ask-bar" role="group" aria-label={`${ask.label}: ${ask.text}, esperando você`}>
          <span className="rotulo">{ask.label}</span>
          <span className="ask-bar-text">{ask.text}</span>
          {ask.detail && <p className="ask-bar-detail pre">{ask.detail}</p>}
          <div className="row">
            <button type="button" onClick={ask.onApprove}>Aprovar</button>
            <button type="button" className="ghost" onClick={ask.onReject}>Recusar</button>
          </div>
        </div>
      ))}
      <form className="composer" onSubmit={submit}>
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
          }}
          onKeyDown={onKeyDown}
          placeholder="Escreva ou cole código…"
          rows={1}
          maxLength={8000}
          aria-label="Mensagem"
        />
        <button type="submit" aria-label="Enviar mensagem" disabled={sending || !draft.trim()}>
          <span aria-hidden="true">→</span>
        </button>
      </form>
      <p className="composer-note">Enter envia · Shift + Enter quebra a linha · <code>/mac projeto</code> pede ao Mac</p>
    </section>
  );
}
