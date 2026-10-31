import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import type { Message } from "../api";

interface ChatViewProps {
  messages: Message[];
  sending: boolean;
  error: string | null;
  onSend: (text: string) => void;
}

export function ChatView({ messages, sending, error, onSend }: ChatViewProps) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, sending]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    onSend(text);
    setDraft("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends, Shift+Enter breaks the line.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <section className="chat">
      <div className="messages" aria-live="polite">
        {messages.length === 0 && !sending && (
          <p className="hint">Conversa nova. Escreva algo para começar.</p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`bubble ${m.role}`}>
            {m.content}
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
          </div>
        ))}
        {sending && <div className="bubble assistant pending">…</div>}
        <div ref={endRef} />
      </div>
      {error && <p className="error">{error}</p>}
      <form className="composer" onSubmit={submit}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Mensagem"
          rows={1}
          maxLength={8000}
          aria-label="Mensagem"
        />
        <button type="submit" disabled={sending || !draft.trim()}>
          Enviar
        </button>
      </form>
    </section>
  );
}
