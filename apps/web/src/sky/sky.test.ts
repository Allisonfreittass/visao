import { describe, expect, it } from "vitest";

import { cssGradient, lookAt, SHADER_SOURCES } from "./sky";

describe("the forest follows the local hour", () => {
  it("is night at midnight and day at noon", () => {
    expect(lookAt(0).night).toBe(1);
    expect(lookAt(12).night).toBe(0);
    expect(lookAt(23.9).night).toBeGreaterThan(0.9);
  });

  it("puts the light high at noon and low at dawn, behind the fog", () => {
    expect(lookAt(12).sun[1]).toBeGreaterThan(0.85);
    expect(lookAt(6.2).sun[1]).toBeLessThan(0.65);
  });

  it("keeps the nearest pines dark at every hour", () => {
    for (let h = 0; h < 24; h += 1) {
      expect(Math.max(...lookAt(h).tree)).toBeLessThanOrEqual(0.21);
    }
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

describe("the shaders", () => {
  // GLSL ES 1.0 reserves these for the future; a variable with one of these names fails to compile.
  const RESERVED = ["half", "fixed", "input", "output", "filter", "sample", "long", "short", "double", "unsigned", "inline", "namespace", "class", "union", "enum", "cast", "goto", "public", "static", "extern", "external", "interface", "superp", "sizeof", "typedef", "template", "this", "packed", "asm", "noinline", "volatile", "default", "switch"];

  it("never name a variable with a reserved word", () => {
    for (const source of Object.values(SHADER_SOURCES)) {
      for (const word of RESERVED) {
        expect(source).not.toMatch(new RegExp(`\\b(?:float|int|bool|vec[234]|mat[234])\\s+${word}\\b`));
      }
    }
  });
});
