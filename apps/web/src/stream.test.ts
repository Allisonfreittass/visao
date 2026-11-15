import { describe, expect, it } from "vitest";

import { commonPrefix, followTurn, revealStep, SseParser, type StreamEvent } from "./stream";

describe("SseParser", () => {
  it("reads events split across chunks, with ids and JSON data", () => {
    const parser = new SseParser();
    expect(parser.push("retry: 2000\n\nid: 7\nevent: delta\nda")).toEqual([]);
    expect(parser.push('ta: {"text":"Oi"}\n\n')).toEqual([{ id: 7, kind: "delta", data: { text: "Oi" } }]);
    expect(parser.lastId).toBe(7);
  });

  it("joins several data lines and ignores comments", () => {
    const parser = new SseParser();
    const events = parser.push(": aqui\r\nevent: x\r\ndata: um\r\ndata: dois\r\n\r\n");
    expect(events).toEqual([{ id: null, kind: "x", data: "um\ndois" }]);
  });

  it("an event without a name is a message", () => {
    expect(new SseParser().push("data: 1\n\n")).toEqual([{ id: null, kind: "message", data: 1 }]);
  });
});

function body(chunks: string[], fail = false): Response {
  const enc = new TextEncoder();
  let next = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (next < chunks.length) controller.enqueue(enc.encode(chunks[next++]));
      else if (fail) controller.error(new Error("rede caiu"));
      else controller.close();
    },
  });
  return new Response(stream, { headers: { "Content-Type": "text/event-stream" } });
}

describe("followTurn", () => {
  it("resumes after a drop with the last id seen", async () => {
    const asked: Array<number | null> = [];
    const responses = [
      body(['id: 1\nevent: delta\ndata: {"text":"Cam"}\n\n'], true),
      body(['id: 2\nevent: delta\ndata: {"text":"berra"}\n\nid: 3\nevent: done\ndata: {}\n\n']),
    ];
    const seen: StreamEvent[] = [];
    const end = await followTurn(
      async (last) => {
        asked.push(last);
        return responses.shift()!;
      },
      (e) => seen.push(e),
      new AbortController().signal,
    );
    expect(end).toBe("done");
    expect(asked).toEqual([null, 1]);
    expect(seen.map((e) => e.id)).toEqual([1, 2, 3]);
  });

  it("is empty when the server had no turn, and throws when it cannot open at all", async () => {
    expect(await followTurn(async () => body(["retry: 2000\n\n"]), () => undefined, new AbortController().signal)).toBe("empty");
    await expect(
      followTurn(async () => { throw new Error("404"); }, () => undefined, new AbortController().signal),
    ).rejects.toThrow("404");
  });
});

describe("reveal", () => {
  it("goes at a steady pace and speeds up to stay about a second behind", () => {
    expect(revealStep(0, 100, 0.1)).toBeCloseTo(10); // 100 behind: 100/s
    expect(revealStep(0, 20, 0.1)).toBeCloseTo(4.5); // little behind: 45/s
    expect(revealStep(18, 20, 1)).toBe(20);
  });

  it("keeps what a replace did not change", () => {
    expect(commonPrefix("Fica em Camberra. Quer?", "Fica em Camberra.")).toBe(17);
  });
});
