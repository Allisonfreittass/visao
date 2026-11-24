import { describe, expect, it } from "vitest";

import type { Message } from "../api";
import { conversationMarkdown, slug } from "./ShareDialog";

describe("share", () => {
  it("names the file after the title", () => {
    expect(slug("Debounce na busca")).toBe("debounce-na-busca");
    expect(slug("Viagem à Lisboa!")).toBe("viagem-a-lisboa");
    expect(slug("   ")).toBe("conversa");
  });

  it("writes who spoke and the text, skipping what was not sent", () => {
    const messages: Message[] = [
      { id: "1", role: "user", content: "Oi", created_at: "2026-11-24T12:00:00Z" },
      { id: "2", role: "assistant", content: "Olá", created_at: "2026-11-24T12:00:05Z" },
      { id: "3", role: "user", content: "não foi", created_at: "2026-11-24T12:01:00Z", local: "failed" },
    ];
    const md = conversationMarkdown("Teste", messages, null);
    expect(md.startsWith("# Teste\n")).toBe(true);
    expect(md).toContain("**Você** ·");
    expect(md).toContain("**Visão** ·");
    expect(md).toContain("Olá");
    expect(md).not.toContain("não foi");
  });
});
