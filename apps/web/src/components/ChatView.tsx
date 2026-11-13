import { type ClipboardEvent, type DragEvent, type FormEvent, type KeyboardEvent, type ReactNode, useEffect, useRef, useState } from "react";

import { type ArtifactSummary, type Attachment, type ProgressStep, utcDate, type Message } from "../api";
import { ACCEPT, type DraftFile, draftKey, MAX_FILES, pastedName, prepareImage } from "../attachments";

/** Something waiting for one tap, right above where you type. */
export interface Ask {
  id: string;
  label: string;
  text: string;
  detail?: string;
  onApprove: () => void;
  onReject: () => void;
}
import { ArtifactCard, ArtifactViewer } from "./ArtifactCard";
import { Icon } from "./Icon";
import { SwipeReply } from "./SwipeReply";
import { DraftAttachments, MessageAttachments } from "./Attachments";
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
  /** What the turn in flight is doing now; null shows "Pensando". */
  status?: ProgressStep | null;
  /** Parar the turn in flight. */
  onStop?: () => void;
  error: string | null;
  onSend: (text: string, attachments: Attachment[], replyTo: Message | null) => void;
  onUpload: (file: Blob, filename: string) => Promise<Attachment>;
  loadAttachment: (id: string) => Promise<Blob>;
  onFeedback: (messageId: string, rating: 1 | -1, tags: string[]) => Promise<string | null>;
  /** Shown left of the message box (the orb, in the "Céu" appearance). */
  composerStart?: ReactNode;
  /** The message box's hint, e.g. "Enviar mensagem para o Visão". */
  placeholder?: string;
  /** A page's full address from its path. */
  pageUrl: (path: string) => string;
  onDeleteArtifact: (artifact: ArtifactSummary) => void;
}

function uploadError(e: unknown): string {
  return e instanceof Error && e.message ? e.message : "Não deu para enviar";
}

