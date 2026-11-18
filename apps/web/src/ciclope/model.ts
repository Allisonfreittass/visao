// Pure model of the mascot (Ciclope Sentinela): the pose of each state, the mechanical blink, the
// springs. Rendering lives in Ciclope.tsx; everything here is deterministic and unit-tested.
// Units are the SVG's (the body is the 0..100 box; the eye is the circle at 50,46 r 23).
import type { CiclopeState } from "./state";

export interface Pose {
  /** Upper lid: its y at the sides and at the middle (equal: flat; middle lower: an alert V). */
  lidSide: number;
  lidMid: number;
  /** Lower lid: the y of its top edge (LID_HIDDEN keeps it out of the eye). */
  lowerLid: number;
  /** Iris offset from its resting place. */
  irisX: number;
  irisY: number;
  /** Iris ring radius scale (1 = r 10.5). */
  ring: number;
  /** Core scale (1 = r 4.5). */
  core: number;
  /** The red glow behind the iris, 0..1. */
  glow: number;
  /** The whole iris, 0..1 (switched off when offline). */
  iris: number;
  /** The body's opacity (offline dims it to .7). */
  body: number;
  /** The outer red ring turning while working, 0..1. */
  outer: number;
}

/** The lower lid sits here when it is not in the eye. */
export const LID_HIDDEN = 76;
/** Where both lids meet when the eye is shut. */
export const LID_SHUT = 54;

const NEUTRAL: Pose = { lidSide: 35, lidMid: 35, lowerLid: LID_HIDDEN, irisX: 0, irisY: 0, ring: 1, core: 1, glow: 0.7, iris: 1, body: 1, outer: 0 };

export const POSES: Record<CiclopeState, Pose> = {
  idle: NEUTRAL,
  listening: { ...NEUTRAL, lidSide: 30, lidMid: 30 },
  thinking: { ...NEUTRAL, lidSide: 37, lidMid: 37, irisY: -4 },
  speaking: NEUTRAL,
  working: { ...NEUTRAL, lidSide: 37, lidMid: 47, glow: 1, outer: 1 },
  error: { ...NEUTRAL, lidSide: 37, lidMid: 50, glow: 1 },
  offline: { ...NEUTRAL, lidSide: LID_SHUT, lidMid: LID_SHUT, lowerLid: LID_SHUT, iris: 0.15, glow: 0, body: 0.7 },
  interrupted: { ...NEUTRAL, lidSide: 30, lidMid: 30 },
};

/** "Fresta": nearly shut, a 6-unit red slit left (the login while the password is typed). */
export const SLIT: Pick<Pose, "lidSide" | "lidMid" | "lowerLid"> = { lidSide: 51, lidMid: 51, lowerLid: 57 };

/** Largest iris travel when following a point. */
export const LOOK_MAX = 4;
/** Iris travel while looking around at rest. */
export const WANDER_MAX = 2;
/** Mechanical blink: shut in 90 ms, hold 60 ms, open in 140 ms. */
export const BLINK_CLOSE_MS = 90;
export const BLINK_HOLD_MS = 60;
export const BLINK_OPEN_MS = 140;
export const BLINK_MS = BLINK_CLOSE_MS + BLINK_HOLD_MS + BLINK_OPEN_MS;

/** The mechanical ease, cubic-bezier(.6, 0, .2, 1), as a function of 0..1. */
export function mech(x: number): number {
  const t = Math.min(1, Math.max(0, x));
  // Solve the bezier's x(t) for t by bisection, then return y(t).
  const bx = (u: number) => 3 * (1 - u) * (1 - u) * u * 0.6 + 3 * (1 - u) * u * u * 0.2 + u * u * u;
  const by = (u: number) => 3 * (1 - u) * u * u * 1 + u * u * u;
  let lo = 0;
  let hi = 1;
  for (let i = 0; i < 24; i++) {
    const mid = (lo + hi) / 2;
    if (bx(mid) < t) lo = mid;
    else hi = mid;
  }
  return by((lo + hi) / 2);
}

/** How shut the eye is, `ms` after a blink started (0 open … 1 shut … 0 open). */
export function blinkAmount(ms: number): number {
  if (ms < 0 || ms >= BLINK_MS) return 0;
  if (ms < BLINK_CLOSE_MS) return mech(ms / BLINK_CLOSE_MS);
  if (ms < BLINK_CLOSE_MS + BLINK_HOLD_MS) return 1;
  return 1 - mech((ms - BLINK_CLOSE_MS - BLINK_HOLD_MS) / BLINK_OPEN_MS);
}

/** Next blink in 6–10 s; `random` in 0..1. */
export function nextBlinkDelay(random: number): number {
  return 6000 + 4000 * random;
}

/** A pose with the eye shut by `amount` (0..1): both lids toward LID_SHUT. */
export function shutBy(pose: Pose, amount: number): Pose {
  if (amount <= 0) return pose;
  const k = Math.min(1, amount);
  return {
    ...pose,
    lidSide: pose.lidSide + (LID_SHUT - pose.lidSide) * k,
    lidMid: pose.lidMid + (LID_SHUT - pose.lidMid) * k,
    lowerLid: pose.lowerLid + (LID_SHUT - pose.lowerLid) * k,
  };
}

/** Eases a pose toward its target: about 220 ms to settle, whatever the frame rate. */
export function approach(current: Pose, target: Pose, dt: number): Pose {
  const a = 1 - Math.exp(-dt / 0.055);
  const out = { ...current };
  for (const key of Object.keys(target) as (keyof Pose)[]) out[key] = current[key] + (target[key] - current[key]) * a;
  return out;
}

export interface Spring {
  x: number;
  v: number;
}

/** One step of a damped spring toward `target` (stiffness 200, damping 26, mass 1: dry). */
export function springStep(s: Spring, target: number, dt: number, stiffness = 200, damping = 26): Spring {
  let { x, v } = s;
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

/** A short tremor (±1.5, three times, once) for `error`: 0 after 300 ms. */
export function shake(ms: number): number {
  if (ms < 0 || ms >= 300) return 0;
  return 1.5 * Math.sin((ms / 100) * Math.PI * 2);
}

/** `error`: the iris flickers three times fast, then stays lit. */
export function errorFlicker(ms: number): number {
  if (ms < 0 || ms >= 360) return 1;
  return Math.floor(ms / 60) % 2 === 0 ? 0.25 : 1;
}

/** The power LED: slow pulse at rest, fast blink thinking or failing, off offline, lit otherwise. */
export function ledOpacity(state: CiclopeState, seconds: number, still: boolean): number {
  if (state === "offline") return 0;
  if (still) return 1;
  if (state === "idle") return 0.675 + 0.325 * Math.cos((seconds / 2.4) * Math.PI * 2);
  if (state === "thinking" || state === "error") return Math.floor(seconds / 0.2) % 2 === 0 ? 1 : 0.25;
  return 1;
}

/** What the voice level does (listening: the core grows and glows; speaking: the ring follows
 * the voice and the grille lights up). */
export function withLevel(pose: Pose, state: CiclopeState, level: number): { pose: Pose; grille: number } {
  const l = Math.max(0, Math.min(1, level));
  if (state === "speaking") return { pose: { ...pose, ring: (10.5 + 1.5 * l) / 10.5 }, grille: l };
  if (state === "listening" || state === "interrupted") return { pose: { ...pose, core: (4.5 + 2 * l) / 4.5, glow: 0.7 + 0.3 * l }, grille: 0 };
  return { pose, grille: 0 };
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
