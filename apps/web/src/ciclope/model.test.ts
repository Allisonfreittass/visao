import { describe, expect, it } from "vitest";

import {
  BLINK_MS,
  LOOK_MAX,
  POSES,
  RESTING,
  approach,
  blinkAmount,
  breathe,
  hash01,
  lookOffset,
  nextBlinkDelay,
  shake,
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
  it("closes the eye when offline and looks up when thinking", () => {
    expect(POSES.offline.lid).toBe(1);
    expect(POSES.offline.gray).toBeCloseTo(0.6);
    expect(POSES.thinking.irisY).toBeLessThan(0);
    expect(POSES.working.ring).toBe(1);
    expect(POSES.listening.sclera).toBeCloseTo(1.06);
  });

  it("settles in about 240 ms", () => {
    let pose = RESTING;
    for (let t = 0; t < 0.24; t += 1 / 60) pose = approach(pose, POSES.offline, 1 / 60);
    expect(pose.lid).toBeGreaterThan(0.95);
  });
});

describe("blink", () => {
  it("closes in 120 ms and opens in 160 ms", () => {
    expect(blinkAmount(0)).toBe(0);
    expect(blinkAmount(120)).toBeCloseTo(1);
    expect(blinkAmount(200)).toBeCloseTo(0.5);
    expect(blinkAmount(BLINK_MS)).toBe(0);
  });

  it("comes every 3 to 6 seconds", () => {
    expect(nextBlinkDelay(0)).toBe(3000);
    expect(nextBlinkDelay(1)).toBe(6000);
  });
});

describe("motion", () => {
  it("springs to the target without blowing up", () => {
    let s = { x: 0, v: 0 };
    for (let i = 0; i < 120; i++) s = springStep(s, 5, 1 / 60);
    expect(s.x).toBeCloseTo(5, 1);
    s = springStep({ x: 0, v: 0 }, 5, 0.5);
    expect(Number.isFinite(s.x)).toBe(true);
  });

  it("never looks further than 5", () => {
    const far = lookOffset(1000, 0, 96);
    expect(far.x).toBeCloseTo(LOOK_MAX);
    expect(Math.hypot(lookOffset(300, -400, 96).x, lookOffset(300, -400, 96).y)).toBeLessThanOrEqual(LOOK_MAX + 1e-9);
    expect(lookOffset(0, 0, 96)).toEqual({ x: 0, y: 0 });
  });

  it("shakes once and breathes up to 3%", () => {
    expect(shake(400)).toBe(0);
    expect(Math.abs(shake(30))).toBeLessThanOrEqual(2);
    expect(breathe(0)).toBe(1);
    expect(breathe(0.6)).toBeCloseTo(1.03);
  });

  it("lets the voice grow the iris when speaking", () => {
    expect(withLevel(POSES.speaking, "speaking", 0).pose.iris).toBeCloseTo(10.5 / 11.5);
    expect(withLevel(POSES.speaking, "speaking", 1).pose.iris).toBeCloseTo(12.5 / 11.5);
    expect(withLevel(POSES.speaking, "speaking", 1).mouth).toBe(1);
    expect(withLevel(POSES.listening, "listening", 1).pose.pupil).toBeGreaterThan(POSES.listening.pupil);
    expect(withLevel(POSES.idle, "idle", 1).pose).toEqual(POSES.idle);
  });

  it("gives each name a stable color slot", () => {
    expect(hash01("Viagem")).toBe(hash01("Viagem"));
    expect(hash01("Viagem")).toBeGreaterThanOrEqual(0);
    expect(hash01("Viagem")).toBeLessThan(1);
  });
});
