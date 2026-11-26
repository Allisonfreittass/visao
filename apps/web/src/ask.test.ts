import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.tsx?$/.test(name) && !/\.test\./.test(name) && name !== "ask.ts" ? [path] : [];
  });
}

describe("confirmações", () => {
  // The Mac app's window (Tauri, macOS WebKit) shows no native confirm or prompt: they answer
  // "cancel" at once, and "Desconectar o Google" did nothing (25/11/2026). src/ask.ts draws them.
  it("never use the browser's native confirm, prompt or alert", () => {
    const found = sources(join(__dirname)).filter((path) =>
      /\bwindow\.(confirm|prompt|alert)\s*\(|(?<![\w.])(confirm|prompt|alert)\s*\(\s*[`"']/.test(readFileSync(path, "utf8")),
    );
    expect(found).toEqual([]);
  });
});
