import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Corvo, corvoSrc } from "./Corvo";

describe("Corvo", () => {
  it("uses the small drawing up to 72 px and the large one above", () => {
    expect(corvoSrc(30)).toBe("/marca/corvo-256.png");
    expect(corvoSrc(72)).toBe("/marca/corvo-256.png");
    expect(corvoSrc(73)).toBe("/marca/corvo-512.png");
  });

  it("is decorative unless it has a label", () => {
    expect(renderToStaticMarkup(<Corvo size={30} />)).toContain('aria-hidden="true"');
    const named = renderToStaticMarkup(<Corvo size={92} label="VISAO" />);
    expect(named).toContain('alt="VISAO"');
    expect(named).not.toContain("aria-hidden");
  });
});
