import { describe, expect, it } from "vitest";

// Every source file of the app, as text (Vite reads them at test time).
const files = import.meta.glob(["./**/*.ts", "./**/*.tsx", "!./**/*.test.*", "!./ask.ts"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("confirmações", () => {
  // The Mac app's window (Tauri, macOS WebKit) shows no native confirm or prompt: they answer
  // "cancel" at once, and "Desconectar o Google" did nothing (25/11/2026). src/ask.ts draws them.
  it("never use the browser's native confirm, prompt or alert", () => {
    expect(Object.keys(files).length).toBeGreaterThan(20);
    const found = Object.entries(files)
      .filter(([, text]) => /\bwindow\.(confirm|prompt|alert)\s*\(|(?<![\w.])(confirm|prompt|alert)\s*\(\s*[`"']/.test(text))
      .map(([path]) => path);
    expect(found).toEqual([]);
  });
});
