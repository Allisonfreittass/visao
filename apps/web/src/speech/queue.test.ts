import { describe, expect, it } from "vitest";

import { speakSentences } from "./queue";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe("speakSentences", () => {
  it("plays in order and prefetches the next sentence while playing", async () => {
    const log: string[] = [];
    const outcome = await speakSentences(["a", "b", "c"], {
      signal: new AbortController().signal,
      synthesize: async (s) => {
        log.push(`synth:${s}`);
        return s;
      },
      play: async (clip) => {
        log.push(`play:${clip}`);
      },
    });
    expect(outcome).toBe("completed");
    // b is requested before a is played: synthesis overlaps playback.
    expect(log).toEqual(["synth:a", "synth:b", "play:a", "synth:c", "play:b", "play:c"]);
  });

  it("stops when aborted mid-playback", async () => {
    const controller = new AbortController();
    const played: string[] = [];
    const gate = deferred<void>();
    const run = speakSentences(["a", "b"], {
      signal: controller.signal,
      synthesize: async (s) => s,
      play: async (clip) => {
        played.push(clip);
        if (clip === "a") await gate.promise;
      },
    });
    await Promise.resolve();
    await Promise.resolve();
    controller.abort();
    gate.resolve();
    expect(await run).toBe("aborted");
    expect(played).toEqual(["a"]);
  });

  it("propagates synthesis errors when not aborted", async () => {
    await expect(
      speakSentences(["a"], {
        signal: new AbortController().signal,
        synthesize: async () => {
          throw new Error("tts caiu");
        },
        play: async () => undefined,
      }),
    ).rejects.toThrow("tts caiu");
  });

  it("does nothing for an empty reply", async () => {
    expect(
      await speakSentences([], {
        signal: new AbortController().signal,
        synthesize: async (s) => s,
        play: async () => undefined,
      }),
    ).toBe("completed");
  });
});
