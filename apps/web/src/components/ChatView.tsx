import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import { utcDate, type Message } from "../api";
import { MessageContent } from "./MessageContent";
import { FeedbackBar } from "./FeedbackBar";

interface ChatViewProps {
  messages: Message[];
  agentName?: string | null;
  hidden?: boolean;
  /** Changes when something outside wants the person typing here, e.g. answering a notice. */
  focusRequest?: number;
  sending: boolean;
  error: string | null;
  onSend: (text: string) => void;
  onFeedback: (messageId: string, rating: 1 | -1, tags: string[]) => Promise<string | null>;
}

export function ChatView({ messages, agentName, hidden, focusRequest, sending, error, onSend, onFeedback }: ChatViewProps) {
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
      <div className="messages" aria-live="polite">
        {messages.length === 0 && !sending && (
          <div className="empty-conversation">
            <span className="rotulo">Conversa nova</span>
            <h2>Por onde a gente <em>começa?</em></h2>
            <p>Um bug, uma ideia pela metade, um plano. Cole o código direto aqui.</p>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`bubble ${m.role}`}>
            <div className="message-meta"><span>{m.role === "user" ? "Você" : agentName ?? "Ele"}</span>{m.origin === "initiative" && <span className="initiative-tag">puxou conversa</span>}<time>{utcDate(m.created_at).toLocaleTimeString("pt-BR", {hour: "2-digit", minute: "2-digit"})}</time></div>
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
      <p className="composer-note">Enter envia · Shift + Enter quebra a linha</p>
    </section>
  );
}
