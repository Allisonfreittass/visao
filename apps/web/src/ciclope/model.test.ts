import { describe, expect, it } from "vitest";

import {
  BLINK_MS,
  LID_HIDDEN,
  LID_SHUT,
  LOOK_MAX,
  POSES,
  SLIT,
  approach,
  blinkAmount,
  errorFlicker,
  hash01,
  ledOpacity,
  lookOffset,
  mech,
  nextBlinkDelay,
  shake,
  shutBy,
  springStep,
  withLevel,
} from "./model";
import { ciclopeState } from "./state";

describe("ciclopeState", () => {
  it("follows the app's state", () => {
    expect(ciclopeState({ state: "DISCONNECTED" })).toBe("offline");
    expect(ciclopeState({ state: "LISTENING" })).toBe("listening");
    expect(ciclopeState({ state: "THINKING" })).toBe("thinking");
    expect(ciclopeState({ state: "SPEAKING" })).toBe("speaking");
    expect(ciclopeState({ state: "INTERRUPTED" })).toBe("interrupted");
    expect(ciclopeState({ state: "IDLE" })).toBe("idle");
  });

  it("shows the Mac at work and errors only when resting", () => {
    expect(ciclopeState({ state: "IDLE", macWorking: true })).toBe("working");
    expect(ciclopeState({ state: "IDLE", error: true })).toBe("error");
    expect(ciclopeState({ state: "THINKING", macWorking: true, error: true })).toBe("thinking");
    expect(ciclopeState({ state: "DISCONNECTED", macWorking: true })).toBe("offline");
  });
});

describe("poses", () => {
  it("has a flat lid at rest, a V at work and a deeper V failing", () => {
    expect(POSES.idle.lidSide).toBe(POSES.idle.lidMid);
    expect(POSES.working.lidMid).toBeGreaterThan(POSES.working.lidSide);
    expect(POSES.error.lidMid).toBeGreaterThan(POSES.working.lidMid);
    expect(POSES.listening.lidSide).toBeLessThan(POSES.idle.lidSide);
  });

  it("shuts and dims when offline", () => {
    expect(POSES.offline.lidMid).toBe(LID_SHUT);
    expect(POSES.offline.lowerLid).toBe(LID_SHUT);
    expect(POSES.offline.iris).toBeCloseTo(0.15);
    expect(POSES.offline.body).toBeCloseTo(0.7);
    expect(POSES.idle.lowerLid).toBe(LID_HIDDEN);
  });

  it("leaves a 6-unit slit for the password", () => {
    expect(SLIT.lowerLid - SLIT.lidMid).toBe(6);
  });

  it("settles in about 220 ms", () => {
    let pose = POSES.idle;
    for (let t = 0; t < 0.22; t += 1 / 60) pose = approach(pose, POSES.offline, 1 / 60);
    expect(LID_SHUT - pose.lidMid).toBeLessThan(1.2);
  });
});

describe("blink", () => {
  it("shuts in 90 ms, holds 60 ms and opens in 140 ms", () => {
    expect(blinkAmount(0)).toBeCloseTo(0);
    expect(blinkAmount(90)).toBeCloseTo(1);
    expect(blinkAmount(120)).toBe(1);
    expect(blinkAmount(BLINK_MS)).toBe(0);
    expect(BLINK_MS).toBe(290);
  });

  it("comes every 6 to 10 seconds", () => {
    expect(nextBlinkDelay(0)).toBe(6000);
    expect(nextBlinkDelay(1)).toBe(10000);
  });

  it("closes both lids", () => {
    const shut = shutBy(POSES.idle, 1);
    expect(shut.lidMid).toBe(LID_SHUT);
    expect(shut.lowerLid).toBe(LID_SHUT);
    expect(shutBy(POSES.idle, 0)).toEqual(POSES.idle);
  });

  it("eases mechanically", () => {
    expect(mech(0)).toBeCloseTo(0);
    expect(mech(1)).toBeCloseTo(1);
    expect(mech(0.25)).toBeLessThan(0.25);
  });
});

describe("motion", () => {
  it("springs dry to the target", () => {
    let s = { x: 0, v: 0 };
    for (let i = 0; i < 120; i++) s = springStep(s, 4, 1 / 60);
    expect(s.x).toBeCloseTo(4, 1);
    expect(Number.isFinite(springStep({ x: 0, v: 0 }, 4, 0.5).x)).toBe(true);
  });

  it("never looks further than 4", () => {
    expect(lookOffset(1000, 0, 96).x).toBeCloseTo(LOOK_MAX);
    const o = lookOffset(300, -400, 96);
    expect(Math.hypot(o.x, o.y)).toBeLessThanOrEqual(LOOK_MAX + 1e-9);
    expect(lookOffset(0, 0, 96)).toEqual({ x: 0, y: 0 });
  });

  it("trembles and flickers once when failing", () => {
    expect(shake(300)).toBe(0);
    expect(Math.abs(shake(25))).toBeLessThanOrEqual(1.5);
    expect(errorFlicker(0)).toBeLessThan(1);
    expect(errorFlicker(400)).toBe(1);
  });

  it("keeps the LED off offline and pulsing at rest", () => {
    expect(ledOpacity("offline", 1, false)).toBe(0);
    expect(ledOpacity("idle", 0, false)).toBeCloseTo(1);
    expect(ledOpacity("idle", 1.2, false)).toBeCloseTo(0.35);
    expect(ledOpacity("idle", 1.2, true)).toBe(1);
  });

  it("lets the voice move the eye and the grille", () => {
    expect(withLevel(POSES.speaking, "speaking", 1).pose.ring).toBeCloseTo(12 / 10.5);
    expect(withLevel(POSES.speaking, "speaking", 0.5).grille).toBe(0.5);
    expect(withLevel(POSES.listening, "listening", 1).pose.core).toBeCloseTo(6.5 / 4.5);
    expect(withLevel(POSES.listening, "listening", 1).pose.glow).toBeCloseTo(1);
    expect(withLevel(POSES.idle, "idle", 1).pose).toEqual(POSES.idle);
  });

  it("gives each name a stable color slot", () => {
    expect(hash01("Chile")).toBe(hash01("Chile"));
    expect(hash01("Chile")).toBeGreaterThanOrEqual(0);
    expect(hash01("Chile")).toBeLessThan(1);
  });
});
