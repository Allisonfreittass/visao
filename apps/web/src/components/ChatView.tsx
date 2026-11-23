import { type ClipboardEvent, type DragEvent, type FormEvent, Fragment, type KeyboardEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import { type ArtifactSummary, type Attachment, type ProgressStep, type Segment, utcDate, type Message } from "../api";
import { dividers } from "../labels";
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
import { Anel } from "../anel/Anel";
import { Sensor, type SensorKind } from "../anel/Sensor";
import type { AnelEstado } from "../anel/state";
import { ArtifactCard, ArtifactViewer } from "./ArtifactCard";
import { Icon } from "./Icon";
import { SwipeReply } from "./SwipeReply";
import { DraftAttachments, MessageAttachments } from "./Attachments";
import { MessageContent } from "./MessageContent";
import { QuoteTable, tableBubble } from "./QuoteTable";
import { commonPrefix, revealStep } from "../stream";
import { FeedbackBar } from "./FeedbackBar";
import { SourcesPill } from "./SourcesPill";

interface ChatViewProps {
  /** The slim bar above the messages: which conversation, and the call on smaller screens. */
  header?: ReactNode;
  /** A reply that changed a project offers to open it (ADR-0021). */
  onOpenProject?: (id: string) => void;
  projectName?: (id: string) => string | undefined;
  messages: Message[];
  /** The continuous conversation's closed stretches: a divider with the day and the subject. */
  segments?: Segment[];
  /** The continuous conversation loads backwards: there are older messages to bring. */
  olderLeft?: boolean;
  onLoadOlder?: () => void;
  /** What it put together from this conversation (Mac work, an email, an event). */
  asks?: Ask[];
  agentName?: string | null;
  hidden?: boolean;
  /** Changes when something outside wants the person typing here, e.g. answering a notice. */
  focusRequest?: number;
  /** Text put in the box from outside (a suggestion on Início); `n` changes each time. */
  draftRequest?: { text: string; n: number } | null;
  sending: boolean;
  /** What the turn in flight is doing now; null shows "Pensando". */
  status?: ProgressStep | null;
  /** Parar the turn in flight. */
  onStop?: () => void;
  /** The reply as it is being written (the stream); null when none is on the way. */
  liveText?: string | null;
  /** The reply that arrived while its text is still coming in: shown in the live bubble. */
  settlingId?: string | null;
  /** The live bubble finished showing the reply: it becomes the message. */
  onSettled?: () => void;
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
  /** On a computer, pages open beside the chat (the app shows them); otherwise over it, here. */
  onOpenPage?: (artifact: ArtifactSummary) => void;
  /** The assistant's live state, for the ring beside its newest reply. */
  anel?: AnelEstado;
  /** A task runs on the Mac: the newest reply says so. */
  macWorking?: boolean;
  /** Voice level 0..1 while it speaks. */
  voiceLevel?: () => number;
  /** The turn in flight, step by step (shown as step cards before the reply's text). */
  steps?: ProgressStep[];
}

/** Which sensor goes on a step card, from what the step says. */
export function stepSensor(label: string): SensorKind {
  if (/\bmac\b|finder|safari|claude code|terminal/i.test(label)) return "mac";
  if (/gmail|e-?mail/i.test(label)) return "email";
  if (/agenda|caderno|anota/i.test(label)) return "caderno";
  return "projeto";
}

function StepCards({ steps }: { steps: ProgressStep[] }) {
  if (steps.length === 0) return null;
  return (
    <ol className="step-cards" aria-label="Passos">
      {steps.map((step, i) => {
        const now = i === steps.length - 1;
        const kind = stepSensor(step.label);
        return (
          <li key={`${i}-${step.label}`} className="step-card">
            <Sensor kind={kind} size={20} />
            <span className="step-card-text">
              {step.label}
              {step.detail && <small>{step.detail}</small>}
            </span>
            {now ? (
              <span className="step-card-status step-card-status--now"><span className="step-spinner" aria-hidden="true" />agora</span>
            ) : (
              <span className="step-card-status">✓ feito</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** Which sensor goes on a card that waits for a yes. */
function askSensor(label: string): SensorKind {
  if (/^mac/i.test(label)) return "mac";
  if (/email|e-mail/i.test(label)) return "email";
  if (/agenda|evento/i.test(label)) return "caderno";
  return "projeto";
}

function uploadError(e: unknown): string {
  return e instanceof Error && e.message ? e.message : "Não deu para enviar";
}

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
/** A new chunk of words starts (and fades in) this often while the text comes in. */
const CHUNK_MS = 140;

/** The text that came in bursts, let out at a steady pace (stream.ts) with where each recent
 * chunk starts, for the fade. With Reduzir movimento, it is all there at once. */
function useReveal(target: string) {
  const [shown, setShown] = useState(target.length);
  const state = useRef({ shown: target.length, target, chunks: [] as number[], chunkAt: 0 });
  useEffect(() => {
    const s = state.current;
    const keep = commonPrefix(s.target, target);
    s.target = target;
    if (s.shown > keep) s.shown = keep;
    if (reducedMotion()) {
      s.shown = target.length;
      setShown(target.length);
      return;
    }
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      const next = revealStep(s.shown, s.target.length, dt);
      if (now - s.chunkAt > CHUNK_MS && next > s.shown) {
        s.chunks = [...s.chunks.filter((c) => c < next && c >= next - 400), Math.floor(s.shown)];
        s.chunkAt = now;
      }
      s.shown = next;
      setShown(Math.floor(next));
      if (next < s.target.length) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target]);
  return { text: target.slice(0, shown), chunks: state.current.chunks, done: shown >= target.length };
}

/** The assistant's bubble while it works: it breathes with the current step, then the text comes
 * in where the dots were, and when the reply has arrived and finished showing it hands over to
 * the message itself (the same bubble, no jump). */
function LiveBubble({ text, status, onStop, settling, onSettled, anel = "pensando", steps = [] }: { text: string; status?: ProgressStep | null; onStop?: () => void; settling: boolean; onSettled?: () => void; anel?: AnelEstado; steps?: ProgressStep[] }) {
  const reveal = useReveal(text);
  useEffect(() => {
    if (settling && reveal.done) onSettled?.();
  }, [settling, reveal.done, onSettled]);
  if (!reveal.text) {
    return (
      <div className="live-status" role="status" aria-live="polite">
        <div className="bubble assistant pending">
          <Anel estado={anel} size={36} decorative className="message-avatar" />
          <span key={status?.label ?? "pensando"} className="live-status-label">{status?.label ?? "Processando"}</span>
          {onStop && (
            <button type="button" className="live-status-stop" onClick={onStop} aria-label="Parar" title="Parar">
              <span aria-hidden="true">×</span>
            </button>
          )}
        </div>
        {steps.length > 1 ? <StepCards steps={steps} /> : status?.detail && <span key={status.detail} className="live-status-detail">{status.detail}</span>}
      </div>
    );
  }
  return (
    <div className="bubble assistant bubble--live" aria-live="off">
      <div className="message-meta message-meta--live"><Anel estado={anel} size={36} decorative className="message-avatar" /><span className="message-label">Visão · {settling ? "concluído" : "respondendo"}</span></div>
      {!settling && <StepCards steps={steps} />}
      {!settling && status && <span key={status.label} className="live-status-label live-status-label--inline">{status.label}</span>}
      <MessageContent text={reveal.text} chunks={reveal.chunks} />
      {!settling && onStop && (
        <button type="button" className="live-status-stop live-status-stop--inline" onClick={onStop} aria-label="Parar" title="Parar">
          <span aria-hidden="true">×</span>
        </button>
      )}
    </div>
  );
}

export function ChatView({ header, onOpenProject, projectName, messages, segments, olderLeft, onLoadOlder, asks = [], agentName, hidden, focusRequest, draftRequest, sending, status, onStop, liveText = null, settlingId = null, onSettled, error, onSend, onUpload, loadAttachment, onFeedback, composerStart, placeholder, pageUrl, onDeleteArtifact, onOpenPage, anel = "ocioso", macWorking = false, voiceLevel, steps = [] }: ChatViewProps) {
  const [draft, setDraft] = useState("");
  // In the continuous conversation: a divider at each new day and at each stretch's start.
  const divided = useMemo(() => (segments ? dividers(messages, segments, utcDate) : new Map<string, string>()), [messages, segments]);
  const [files, setFiles] = useState<DraftFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const [viewing, setViewing] = useState<ArtifactSummary | null>(null);
  const [replyTo, setReplyTo] = useState<Message | null>(null);
  /** The message whose menu is open (long press, right click or the ⋯ button). */
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [rating, setRating] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  /** Whether you are at the end of the conversation: only then does it follow the new text. */
  const atEnd = useRef(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pickerRef = useRef<HTMLInputElement>(null);

  const lastIsYours = messages.at(-1)?.role === "user";
  useEffect(() => {
    // What you just sent always shows; the rest follows only if you are at the end.
    if (atEnd.current || lastIsYours) endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, sending, status?.label, asks.length, lastIsYours]);
  useEffect(() => {
    const list = listRef.current;
    if (list && atEnd.current && liveText) list.scrollTop = list.scrollHeight;
  });

  useEffect(() => {
    if (focusRequest) textareaRef.current?.focus();
  }, [focusRequest]);

  useEffect(() => {
    if (!draftRequest) return;
    setDraft(draftRequest.text);
    textareaRef.current?.focus();
  }, [draftRequest]);

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
      <div
        className="messages"
        aria-live="polite"
        ref={listRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          atEnd.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
      >
        {messages.length === 0 && !sending && (
          <div className="empty-conversation">
            <h2>Pronto para a <em>ordem.</em></h2>
            <p>Escreva, cole código, mande uma foto ou um arquivo, ou fale pelo microfone.</p>
          </div>
        )}
        {olderLeft && onLoadOlder && (
          <button type="button" className="load-older" onClick={onLoadOlder}>Carregar mensagens anteriores</button>
        )}
        {messages.filter((m) => m.id !== settlingId).map((m, i, shown) => (
          <Fragment key={m.id}>
          {segments && divided.get(m.id) && (
            <div className="chat-divider" role="separator" aria-label={divided.get(m.id)}>
              <span>{divided.get(m.id)}</span>
            </div>
          )}
          <SwipeReply
            id={`msg-${m.id}`}
            className={`bubble ${m.role}${i === shown.length - 1 ? " bubble--last" : ""}${m.local ? ` bubble--${m.local}` : ""}${m.streamed ? " bubble--streamed" : ""}`}
            disabled={!!m.local}
            onReply={() => {
              setReplyTo(m);
              textareaRef.current?.focus();
            }}
            onMenu={() => setMenuFor(m.id)}
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
            <div className="message-meta">{m.role === "assistant" && (
              i === shown.length - 1 && !sending
                ? <Anel estado={anel} size={36} level={anel === "ouvindo" ? voiceLevel : undefined} decorative className="message-avatar" />
                : <Anel estado="ocioso" size={36} animated={false} decorative className="message-avatar" />
            )}{m.role === "assistant" ? (
              i === shown.length - 1 && !sending && macWorking
                ? <span className="message-label message-label--working">Visão · executando no Mac</span>
                : <span className="message-label">{m.local_model ? "Visão · local" : "Visão · concluído"}</span>
            ) : <span>Você</span>}{m.origin === "arm" && <Sensor kind="mac" size={16} />}{m.origin === "initiative" && <span className="initiative-tag">puxou conversa</span>}{m.origin === "arm" && <span className="initiative-tag">no Mac</span>}{m.origin === "google" && <span className="initiative-tag">no Google</span>}{m.origin === "share" && <span className="initiative-tag">compartilhado do iPhone</span>}{m.local === "failed" ? <span className="failed-tag">não foi enviada</span> : m.local === "stopped" ? <span className="failed-tag">parada</span> : <time>{utcDate(m.created_at).toLocaleTimeString("pt-BR", {hour: "2-digit", minute: "2-digit"})}</time>}</div>
            {m.attachments && m.attachments.length > 0 && <MessageAttachments attachments={m.attachments} load={loadAttachment} />}
            {m.parts && m.parts.length > 1
              ? m.parts.map((part, n) => (
                  <div key={n} className="bubble-part" style={{ animationDelay: `${n * 0.35}s` }}>
                    {m.quote_table && n === tableBubble(m.parts, m.quote_table)
                      ? <QuoteTable table={m.quote_table} />
                      : <MessageContent text={part} />}
                  </div>
                ))
              : m.content && <MessageContent text={m.content} />}
            {m.artifact && <ArtifactCard artifact={m.artifact} onOpen={onOpenPage ?? setViewing} />}
            {m.project_id && onOpenProject && (
              <button type="button" className="project-link" onClick={() => onOpenProject(m.project_id as string)}>
                <span className="project-link-text">Abrir o projeto{projectName?.(m.project_id) ? ` «${projectName(m.project_id)}»` : ""}</span>
                <span aria-hidden="true">→</span>
              </button>
            )}
            {m.sources && m.sources.length > 0 && <SourcesPill sources={m.sources} at={m.created_at} />}
            {!m.local && (
              <button type="button" className="bubble-more" onClick={() => setMenuFor(menuFor === m.id ? null : m.id)} aria-label="Mais opções desta mensagem" aria-expanded={menuFor === m.id} title="Mais">
                <span aria-hidden="true">⋯</span>
              </button>
            )}
            {menuFor === m.id && (
              <div className="message-menu" role="menu">
                <button type="button" role="menuitem" onClick={() => { setReplyTo(m); setMenuFor(null); textareaRef.current?.focus(); }}>Responder</button>
                <button type="button" role="menuitem" onClick={() => { void navigator.clipboard?.writeText(m.content); setMenuFor(null); }}>Copiar texto</button>
                {m.role === "assistant" && (
                  <button type="button" role="menuitem" onClick={() => { setRating(m.id); setMenuFor(null); }}>Avaliar resposta</button>
                )}
                <button type="button" role="menuitem" className="message-menu-close" onClick={() => setMenuFor(null)}>Fechar</button>
              </div>
            )}
            {rating === m.id && m.role === "assistant" && (
              <div className="message-feedback">
                <span className="message-feedback-title">Como foi essa resposta?</span>
                <FeedbackBar onSend={(value, tags) => onFeedback(m.id, value, tags)} />
              </div>
            )}
          </SwipeReply>
          </Fragment>
        ))}
        {(sending || settlingId) && (
          <LiveBubble text={liveText ?? ""} status={status} onStop={onStop} settling={!!settlingId && !sending} onSettled={onSettled} anel={sending ? "pensando" : anel} steps={steps} />
        )}
        {asks.map((ask) => (
          <div key={ask.id} className="action-card" role="group" aria-label={`${ask.label}: ${ask.text}, esperando você`}>
            <span className="action-card-label"><Sensor kind={askSensor(ask.label)} size={18} />{ask.label}</span>
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
            <Icon name="send" size={20} />
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
