import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Anel } from "./Anel";

const at = (size: number) => renderToStaticMarkup(<Anel estado="ocioso" size={size} decorative />);
const count = (html: string, cls: string) => (html.match(new RegExp(`class="${cls}[" ]`, "g")) ?? []).length;

describe("<Anel> by size", () => {
  it("below 32 px draws the thin circle and no Muninn", () => {
    const html = at(28);
    expect(html).toContain("anel--mini");
    expect(html).toContain("anel-contorno");
    expect(html).not.toContain("anel-muninn");
  });

  it("from 32 to 120 px draws the 23 marks alone, no circle, no Muninn", () => {
    for (const size of [32, 120]) {
      const html = at(size);
      expect(html).not.toContain("anel--mini");
      expect(html).not.toContain("anel-contorno");
      expect(html).not.toContain("anel-muninn");
      expect(count(html, "anel-marca")).toBe(23);
    }
  });

  it("above 120 px holds Muninn, with his eye apart from the dot", () => {
    const html = at(121);
    expect(html).toContain("anel--muninn");
    expect(html).toContain("/muninn/muninn-720.webp");
    expect(html).toContain("anel-olho");
    expect(html).toContain("anel-ponto");
  });

  it("names its state for screen readers unless it is decorative", () => {
    expect(renderToStaticMarkup(<Anel estado="aprovacao" size={36} />)).toContain('aria-label="V.I.S.A.O., esperando seu sim"');
    expect(at(36)).toContain('aria-hidden="true"');
  });
});

describe("<Anel vazio>", () => {
  it("keeps the ring of Muninn's size but leaves him and his eye to whoever draws them", () => {
    const html = renderToStaticMarkup(<Anel estado="pensando" size={220} decorative vazio />);
    expect(html).toContain("anel--muninn");
    expect(html).not.toContain("anel-muninn\"");
    expect(html).not.toContain("anel-olho");
    expect(count(html, "anel-marca")).toBe(23);
  });
});
