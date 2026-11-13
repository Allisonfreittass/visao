import { describe, expect, it } from "vitest";

import { cssGradient, lookAt } from "./sky";

describe("the sky follows the local hour", () => {
  it("is night at midnight and day at noon", () => {
    expect(lookAt(0).night).toBe(1);
    expect(lookAt(12).night).toBe(0);
    expect(lookAt(23.9).night).toBeGreaterThan(0.9);
  });

  it("puts the sun high at noon and low at dawn", () => {
    expect(lookAt(12).sun[1]).toBeGreaterThan(0.75);
    expect(lookAt(6.2).sun[1]).toBeLessThan(0.35);
  });

  it("blends between key hours without jumps", () => {
    for (let h = 0; h < 24; h += 0.25) {
      const a = lookAt(h);
      const b = lookAt(h + 0.25);
      a.top.forEach((v, i) => expect(Math.abs(v - b.top[i])).toBeLessThan(0.35));
      expect(Math.abs(a.night - b.night)).toBeLessThan(0.5);
    }
  });

  it("wraps hours past midnight", () => {
    expect(lookAt(25)).toEqual(lookAt(1));
    expect(lookAt(-1)).toEqual(lookAt(23));
  });

  it("has a CSS gradient for browsers without WebGL", () => {
    expect(cssGradient(lookAt(12))).toMatch(/^linear-gradient\(180deg, rgb\(/);
  });
});
