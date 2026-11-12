// Pure model of the particle orb: per-state parameters, smooth transitions, geometry.
// Rendering lives in Orb.tsx; everything here is deterministic and unit-tested.

export type OrbState =
  | "IDLE"
  | "LISTENING"
  | "THINKING"
  | "SPEAKING"
  | "INTERRUPTED"
  | "DISCONNECTED";

export interface OrbParams {
  /** Radians per second around the vertical axis. */
  rotationSpeed: number;
  /** Fraction of the radius the whole orb breathes by. */
  breathAmplitude: number;
  /** Breaths per second. */
  breathRate: number;
  /** Per-particle radial noise, fraction of the radius. */
  turbulence: number;
  /** How strongly the audio level (0..1) pushes particles outward. */
  levelGain: number;
  /** Overall size multiplier. */
  radiusScale: number;
  /** 1 = full orange, 0 = gray. */
  saturation: number;
  /** Lightness multiplier. */
  brightness: number;
}

export const STATE_PARAMS: Record<OrbState, OrbParams> = {
  IDLE: {
    rotationSpeed: 0.15,
    breathAmplitude: 0.03,
    breathRate: 0.25,
    turbulence: 0.01,
    levelGain: 0,
    radiusScale: 1,
    saturation: 1,
    brightness: 0.85,
  },
  LISTENING: {
    rotationSpeed: 0.25,
    breathAmplitude: 0.01,
    breathRate: 0.5,
    turbulence: 0.02,
    levelGain: 0.35,
    radiusScale: 1.05,
    saturation: 1,
    brightness: 1,
  },
  THINKING: {
    rotationSpeed: 1.1,
    breathAmplitude: 0.02,
    breathRate: 0.8,
    turbulence: 0.09,
    levelGain: 0,
    radiusScale: 0.95,
    saturation: 1,
    brightness: 0.95,
  },
  SPEAKING: {
    rotationSpeed: 0.35,
    breathAmplitude: 0.01,
    breathRate: 0.4,
    turbulence: 0.03,
    levelGain: 0.45,
    radiusScale: 1.05,
    saturation: 1,
    brightness: 1.1,
  },
  INTERRUPTED: {
    rotationSpeed: 0.05,
    breathAmplitude: 0,
    breathRate: 0,
    turbulence: 0.005,
    levelGain: 0,
    radiusScale: 0.78,
    saturation: 0.85,
    brightness: 0.8,
  },
  DISCONNECTED: {
    rotationSpeed: 0,
    breathAmplitude: 0,
    breathRate: 0,
    turbulence: 0,
    levelGain: 0,
    radiusScale: 0.9,
    saturation: 0,
    brightness: 0.55,
  },
};

const KEYS = Object.keys(STATE_PARAMS.IDLE) as Array<keyof OrbParams>;

/** Moves `current` toward `target` by fraction t (0..1); used every frame for smooth changes. */
export function lerpParams(current: OrbParams, target: OrbParams, t: number): OrbParams {
  const k = Math.min(Math.max(t, 0), 1);
  const out = { ...current };
  for (const key of KEYS) out[key] = current[key] + (target[key] - current[key]) * k;
  return out;
}

/** Frame-rate independent smoothing: same visual speed at 30 or 120 fps. */
export function smoothingFactor(dtSeconds: number, halfLifeSeconds = 0.18): number {
  return 1 - Math.pow(0.5, dtSeconds / halfLifeSeconds);
}

export type Point3 = [number, number, number];

/** Evenly spread points on a unit sphere (Fibonacci lattice). */
export function fibonacciSphere(count: number): Point3[] {
  const points: Point3[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y = count === 1 ? 0 : 1 - (i / (count - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = golden * i;
    points.push([Math.cos(theta) * r, y, Math.sin(theta) * r]);
  }
  return points;
}

/** Deterministic hash of an integer seed into [0, 1). */
export function hash01(seed: number): number {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
}

/** Fibonacci lattice nudged off its grid (still on the unit sphere), so it reads as an
 * organic cloud of data points rather than a regular pattern. */
export function organicSphere(count: number, jitter = 0.12): Point3[] {
  return fibonacciSphere(count).map(([x, y, z], i) => {
    const jx = x + (hash01(i * 3 + 1) - 0.5) * jitter;
    const jy = y + (hash01(i * 3 + 2) - 0.5) * jitter;
    const jz = z + (hash01(i * 3 + 3) - 0.5) * jitter;
    const n = Math.hypot(jx, jy, jz) || 1;
    return [jx / n, jy / n, jz / n];
  });
}

/** Cheap smooth pseudo-noise in [-1, 1], distinct per particle seed. */
export function wobble(seed: number, time: number): number {
  return Math.sin(seed * 12.9898 + time * 2.3) * Math.sin(seed * 78.233 + time * 1.7);
}

/** Radius multiplier of one particle at a given time and input/output audio level. */
export function particleRadius(params: OrbParams, seed: number, time: number, level: number): number {
  const breath = params.breathAmplitude * Math.sin(time * params.breathRate * Math.PI * 2);
  const noise = params.turbulence * wobble(seed, time);
  const audio = params.levelGain * Math.max(0, Math.min(level, 1)) * (0.6 + 0.4 * wobble(seed, time * 3));
  return params.radiusScale * (1 + breath + noise + audio);
}

/** Rastros `estanho` (cold tin, hue 184) fading to plain gray as saturation drops;
 * depth 0 (back) .. 1 (front). The only warmth is the lanterna core, drawn separately. */
export const ESTANHO_HUE = 184;
export const LANTERNA_HUE = 3;

export function particleColor(params: OrbParams, depth: number): string {
  const saturation = Math.round(14 * params.saturation);
  const lightness = Math.round(Math.min(86, (34 + 38 * depth) * params.brightness));
  const alpha = (0.22 + 0.7 * depth).toFixed(3);
  return `hsla(${ESTANHO_HUE}, ${saturation}%, ${lightness}%, ${alpha})`;
}

/** Strength 0..1 of the lanterna core: the one warm light, brighter while it talks or listens. */
export function coreIntensity(params: OrbParams, level: number): number {
  if (params.saturation === 0) return 0; // disconnected: the light is off
  const audio = Math.max(0, Math.min(level, 1));
  return Math.min(1, 0.35 * params.brightness + 0.55 * audio * params.levelGain * 2.5);
}

/** Slows everything down for users who asked the OS for reduced motion. */
export function reducedMotion(params: OrbParams): OrbParams {
  return {
    ...params,
    rotationSpeed: params.rotationSpeed * 0.2,
    breathAmplitude: params.breathAmplitude * 0.3,
    turbulence: params.turbulence * 0.3,
  };
}
