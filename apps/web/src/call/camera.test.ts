import { describe, expect, it } from "vitest";

import { fitWithin, MAX_SIDE } from "./camera";

describe("fitWithin", () => {
  it("shrinks the long side to the limit, keeping the shape", () => {
    expect(fitWithin(1920, 1080)).toEqual({ width: MAX_SIDE, height: 882 });
    expect(fitWithin(1080, 1920)).toEqual({ width: 882, height: MAX_SIDE });
  });

  it("never enlarges a small picture", () => {
    expect(fitWithin(640, 480)).toEqual({ width: 640, height: 480 });
    expect(fitWithin(0, 0)).toEqual({ width: 0, height: 0 });
  });
});
