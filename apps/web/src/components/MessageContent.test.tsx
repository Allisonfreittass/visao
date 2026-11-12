import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MessageContent } from "./MessageContent";
import { utcDate } from "../api";

describe("MessageContent", () => {
  it("formats useful Markdown while escaping HTML and executable links", () => {
    const html = renderToStaticMarkup(<MessageContent text={"**Nome**\n\n- Uma ideia\n- Outra ideia\n\n<script>alert(1)</script>\n\n[teste](javascript:alert(1))\n\n[fonte](https://example.com)"} />);
    expect(html).toContain("<strong>Nome</strong>");
    expect(html).toContain("<li>Uma ideia</li>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('href="javascript:');
    expect(html).toContain('href="https://example.com"');
    expect(html).toContain('rel="noopener noreferrer"');
  });
  it("keeps code escaped and preserves line breaks", () => {
    const html = renderToStaticMarkup(<MessageContent text={"```html\n<img onerror='alert(1)'>\n```"} />);
    expect(html).toContain("<pre><code>&lt;img");
    expect(html).not.toContain("<img");
  });
});

describe("UTC timestamps", () => {
  it("interprets old offset-free API dates as UTC", () => {
    expect(utcDate("2026-10-31T14:39:00").getTime()).toBe(Date.UTC(2026, 9, 31, 14, 39));
    expect(utcDate("2026-10-31T14:39:00Z").getTime()).toBe(Date.UTC(2026, 9, 31, 14, 39));
  });
});

describe("code blocks", () => {
  it("label the language, offer a copy button and survive a reply cut mid-block", () => {
    const html = renderToStaticMarkup(<MessageContent text={"Assim:\n\n```TypeScript\nconst a = 1;\n```\n\nE o resto:\n\n```py\nprint(1)"} />);
    expect(html).toContain("<span>typescript</span>");
    expect(html).toContain("Copiar");
    expect(html).toContain("<pre><code>const a = 1;</code></pre>");
    expect(html).toContain("<pre><code>print(1)</code></pre>");
    expect(html).not.toContain("```");
  });
});
