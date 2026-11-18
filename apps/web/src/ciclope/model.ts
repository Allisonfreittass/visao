// Pure model of the Ciclope: the pose of each state, the blink, the springs. Rendering lives in
// Ciclope.tsx; everything here is deterministic and unit-tested. Units are the SVG's viewBox
// (0..100), so "5px" of iris travel means 5 of 100.
import type { CiclopeState } from "./state";

export interface Pose {
  /** Iris offset from its resting place. */
  irisX: number;
  irisY: number;
  /** Iris radius scale (1 = r 11.5). */
  iris: number;
  /** Pupil scale (1 = r 5). */
  pupil: number;
  /** Eyelid: 0 open, 1 closed. */
  lid: number;
  /** Eyelid tilt in degrees (a drooping brow when sad). */
  lidTilt: number;
  /** Eye (sclera) scale: wide open when listening. */
  sclera: number;
  /** Desaturation of the body, 0..1 (offline is 0.6, i.e. 40% saturation). */
  gray: number;
  /** The thin orange ring around the body while working, 0..1. */
  ring: number;
  /** The mouth's curve: 1 a smile, negative a frown. */
  smile: number;
}

export const RESTING: Pose = { irisX: 0, irisY: 0, iris: 1, pupil: 1, lid: 0, lidTilt: 0, sclera: 1, gray: 0, ring: 0, smile: 1 };

export const POSES: Record<CiclopeState, Pose> = {
  idle: RESTING,
  listening: { ...RESTING, sclera: 1.06, pupil: 1.05 },
  thinking: { ...RESTING, irisX: 2, irisY: -6, lid: 0.2 },
  speaking: { ...RESTING, iris: 10.5 / 11.5 },
  working: { ...RESTING, lid: 0.35, ring: 1 },
  error: { ...RESTING, irisX: -1, irisY: 3, lid: 0.4, lidTilt: -18, smile: -0.8 },
  offline: { ...RESTING, lid: 1, gray: 0.6, smile: 0.5 },
  interrupted: { ...RESTING, sclera: 1.06, pupil: 1.05 },
};

/** Largest iris travel when following a point. */
export const LOOK_MAX = 5;
/** Iris travel while wandering at rest. */
export const WANDER_MAX = 3;
/** Blink: close fast, open a bit slower (ms). */
export const BLINK_CLOSE_MS = 120;
export const BLINK_OPEN_MS = 160;
export const BLINK_MS = BLINK_CLOSE_MS + BLINK_OPEN_MS;

/** How closed the lid is, `ms` after a blink started (0 open … 1 closed … 0 open). */
export function blinkAmount(ms: number): number {
  if (ms < 0 || ms >= BLINK_MS) return 0;
  if (ms < BLINK_CLOSE_MS) return ms / BLINK_CLOSE_MS;
  return 1 - (ms - BLINK_CLOSE_MS) / BLINK_OPEN_MS;
}

/** Next blink in 3–6 s; `random` in 0..1. */
export function nextBlinkDelay(random: number): number {
  return 3000 + 3000 * random;
}

/** Eases a pose toward its target: about 240 ms to settle, whatever the frame rate. */
export function approach(current: Pose, target: Pose, dt: number): Pose {
  const a = 1 - Math.exp(-dt / 0.06);
  const out = { ...current };
  for (const key of Object.keys(target) as (keyof Pose)[]) out[key] = current[key] + (target[key] - current[key]) * a;
  return out;
}

export interface Spring {
  x: number;
  v: number;
}

/** One step of a damped spring toward `target` (stiffness 170, damping 22, mass 1). */
export function springStep(s: Spring, target: number, dt: number, stiffness = 170, damping = 22): Spring {
  let { x, v } = s;
  // Small substeps keep it stable at low frame rates.
  const steps = Math.max(1, Math.ceil(dt / (1 / 120)));
  const h = dt / steps;
  for (let i = 0; i < steps; i++) {
    const a = -stiffness * (x - target) - damping * v;
    v += a * h;
    x += v * h;
  }
  return { x, v };
}

/** Where the iris looks for a point `dx, dy` pixels from the eye's center: towards it, up to
 * LOOK_MAX, less when the point is close. */
export function lookOffset(dx: number, dy: number, size: number): { x: number; y: number } {
  const distance = Math.hypot(dx, dy);
  if (distance < 1) return { x: 0, y: 0 };
  const reach = Math.min(LOOK_MAX, (distance / Math.max(size, 1)) * LOOK_MAX);
  return { x: (dx / distance) * reach, y: (dy / distance) * reach };
}

/** A short shake (±2, three times, once) for `error`: 0 after 360 ms. */
export function shake(ms: number): number {
  if (ms < 0 || ms >= 360) return 0;
  return 2 * Math.sin((ms / 120) * Math.PI * 2) * (1 - ms / 360);
}

/** Breathing for `listening`: scale 1 → 1.03 → 1 every 1.2 s. */
export function breathe(seconds: number): number {
  return 1 + 0.015 * (1 - Math.cos((seconds / 1.2) * Math.PI * 2));
}

/** What the voice level does to the pose (listening: the pupil dilates; speaking: the iris
 * grows 10.5 → 12.5 and the mouth opens). */
export function withLevel(pose: Pose, state: CiclopeState, level: number): { pose: Pose; mouth: number } {
  const l = Math.max(0, Math.min(1, level));
  if (state === "speaking") return { pose: { ...pose, iris: (10.5 + 2 * l) / 11.5 }, mouth: l };
  if (state === "listening" || state === "interrupted") return { pose: { ...pose, pupil: pose.pupil + 0.5 * l }, mouth: 0 };
  return { pose, mouth: 0 };
}

/** Stable 0..1 from a string (a project's name), for its color. */
export function hash01(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 10_000) / 10_000;
}
