import { useEffect, useRef } from "react";

import { type Message, utcDate } from "../api";
import { Icon } from "./Icon";

/** "Debounce na busca" → "debounce-na-busca". */
export function slug(title: string): string {
  const s = title
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  return s || "conversa";
}

/** The conversation as Markdown: who spoke, when, and the text. Only what is on screen: no memory,
 * nothing that was not sent. */
export function conversationMarkdown(title: string, messages: Message[], agentName: string | null): string {
  const lines = [`# ${title}`, ""];
  for (const m of messages) {
    if (m.local === "failed" || m.local === "queued" || !m.content.trim()) continue;
    const who = m.role === "assistant" ? agentName ?? "Visão" : "Você";
    const when = utcDate(m.created_at).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
    lines.push(`**${who}** · ${when}`, "", m.content.trim(), "");
  }
  return lines.join("\n");
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

interface ShareDialogProps {
  title: string;
  messages: Message[];
  agentName: string | null;
  onClose: () => void;
  /** The confirmation shown after each choice. */
  onDone: (message: string) => void;
}

/** Share or export the conversation in front: a private link (not available yet), Markdown, PDF. */
export function ShareDialog({ title, messages, agentName, onClose, onDone }: ShareDialogProps) {
  const firstRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    firstRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); before?.focus?.(); };
  }, [onClose]);

  const file = `${slug(title)}.md`;
  return (
    <div className="palette-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="share" role="dialog" aria-modal="true" aria-labelledby="share-title">
        <div className="share-head">
          <h2 id="share-title">Compartilhar a conversa</h2>
          <button type="button" className="palette-close" aria-label="Fechar" title="Fechar" onClick={onClose}>
            <Icon name="close" size={16} />
          </button>
        </div>
        <button type="button" className="share-option" disabled aria-describedby="share-link-note">
          <Icon name="link" size={18} />
          <span>
            <span className="share-option-title">Copiar link privado</span>
            <span id="share-link-note" className="share-option-note">Ainda não disponível: o servidor não cria link de conversa.</span>
          </span>
        </button>
        <button
          ref={firstRef}
          type="button"
          className="share-option"
          onClick={() => {
            download(file, conversationMarkdown(title, messages, agentName));
            onClose();
            onDone(`Conversa exportada: ${file}`);
          }}
        >
          <Icon name="file" size={18} />
          <span>
            <span className="share-option-title">Exportar Markdown</span>
            <span className="share-option-note">{file}, com o código</span>
          </span>
        </button>
        <button
          type="button"
          className="share-option"
          onClick={() => {
            onClose();
            onDone("Na janela de impressão, escolha “Salvar como PDF”.");
            setTimeout(() => window.print(), 50);
          }}
        >
          <Icon name="download" size={18} />
          <span>
            <span className="share-option-title">Salvar PDF</span>
            <span className="share-option-note">Para mandar a alguém de fora</span>
          </span>
        </button>
        <p className="share-foot">Vai só o texto da conversa: nada da memória dele.</p>
      </div>
    </div>
  );
}

/** The short confirmation at the bottom of the window. */
export function Toast({ message }: { message: string | null }) {
  return (
    <div className="toast-region" role="status" aria-live="polite">
      {message && <div className="toast">{message}</div>}
    </div>
  );
}
