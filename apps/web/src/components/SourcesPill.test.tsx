import { describe, expect, it } from "vitest";

import { sourcesLabel } from "./SourcesPill";

const at = "2026-11-15T13:14:00Z";

describe("sourcesLabel", () => {
  it("counts sources from a search", () => {
    expect(sourcesLabel([{ title: "a", url: "https://a.com", source: "web" }], at)).toBe("1 fonte");
    expect(
      sourcesLabel(
        [
          { title: "a", url: "https://a.com", source: "web" },
          { title: "b", url: "https://b.com", source: "Wikipédia" },
        ],
        at,
      ),
    ).toBe("2 fontes");
  });

  it("says a live price came from which site and when", () => {
    const label = sourcesLabel([{ title: "Google Voos", url: "https://www.google.com/travel/flights?q=x", source: "ao vivo" }], at);
    expect(label).toMatch(/^ao vivo · google\.com · \d\d:\d\d$/);
  });
});
