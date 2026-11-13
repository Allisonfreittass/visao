import { useEffect, useState } from "react";

import { useBackClose } from "../hooks/useBackClose";
import { useDragToClose } from "../hooks/useDragToClose";

import type { ArtifactSummary } from "../api";

/** The card under the reply that said it would write a page: "Criando…", then open it. */
export function ArtifactCard({ artifact, onOpen }: { artifact: ArtifactSummary; onOpen: (a: ArtifactSummary) => void }) {
  const ready = artifact.status === "ready" && artifact.path;
  return (
    <div className={`artifact-card artifact-card--${artifact.status}`} role="group" aria-label={`Página: ${artifact.title}`}>
      <div className="artifact-card-text">
        <strong>{artifact.title}</strong>
        <span>
          {artifact.status === "pending" && "Criando a página…"}
          {artifact.status === "failed" && (artifact.error ?? "Não deu para criar a página.")}
          {ready && "index.html"}
        </span>
      </div>
      {artifact.status === "pending" && (
        <div className="artifact-card-making" aria-hidden="true">
          <span className="thinking-dots"><i /><i /><i /></span>
          Escrevendo {artifact.title}
        </div>
      )}
      {ready && (
        <button type="button" className="artifact-card-open" onClick={() => onOpen(artifact)}>
          Abrir
        </button>
      )}
    </div>
  );
}

/** The page over the chat, in a frame with no scripts and no access to the app. */
export function ArtifactViewer({ artifact, url, onClose, onDelete, docked }: { artifact: ArtifactSummary; url: string; onClose: () => void; onDelete: () => void; docked?: boolean }) {
  const [copied, setCopied] = useState(false);
  useBackClose(!docked, onClose);
  const drag = useDragToClose("down", onClose);
  const canShare = typeof navigator !== "undefined" && typeof navigator.share === "function" && !docked;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function share() {
    try {
      await navigator.share({ title: artifact.title, url });
    } catch {
      // Closed the share sheet: nothing to do.
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // No clipboard here: "Nova aba" still gives the address.
    }
  }

  return (
    <div
      className={`artifact-viewer${docked ? " artifact-viewer--docked" : ""}${drag.offset ? " artifact-viewer--dragging" : ""}`}
      role={docked ? "region" : "dialog"}
      aria-modal={docked ? undefined : true}
      aria-label={artifact.title}
      style={drag.offset ? { transform: `translateY(${drag.offset}px)` } : undefined}
    >
      <header className="artifact-viewer-bar" {...(docked ? {} : drag.handlers)}>
        {!docked && <span className="sheet-grabber" aria-hidden="true" />}
        <strong>{artifact.title}</strong>
        <div className="row">
          {canShare ? (
            <button type="button" onClick={() => void share()} title="Quem tiver o link consegue abrir">Compartilhar</button>
          ) : (
            <button type="button" onClick={() => void copy()} title="Quem tiver o link consegue abrir">{copied ? "Copiado" : "Copiar link"}</button>
          )}
          <a className="artifact-viewer-tab" href={url} target="_blank" rel="noopener noreferrer">Nova aba</a>
          <button type="button" className="ghost" onClick={onDelete} title="O link para de funcionar">Apagar</button>
          <button type="button" className="artifact-viewer-close" onClick={onClose} aria-label="Fechar">×</button>
        </div>
      </header>
      <iframe
        className="artifact-viewer-frame"
        src={url}
        title={artifact.title}
        sandbox="allow-popups allow-popups-to-escape-sandbox"
        referrerPolicy="no-referrer"
      />
    </div>
  );
}
