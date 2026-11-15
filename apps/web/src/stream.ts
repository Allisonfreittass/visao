// The reply as it is written (docs/decisions/0011): server-sent events read with fetch, since
// EventSource cannot send the Authorization header. A dropped connection resumes after the last
// event seen (Last-Event-ID); if the stream cannot be had at all, the caller polls /progress.

export interface StreamEvent {
  id: number | null;
  kind: string;
  data: unknown;
}

/** text/event-stream, a chunk at a time: lines, events of several data lines, comments. */
export class SseParser {
  private buffer = "";
  private id: number | null = null;
  private kind = "";
  private data: string[] = [];
  lastId: number | null = null;

  push(chunk: string): StreamEvent[] {
    this.buffer += chunk;
    const out: StreamEvent[] = [];
    let newline: number;
    while ((newline = this.buffer.search(/\r\n|\r|\n/)) >= 0) {
      const line = this.buffer.slice(0, newline);
      const width = this.buffer.startsWith("\r\n", newline) ? 2 : 1;
      this.buffer = this.buffer.slice(newline + width);
      if (line === "") {
        if (this.data.length > 0) {
          const raw = this.data.join("\n");
          let data: unknown = raw;
          try {
            data = JSON.parse(raw);
          } catch {
            // Not JSON: hand it over as text.
          }
          out.push({ id: this.id, kind: this.kind || "message", data });
          if (this.id !== null) this.lastId = this.id;
        }
        this.id = null;
        this.kind = "";
        this.data = [];
        continue;
      }
      if (line.startsWith(":")) continue; // a comment keeps the connection alive
      const colon = line.indexOf(":");
      const field = colon < 0 ? line : line.slice(0, colon);
      let value = colon < 0 ? "" : line.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "data") this.data.push(value);
      else if (field === "event") this.kind = value;
      else if (field === "id" && /^\d+$/.test(value)) this.id = Number(value);
    }
    return out;
  }
}

export type TurnEnd = "done" | "error" | "empty";

/** Opens the response of GET /conversations/{id}/stream (with auth); throws when unavailable. */
export type OpenStream = (lastEventId: number | null, signal: AbortSignal) => Promise<Response>;

const RETRIES = 3;
const RETRY_MS = 800;

/**
 * Follows the turn until `done` or `error`. Resumes up to 3 times after a drop. Resolves "empty"
 * when the server ended the stream without a turn; rejects when it could not be read at all
 * (the caller then polls /progress).
 */
export async function followTurn(open: OpenStream, onEvent: (event: StreamEvent) => void, signal: AbortSignal): Promise<TurnEnd> {
  const parser = new SseParser();
  let failures = 0;
  let seen = 0;
  for (;;) {
    let response: Response;
    try {
      response = await open(parser.lastId, signal);
      if (!response.body) throw new Error("sem corpo");
    } catch (e) {
      if (signal.aborted || ++failures > RETRIES || seen === 0) throw e;
      await new Promise((r) => setTimeout(r, RETRY_MS));
      continue;
    }
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let ended: TurnEnd | null = null;
    let dropped = false;
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        for (const event of parser.push(value)) {
          seen += 1;
          onEvent(event);
          if (event.kind === "done" || event.kind === "error") ended = event.kind;
        }
        if (ended) break;
      }
    } catch (e) {
      if (signal.aborted) throw e;
      // A drop in the middle: resume after the last event seen.
      dropped = true;
    } finally {
      reader.cancel().catch(() => undefined);
    }
    if (ended) return ended;
    if (seen === 0 && !dropped) return "empty";
    if (signal.aborted || ++failures > RETRIES) throw new Error("o stream caiu");
    await new Promise((r) => setTimeout(r, RETRY_MS));
  }
}

/** Characters per second the text comes in at, before it speeds up to catch up. */
export const REVEAL_CPS = 45;
/** It never falls further behind the server than this. */
export const REVEAL_MAX_LAG_S = 1;

/** How many characters of `target` to show after `dt` seconds, having shown `shown`. */
export function revealStep(shown: number, target: number, dt: number): number {
  if (shown >= target) return target;
  const behind = target - shown;
  const rate = Math.max(REVEAL_CPS, behind / REVEAL_MAX_LAG_S);
  return Math.min(target, shown + Math.max(1, rate * dt));
}

/** Where two texts stop agreeing (a `replace` keeps what was already right). */
export function commonPrefix(a: string, b: string): number {
  const n = Math.min(a.length, b.length);
  let i = 0;
  while (i < n && a.charCodeAt(i) === b.charCodeAt(i)) i += 1;
  return i;
}
