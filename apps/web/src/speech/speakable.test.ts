import { describe, expect, it } from "vitest";

import { pickVoice } from "../voice/browser";
import { speakableText } from "./speakable";

describe("speakableText", () => {
  it("says code is on screen instead of reading it", () => {
    const text = "Assim:\n\n```ts\nconst a = 1;\n```\n\n```py\nb = 2\n```\n\nPronto.";
    expect(speakableText(text)).toBe("Assim:\nDeixei o código na tela. Pronto.");
  });

  it("keeps link text and drops markdown marks", () => {
    expect(speakableText("Veja **isto** em [MDN](https://developer.mozilla.org) e `fetch`."))
      .toBe("Veja isto em MDN e fetch.");
  });

  it("does not read raw URLs", () => {
    expect(speakableText("Fonte: https://pt.wikipedia.org/wiki/X")).toBe("Fonte: o link na tela");
  });
});

describe("pickVoice", () => {
  const voice = (lang: string, localService: boolean, name = lang) =>
    ({ lang, localService, name }) as SpeechSynthesisVoice;

  it("prefers a Brazilian voice on the device", () => {
    const chosen = pickVoice([voice("en-US", true), voice("pt-BR", false, "net"), voice("pt-BR", true, "local")]);
    expect(chosen?.name).toBe("local");
  });

  it("falls back to any Portuguese voice, then to none", () => {
    expect(pickVoice([voice("pt-PT", true)])?.lang).toBe("pt-PT");
    expect(pickVoice([voice("en-US", true)])).toBeNull();
  });
});