export function ChatView({ header, messages, asks = [], agentName, hidden, focusRequest, sending, status, onStop, error, onSend, onUpload, loadAttachment, onFeedback, composerStart, placeholder, pageUrl, onDeleteArtifact }: ChatViewProps) {
  const [draft, setDraft] = useState("");
  const [files, setFiles] = useState<DraftFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const [viewing, setViewing] = useState<ArtifactSummary | null>(null);
  const [replyTo, setReplyTo] = useState<Message | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pickerRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, sending, status?.label, asks.length]);

  useEffect(() => {
    if (focusRequest) textareaRef.current?.focus();
  }, [focusRequest]);

  function update(key: string, change: Partial<DraftFile>) {
    setFiles((list) => list.map((f) => (f.key === key ? { ...f, ...change } : f)));
  }

  function addFiles(picked: File[], named?: (file: File, index: number) => string) {
    const room = MAX_FILES - files.length;
    if (room <= 0 || picked.length === 0) return;
    picked.slice(0, room).forEach((file, index) => {
      const key = draftKey();
      const name = named ? named(file, index) : file.name;
      const isImage = file.type.startsWith("image/");
      setFiles((list) => [...list, { key, name, isImage, status: "uploading", preview: isImage ? URL.createObjectURL(file) : undefined }]);
      void (async () => {
        try {
          const ready = isImage ? await prepareImage(file) : { blob: file, name };
          // A shrunk photo became a JPEG: keep the name it was shown with, with the new ending.
          const finalName = ready.name === file.name ? name : name.replace(/\.[^.]+$/, "") + ".jpg";
          const attachment = await onUpload(ready.blob, finalName);
          update(key, { status: "ready", attachment });
        } catch (e) {
          update(key, { status: "error", error: uploadError(e) });
        }
      })();
    });
  }

  function removeFile(key: string) {
    setFiles((list) => {
      const gone = list.find((f) => f.key === key);
      if (gone?.preview) URL.revokeObjectURL(gone.preview);
      return list.filter((f) => f.key !== key);
    });
  }

  const ready = files.filter((f) => f.status === "ready" && f.attachment).map((f) => f.attachment as Attachment);
  const uploading = files.some((f) => f.status === "uploading");
  // You can keep writing while it answers: those messages wait and go with the next turn.
  const canSend = !uploading && (draft.trim().length > 0 || ready.length > 0);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!canSend) return;
    onSend(draft.trim(), ready, replyTo);
    setDraft("");
    setReplyTo(null);
    files.forEach((f) => f.preview && URL.revokeObjectURL(f.preview));
    setFiles([]);
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends, Shift+Enter breaks the line.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const pasted = Array.from(event.clipboardData.files);
    if (pasted.length === 0) return; // plain text pastes as usual
    event.preventDefault();
    addFiles(pasted, pastedName);
  }

  function onDrop(event: DragEvent<HTMLElement>) {
    if (!event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    setDragging(false);
    addFiles(Array.from(event.dataTransfer.files));
  }

  return (
    <section
      className={`chat${dragging ? " chat--dragging" : ""}`}
      hidden={hidden}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes("Files")) return;
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target || !e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
      }}
      onDrop={onDrop}
    >
      {header}
      <div className="messages" aria-live="polite">
        {messages.length === 0 && !sending && (
          <div className="empty-conversation">
            <span className="rotulo">Conversa nova</span>
            <h2>Por onde a gente <em>começa?</em></h2>
            <p>Um bug, uma ideia pela metade, um plano. Pode escrever, colar código, mandar uma foto ou um arquivo, ou me ligar.</p>
          </div>
        )}
        {messages.map((m, i) => (
          <SwipeReply
            key={m.id}
            id={`msg-${m.id}`}
            className={`bubble ${m.role}${i === messages.length - 1 ? " bubble--last" : ""}${m.local ? ` bubble--${m.local}` : ""}`}
            disabled={!!m.local}
            onReply={() => {
              setReplyTo(m);
              textareaRef.current?.focus();
            }}
          >
            {!m.local && (
              <button
                type="button"
                className="bubble-reply"
                onClick={() => {
                  setReplyTo(m);
                  textareaRef.current?.focus();
                }}
                aria-label={`Responder a esta mensagem${m.role === "assistant" ? (agentName ? ` de ${agentName}` : " dele") : " sua"}`}
                title="Responder"
              >
                <Icon name="reply" size={15} />
              </button>
            )}
            {m.reply_to && (
              <button
                type="button"
                className="bubble-quote"
                onClick={() => document.getElementById(`msg-${m.reply_to!.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}
                title="Ir para a mensagem"
              >
                <span className="bubble-quote-who">{m.reply_to.role === "assistant" ? agentName ?? "Ele" : "Você"}</span>
                <span className="bubble-quote-text">{m.reply_to.excerpt}</span>
              </button>
            )}
            <div className="message-meta"><span>{m.role === "user" ? "Você" : agentName ?? "Ele"}</span>{m.origin === "initiative" && <span className="initiative-tag">puxou conversa</span>}{m.origin === "arm" && <span className="initiative-tag">no Mac</span>}{m.origin === "google" && <span className="initiative-tag">no Google</span>}{m.local === "failed" ? <span className="failed-tag">não foi enviada</span> : m.local === "stopped" ? <span className="failed-tag">parada</span> : <time>{utcDate(m.created_at).toLocaleTimeString("pt-BR", {hour: "2-digit", minute: "2-digit"})}</time>}</div>
            {m.attachments && m.attachments.length > 0 && <MessageAttachments attachments={m.attachments} load={loadAttachment} />}
            {m.content && <MessageContent text={m.content} />}
            {m.artifact && <ArtifactCard artifact={m.artifact} onOpen={setViewing} />}
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
          </SwipeReply>
        ))}
        {sending && (
          <div className="live-status" role="status" aria-live="polite">
            <div className="bubble assistant pending">
              <span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span>
              <span key={status?.label ?? "pensando"} className="live-status-label">{status?.label ?? "Pensando"}</span>
              {onStop && (
                <button type="button" className="live-status-stop" onClick={onStop} aria-label="Parar" title="Parar">
                  <span aria-hidden="true">×</span>
                </button>
              )}
            </div>
            {status?.detail && <span key={status.detail} className="live-status-detail">{status.detail}</span>}
          </div>
        )}
        {asks.map((ask) => (
          <div key={ask.id} className="action-card" role="group" aria-label={`${ask.label}: ${ask.text}, esperando você`}>
            <span className="action-card-label">{ask.label}</span>
            <p className="action-card-text">{ask.text}</p>
            {ask.detail && <p className="action-card-detail pre">{ask.detail}</p>}
            <div className="action-card-buttons">
              <button type="button" className="action-card-no" onClick={ask.onReject}>Recusar</button>
              <button type="button" className="action-card-yes" onClick={ask.onApprove}>Aprovar</button>
            </div>
            <span className="action-card-note">Nada roda sem o seu toque.</span>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      {error && <p className="error" role="alert">× {error}</p>}
      <div className="composer-dock">
      {composerStart}
      <form className="composer" onSubmit={submit}>
        {replyTo && (
          <div className="composer-reply" role="status">
            <span className="composer-reply-text">
              Respondendo a <strong>{replyTo.role === "assistant" ? agentName ?? "ele" : "você"}</strong>: «{replyTo.content.replace(/\s+/g, " ").slice(0, 120)}{replyTo.content.length > 120 ? "…" : ""}»
            </span>
            <button type="button" className="composer-reply-cancel" onClick={() => setReplyTo(null)} aria-label="Não responder a essa mensagem">×</button>
          </div>
        )}
        <DraftAttachments files={files} onRemove={removeFile} />
        <div className="composer-row">
          <button
            type="button"
            className="composer-attach"
            onClick={() => pickerRef.current?.click()}
            disabled={files.length >= MAX_FILES}
            aria-label="Anexar foto ou arquivo"
            title="Foto ou arquivo"
          >
            <span aria-hidden="true">+</span>
          </button>
          <input
            ref={pickerRef}
            type="file"
            accept={ACCEPT}
            multiple
            hidden
            onChange={(e) => {
              addFiles(Array.from(e.target.files ?? []));
              e.target.value = "";
            }}
          />
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
            }}
            onKeyDown={onKeyDown}
            onPaste={onPaste}
            placeholder={files.length ? "Quer dizer algo sobre isso?" : placeholder ?? "Escreva, cole código ou um print…"}
            rows={1}
            maxLength={8000}
            aria-label="Mensagem"
          />
          <button type="submit" className="composer-send" aria-label="Enviar mensagem" disabled={!canSend}>
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </form>
      </div>
      <p className="composer-note">Enter envia · Shift + Enter quebra a linha · cole ou arraste fotos e arquivos · <code>/mac projeto</code> pede ao Mac</p>
      {dragging && <div className="drop-hint" aria-hidden="true">Solte aqui para anexar</div>}
      {viewing?.path && (
        <ArtifactViewer
          artifact={viewing}
          url={pageUrl(viewing.path)}
          onClose={() => setViewing(null)}
          onDelete={() => {
            if (!window.confirm(`Apagar “${viewing.title}”? O link para de funcionar.`)) return;
            onDeleteArtifact(viewing);
            setViewing(null);
          }}
        />
      )}
    </section>
  );
}
