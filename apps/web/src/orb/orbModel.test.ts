import { describe, expect, it } from "vitest";

import {
  STATE_PARAMS,
  fibonacciSphere,
  hash01,
  organicSphere,
  lerpParams,
  coreIntensity,
  particleColor,
  particleRadius,
  reducedMotion,
  smoothingFactor,
} from "./orbModel";

describe("orb model", () => {
  it("spreads points on the unit sphere", () => {
    const points = fibonacciSphere(500);
    expect(points).toHaveLength(500);
    for (const [x, y, z] of points) expect(Math.hypot(x, y, z)).toBeCloseTo(1, 6);
    const meanY = points.reduce((sum, p) => sum + p[1], 0) / points.length;
    expect(Math.abs(meanY)).toBeLessThan(1e-9);
  });

  it("jitters the lattice deterministically while staying on the sphere", () => {
    const a = organicSphere(200);
    expect(a).toEqual(organicSphere(200));
    expect(a).not.toEqual(fibonacciSphere(200));
    for (const [x, y, z] of a) expect(Math.hypot(x, y, z)).toBeCloseTo(1, 6);
    for (let i = 0; i < 100; i++) expect(hash01(i)).toBeGreaterThanOrEqual(0);
  });

  it("interpolates parameters and clamps t", () => {
    const { IDLE, THINKING } = STATE_PARAMS;
    expect(lerpParams(IDLE, THINKING, 0)).toEqual(IDLE);
    expect(lerpParams(IDLE, THINKING, 1)).toEqual(THINKING);
    expect(lerpParams(IDLE, THINKING, 5)).toEqual(THINKING);
    const half = lerpParams(IDLE, THINKING, 0.5);
    expect(half.rotationSpeed).toBeCloseTo((IDLE.rotationSpeed + THINKING.rotationSpeed) / 2);
  });

  it("smooths independently of frame rate", () => {
    // Two 1/120 s steps must land where one 1/60 s step does.
    const twoSteps = 1 - (1 - smoothingFactor(1 / 120)) ** 2;
    expect(twoSteps).toBeCloseTo(smoothingFactor(1 / 60), 10);
  });

  it("reacts to audio level only in voice states", () => {
    const quiet = particleRadius(STATE_PARAMS.SPEAKING, 3, 1, 0);
    const loud = particleRadius(STATE_PARAMS.SPEAKING, 3, 1, 1);
    expect(loud).toBeGreaterThan(quiet);
    expect(particleRadius(STATE_PARAMS.IDLE, 3, 1, 1)).toBe(particleRadius(STATE_PARAMS.IDLE, 3, 1, 0));
  });

  it("is still and gray when disconnected", () => {
    const p = STATE_PARAMS.DISCONNECTED;
    expect(particleRadius(p, 1, 0.3, 1)).toBe(particleRadius(p, 2, 9.1, 0));
    expect(particleColor(p, 1)).toMatch(/^hsla\(184, 0%,/);
    expect(particleColor(STATE_PARAMS.IDLE, 1)).toMatch(/^hsla\(184, 14%,/);
    expect(coreIntensity(p, 1)).toBe(0);
    expect(coreIntensity(STATE_PARAMS.SPEAKING, 1)).toBeGreaterThan(coreIntensity(STATE_PARAMS.SPEAKING, 0));
  });

  it("calms motion for reduced-motion users", () => {
    const calm = reducedMotion(STATE_PARAMS.THINKING);
    expect(calm.rotationSpeed).toBeLessThan(STATE_PARAMS.THINKING.rotationSpeed);
    expect(calm.turbulence).toBeLessThan(STATE_PARAMS.THINKING.turbulence);
  });
});
