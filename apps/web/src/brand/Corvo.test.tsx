import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CORVO_ALT, Corvo, corvoSrc } from "./Corvo";

describe("Corvo", () => {
  it("uses the close crop up to 48 px and the whole icon above", () => {
    expect(corvoSrc(16)).toBe("/marca/corvo-olho-pequeno.svg");
    expect(corvoSrc(48)).toBe("/marca/corvo-olho-pequeno.svg");
    expect(corvoSrc(49)).toBe("/marca/corvo-olho.svg");
    expect(corvoSrc(380)).toBe("/marca/corvo-olho.svg");
  });

  it("is decorative unless it has a label", () => {
    expect(renderToStaticMarkup(<Corvo size={30} />)).toContain('aria-hidden="true"');
    const named = renderToStaticMarkup(<Corvo size={92} label={CORVO_ALT} />);
    expect(named).toContain('alt="O corvo do VISAO, de olho âmbar"');
    expect(named).not.toContain("aria-hidden");
  });
});
