// Timeline and geometry of the genesis (DESIGN.md §5–§6), in the ring's own space: 0..1000,
// the same space brand/muninn/trace.py writes strokes.json in. Pure, so it can be tested.

export const T = {
  strokesStart: 0.4,
  strokesEnd: 6.4,
  strokeDur: 0.55,
  revealStart: 6.2,
  revealEnd: 8.4,
  eyeAt: 8.0,
  ringStart: 8.4,
  markGap: 0.05,
  markDur: 0.18,
  /** The whole genesis; after this the frame is still. */
  total: 14,
} as const;

export const MARKS = 24;
/** Where the illustration sits in the ring (§5): 76 % of it, centred, 1.4 % lower. */
export const ART = { scale: 0.76, offsetY: 14 } as const;
/** The eye, in ring space (§5: 51.6 %; 35.7 %). */
export const EYE = { x: 516, y: 357 } as const;
/** Where the first amber dot lights: the chest trace.py orders the strokes from. */
export const CHEST = { x: 500, y: 498 } as const;
export const RING = { inner: 448, outer: 486, litInner: 436 } as const;

/** The gap at the top flashes after the last mark closes. */
export const lastMarkAt = T.ringStart + (MARKS - 2) * T.markGap;
export const flash = { start: lastMarkAt + T.markDur, dur: 0.9 } as const;

export const clamp01 = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x);
export const easeOutCubic = (x: number) => 1 - (1 - clamp01(x)) ** 3;

/** When stroke `i` of `n` starts: in order, so the last one ends exactly at strokesEnd. */
export function strokeStart(i: number, n: number): number {
  if (n <= 1) return T.strokesStart;
  return T.strokesStart + (i * (T.strokesEnd - T.strokeDur - T.strokesStart)) / (n - 1);
}

/** How much of stroke `i` is drawn at time `t`, eased (0..1). */
export function strokeProgress(t: number, i: number, n: number): number {
  return easeOutCubic((t - strokeStart(i, n)) / T.strokeDur);
}

/** Angle of hour `h` on the ring; hour 0 is the top, where the gap (the name's place) is. */
export function markAngle(h: number): number {
  return (h / MARKS) * Math.PI * 2 - Math.PI / 2;
}

/** Marks 1..23 close clockwise from the gap; mark 0 never draws. Returns 0..1. */
export function markProgress(t: number, h: number): number {
  if (h <= 0 || h >= MARKS) return 0;
  return easeOutCubic((t - (T.ringStart + (h - 1) * T.markGap)) / T.markDur);
}

/** The illustration fades in over the strokes while they fade out. */
export function revealProgress(t: number): number {
  return easeOutCubic((t - T.revealStart) / (T.revealEnd - T.revealStart));
}

export function eyeProgress(t: number): number {
  return easeOutCubic((t - T.eyeAt) / 0.4);
}

/** The first amber dot: lights at 0 s, gives way to the eye as the illustration arrives. */
export function chestDot(t: number): number {
  return easeOutCubic(t / 0.3) * (1 - clamp01((t - T.revealStart) / 1.0));
}

/** Two amber pulses on the empty gap, then nothing: the name is not chosen yet. */
export function gapFlash(t: number): number {
  const x = (t - flash.start) / flash.dur;
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
