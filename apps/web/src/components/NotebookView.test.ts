import { describe, expect, it } from "vitest";

import { memoryOrigin, warmth } from "./NotebookView";

describe("Caderno", () => {
  it("says where a memory came from", () => {
    expect(memoryOrigin({ type: "preference", created_at: "2026-11-23T12:00:00Z", source_message_ids: ["a"] })).toBe("preferência · 23/11 · de 1 mensagem da conversa");
    expect(memoryOrigin({ type: "fact", created_at: "2026-11-23T12:00:00Z", source_message_ids: [] })).toBe("fato · 23/11 · guardado sem mensagem de origem");
  });

  it("names how warm an interest is", () => {
    expect(warmth(0.9)).toBe("quente");
    expect(warmth(0.5)).toBe("morno");
    expect(warmth(0.1)).toBe("esfriando");
  });
});
