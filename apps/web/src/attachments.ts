// Photos and files picked, pasted or dropped in the composer (docs/ANEXOS.md).

import type { Attachment } from "./api";

export const MAX_FILES = 4;
/** What the file picker offers; the server decides by the bytes either way. */
export const ACCEPT =
  "image/jpeg,image/png,image/webp,image/gif,.pdf,.txt,.md,.csv,.tsv,.json,.yaml,.yml,.xml,.html,.log,.sql," +
  ".py,.js,.jsx,.ts,.tsx,.java,.kt,.swift,.go,.rs,.rb,.php,.c,.h,.cpp,.cs,.sh,.toml,.ini,.vue,.dart";
/** The long side a vision model actually looks at; anything bigger only costs upload time. */
const MAX_SIDE = 1568;
const REENCODE_ABOVE_BYTES = 1.5 * 1024 * 1024;

export interface DraftFile {
  key: string;
  name: string;
  isImage: boolean;
  /** Local preview while uploading (photos only). */
  preview?: string;
  status: "uploading" | "ready" | "error";
  attachment?: Attachment;
  error?: string;
}

let counter = 0;
export function draftKey(): string {
  counter += 1;
  return `draft-${Date.now()}-${counter}`;
}

/** Shrinks a big photo in the browser before it travels. GIFs stay as they are (animation). */
export async function prepareImage(file: File): Promise<{ blob: Blob; name: string }> {
  if (!file.type.startsWith("image/") || file.type === "image/gif" || typeof createImageBitmap !== "function") {
    return { blob: file, name: file.name };
  }
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    return { blob: file, name: file.name }; // the server says whether it can use it
  }
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  if (scale === 1 && file.size <= REENCODE_ABOVE_BYTES) {
    bitmap.close();
    return { blob: file, name: file.name };
  }
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
  if (!blob) return { blob: file, name: file.name };
  return { blob, name: file.name.replace(/\.[^.]+$/, "") + ".jpg" };
}

/** Pasted screenshots arrive nameless ("image.png"); give them a readable one. */
export function pastedName(file: File, index: number): string {
  if (file.name && file.name !== "image.png") return file.name;
  const stamp = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }).replace(":", "h");
  return `print-${stamp}${index ? `-${index + 1}` : ""}.png`;
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}

const blobUrls = new Map<string, Promise<string>>();

/** One object URL per attachment for the whole session: scrolling back never re-downloads. */
export function attachmentUrl(id: string, load: (id: string) => Promise<Blob>): Promise<string> {
  let url = blobUrls.get(id);
  if (!url) {
    url = load(id).then((blob) => URL.createObjectURL(blob));
    url.catch(() => blobUrls.delete(id));
    blobUrls.set(id, url);
  }
  return url;
}
