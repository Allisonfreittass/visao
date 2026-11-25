import { describe, expect, it } from "vitest";

import { MARKS, T, T_CURTA, flash, flashOf, gapFlash, litHour, markProgress, revealProgress, strokeProgress, strokeStart, thinkingBoost } from "./genesis.logic";

describe("genesis timeline", () => {
  it("draws the strokes in order between 0.4 s and 6.4 s", () => {
    const n = 1965;
    expect(strokeStart(0, n)).toBeCloseTo(0.4);
    expect(strokeStart(n - 1, n) + T.strokeDur).toBeCloseTo(6.4);
    expect(strokeProgress(0.3, 0, n)).toBe(0);
    expect(strokeProgress(6.4, n - 1, n)).toBeCloseTo(1);
  });

  it("reveals the illustration from 6.2 s to 8.4 s", () => {
    expect(revealProgress(6.2)).toBe(0);
    expect(revealProgress(8.4)).toBe(1);
  });

  it("closes the ring from the gap, mark by mark, and never draws the gap", () => {
    expect(markProgress(T.total, 0)).toBe(0);
    for (let h = 1; h < MARKS; h++) expect(markProgress(T.total, h)).toBe(1);
    expect(markProgress(T.ringStart, 2)).toBe(0);
  });

  it("flashes the gap only after the ring has closed, then leaves it empty", () => {
    expect(gapFlash(flash.start - 0.01)).toBe(0);
    expect(gapFlash(flash.start + flash.dur / 4)).toBeGreaterThan(0.9);
    expect(gapFlash(T.total)).toBe(0);
    expect(flash.start + flash.dur).toBeLessThan(T.total);
  });
});

describe("ring at rest", () => {
  it("lights the current hour, and nothing at midnight (the gap)", () => {
    expect(litHour(new Date(2026, 10, 23, 14, 30))).toBe(14);
    expect(litHour(new Date(2026, 10, 23, 0, 30))).toBeNull();
  });

  it("runs a trace with a fading tail while thinking", () => {
    const head = 6;
    const s = (head / MARKS) * 1.6;
    expect(thinkingBoost(6, s)).toBeCloseTo(1);
    expect(thinkingBoost(4, s)).toBeGreaterThan(0);
    expect(thinkingBoost(10, s)).toBe(0);
  });
});

describe("short genesis (the opening after login)", () => {
  it("tells the same story, in order, before the name is typed at 1.5 s", () => {
    const n = 1965;
    expect(strokeStart(n - 1, n, T_CURTA) + T_CURTA.strokeDur).toBeCloseTo(T_CURTA.strokesEnd);
    expect(T_CURTA.strokesEnd).toBeLessThan(T_CURTA.revealEnd);
    expect(T_CURTA.eyeAt).toBeLessThan(T_CURTA.ringStart);
    for (let h = 1; h < MARKS; h++) expect(markProgress(1.5, h, T_CURTA)).toBe(1);
    const f = flashOf(T_CURTA);
    expect(f.start).toBeLessThan(1.5);
    expect(f.start + f.dur).toBeLessThanOrEqual(T_CURTA.total);
    expect(gapFlash(T_CURTA.total, T_CURTA)).toBe(0);
  });

  it("leaves the full genesis unchanged", () => {
    expect(flashOf(T)).toEqual(flash);
    expect(revealProgress(6.2)).toBe(revealProgress(6.2, T));
  });
});
