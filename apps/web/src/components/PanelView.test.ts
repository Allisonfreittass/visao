import { describe, expect, it } from "vitest";

import { chartGeometry } from "./PanelView";

describe("panel chart", () => {
  it("needs two checks", () => {
    expect(chartGeometry([{ total: "3420" }], null)).toBeNull();
    expect(chartGeometry([{ total: null }, { total: "3420" }], null)).toBeNull();
  });

  it("falls from the top-left and puts the goal inside the range", () => {
    const geo = chartGeometry([{ total: "3620" }, { total: "3420" }], "3200")!;
    expect(geo.first).toBe(3620);
    expect(geo.last).toBe(3420);
    const [a, b] = geo.points.split(" ").map((p) => Number(p.split(",")[1]));
    expect(a).toBeLessThan(b);
    expect(geo.goalY).toBe(140);
  });
});
