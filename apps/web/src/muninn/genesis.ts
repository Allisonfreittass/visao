// Timeline and geometry of the genesis (DESIGN.md §5–§6), in the ring's own space: 0..1000,
// the same space brand/muninn/trace.py writes strokes.json in. Pure, so it can be tested.

export interface Timeline {
  /** The first amber dot at the chest: how fast it lights, and how long it takes to give way. */
  dotIn: number;
  dotOut: number;
  strokesStart: number;
  strokesEnd: number;
  strokeDur: number;
  revealStart: number;
  revealEnd: number;
  eyeAt: number;
  eyeDur: number;
  ringStart: number;
  markGap: number;
  markDur: number;
  flashDur: number;
  /** The whole genesis; after this the frame is still. */
  total: number;
}

/** The genesis of §6 (login, first open, when he "wakes"): 14 s. */
export const T: Timeline = {
  dotIn: 0.3,
  dotOut: 1.0,
  strokesStart: 0.4,
  strokesEnd: 6.4,
  strokeDur: 0.55,
  revealStart: 6.2,
  revealEnd: 8.4,
  eyeAt: 8.0,
  eyeDur: 0.4,
  ringStart: 8.4,
  markGap: 0.05,
  markDur: 0.18,
  flashDur: 0.9,
  total: 14,
};

/** The same story in 1.8 s, for the opening after login (components/Intro.tsx): the strokes grow
 * from the chest by 0.85 s, the eye lights at 1.0 s, the ring closes by 1.43 s and the gap
 * flashes once, before the name is typed at 1.5 s. */
export const T_CURTA: Timeline = {
  dotIn: 0.1,
  dotOut: 0.3,
  strokesStart: 0.05,
  strokesEnd: 0.85,
  strokeDur: 0.2,
  revealStart: 0.7,
  revealEnd: 1.1,
  eyeAt: 1.0,
  eyeDur: 0.15,
  ringStart: 1.05,
  markGap: 0.012,
  markDur: 0.12,
  flashDur: 0.35,
  total: 1.8,
};

export const MARKS = 24;
/** Where the illustration sits in the ring (§5): 76 % of it, centred, 1.4 % lower. */
export const ART = { scale: 0.76, offsetY: 14 } as const;
/** The eye, in ring space (§5: 51.6 %; 35.7 %). */
export const EYE = { x: 516, y: 357 } as const;
/** Where the first amber dot lights: the chest trace.py orders the strokes from. */
export const CHEST = { x: 500, y: 498 } as const;
export const RING = { inner: 448, outer: 486, litInner: 436 } as const;

/** The gap at the top flashes after the last mark closes. */
export const flashOf = (tl: Timeline) => ({ start: tl.ringStart + (MARKS - 2) * tl.markGap + tl.markDur, dur: tl.flashDur });
export const lastMarkAt = T.ringStart + (MARKS - 2) * T.markGap;
export const flash = flashOf(T);

export const clamp01 = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x);
export const easeOutCubic = (x: number) => 1 - (1 - clamp01(x)) ** 3;

/** When stroke `i` of `n` starts: in order, so the last one ends exactly at strokesEnd. */
export function strokeStart(i: number, n: number, tl: Timeline = T): number {
  if (n <= 1) return tl.strokesStart;
  return tl.strokesStart + (i * (tl.strokesEnd - tl.strokeDur - tl.strokesStart)) / (n - 1);
}

/** How much of stroke `i` is drawn at time `t`, eased (0..1). */
export function strokeProgress(t: number, i: number, n: number, tl: Timeline = T): number {
  return easeOutCubic((t - strokeStart(i, n, tl)) / tl.strokeDur);
}

/** Angle of hour `h` on the ring; hour 0 is the top, where the gap (the name's place) is. */
export function markAngle(h: number): number {
  return (h / MARKS) * Math.PI * 2 - Math.PI / 2;
}

/** Marks 1..23 close clockwise from the gap; mark 0 never draws. Returns 0..1. */
export function markProgress(t: number, h: number, tl: Timeline = T): number {
  if (h <= 0 || h >= MARKS) return 0;
  return easeOutCubic((t - (tl.ringStart + (h - 1) * tl.markGap)) / tl.markDur);
}

/** The illustration fades in over the strokes while they fade out. */
export function revealProgress(t: number, tl: Timeline = T): number {
  return easeOutCubic((t - tl.revealStart) / (tl.revealEnd - tl.revealStart));
}

export function eyeProgress(t: number, tl: Timeline = T): number {
  return easeOutCubic((t - tl.eyeAt) / tl.eyeDur);
}

/** The first amber dot: lights at 0 s, gives way to the eye as the illustration arrives. */
export function chestDot(t: number, tl: Timeline = T): number {
  return easeOutCubic(t / tl.dotIn) * (1 - clamp01((t - tl.revealStart) / tl.dotOut));
}

/** Two amber pulses on the empty gap, then nothing: the name is not chosen yet. */
export function gapFlash(t: number, tl: Timeline = T): number {
  const f = flashOf(tl);
  const x = (t - f.start) / f.dur;
  if (x <= 0 || x >= 1) return 0;
  return Math.sin(x * Math.PI * 2) ** 2;
}

/** The hour mark that stays lit at rest (§6, "ocioso"); none at midnight, which is the gap. */
export function litHour(date: Date): number | null {
  const h = date.getHours();
  return h === 0 ? null : h;
}

/** "Pensando": a trace runs round the ring. Brightness boost (0..1) of mark `h` at time `s`. */
export function thinkingBoost(h: number, s: number, lapSeconds = 1.6): number {
  const head = ((s / lapSeconds) % 1) * MARKS;
  const behind = (head - h + MARKS) % MARKS;
  return behind < 5 ? 1 - behind / 5 : 0;
}
