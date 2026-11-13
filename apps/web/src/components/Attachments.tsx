import { useEffect, useState } from "react";

import type { Attachment } from "../api";
import { attachmentUrl, type DraftFile, formatSize } from "../attachments";

type Loader = (id: string) => Promise<Blob>;

function Photo({ attachment, load }: { attachment: Attachment; load: Loader }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    attachmentUrl(attachment.id, load)
      .then((u) => alive && setUrl(u))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [attachment.id, load]);
  if (failed) return <span className="attachment-file">Foto indisponível</span>;
  return (
    <a className="attachment-photo" href={url ?? undefined} target="_blank" rel="noopener noreferrer" aria-label={`Abrir ${attachment.filename}`}>
      {url ? <img src={url} alt={attachment.filename} loading="lazy" /> : <span className="attachment-photo-wait" aria-hidden="true" />}
    </a>
  );
}

function FileChip({ attachment, load }: { attachment: Attachment; load: Loader }) {
  async function open() {
    try {
      const url = await attachmentUrl(attachment.id, load);
      const a = document.createElement("a");
      a.href = url;
      a.download = attachment.filename;
      a.click();
    } catch {
      // Nothing to open: the chip stays as a label.
    }
  }
  const kind = attachment.media_type === "application/pdf" ? "PDF" : "Texto";
  return (
    <button type="button" className="attachment-file" onClick={() => void open()} title="Baixar">
      <span className="attachment-file-icon" aria-hidden="true">{kind === "PDF" ? "PDF" : "TXT"}</span>
      <span className="attachment-file-text">
        <strong>{attachment.filename}</strong>
        <span>
          {kind} · {formatSize(attachment.size_bytes)}
          {attachment.readable === false && " · sem texto legível"}
        </span>
      </span>
    </button>
  );
}

/** What came with a message: photos as a grid, files as chips. */
export function MessageAttachments({ attachments, load }: { attachments: Attachment[]; load: Loader }) {
  const photos = attachments.filter((a) => a.kind === "image");
  const files = attachments.filter((a) => a.kind !== "image");
  return (
    <div className="message-attachments">
      {photos.length > 0 && (
        <div className={`attachment-photos attachment-photos--${Math.min(photos.length, 4)}`}>
          {photos.map((a) => <Photo key={a.id} attachment={a} load={load} />)}
        </div>
      )}
      {files.map((a) => <FileChip key={a.id} attachment={a} load={load} />)}
    </div>
  );
}

/** Picked files above the text box, each removable, each showing its upload. */
export function DraftAttachments({ files, onRemove }: { files: DraftFile[]; onRemove: (key: string) => void }) {
  if (files.length === 0) return null;
  return (
    <ul className="draft-attachments" aria-label="Anexos desta mensagem">
      {files.map((f) => (
        <li key={f.key} className={`draft-attachment draft-attachment--${f.status}`} title={f.error ?? f.name}>
          {f.isImage && f.preview ? <img src={f.preview} alt="" /> : <span className="draft-attachment-icon" aria-hidden="true">{/\.pdf$/i.test(f.name) ? "PDF" : "TXT"}</span>}
          <span className="draft-attachment-name">{f.status === "error" ? f.error : f.name}</span>
          {f.status === "uploading" && <span className="draft-attachment-spinner" role="status" aria-label="Enviando" />}
          <button type="button" className="draft-attachment-remove" onClick={() => onRemove(f.key)} aria-label={`Tirar ${f.name}`}>×</button>
        </li>
      ))}
    </ul>
  );
}
