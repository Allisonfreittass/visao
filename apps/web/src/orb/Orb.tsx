import { useEffect, useRef } from "react";

import {
  type OrbState,
  STATE_PARAMS,
  hash01,
  lerpParams,
  organicSphere,
  particleColor,
  particleRadius,
  reducedMotion,
  smoothingFactor,
} from "./orbModel";

const PARTICLES = 720;
const INNER_PARTICLES = 220;
const INNER_SCALE = 0.55;
const TILT = 0.35; // radians around X, so the poles don't face the viewer

interface OrbProps {
  state: OrbState;
  /** Current audio level 0..1 (microphone while LISTENING, playback while SPEAKING). */
  level?: number;
  size?: number;
}

export function Orb({ state, level = 0, size = 280 }: OrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // The animation loop reads these refs so prop changes never restart it.
  const stateRef = useRef(state);
  const levelRef = useRef(level);
  stateRef.current = state;
  levelRef.current = level;

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    // Outer shell plus a fainter inner shell for depth; sizes vary per particle.
    const points = [
      ...organicSphere(PARTICLES).map((p) => ({ p, shell: 1 })),
      ...organicSphere(INNER_PARTICLES, 0.3).map((p) => ({ p, shell: INNER_SCALE })),
    ];
    const sizes = points.map((_, i) => 0.6 + 0.8 * hash01(i + 9_000));
    let params = { ...STATE_PARAMS[stateRef.current] };
    let angle = 0;
    let last = performance.now();
    let frame = 0;
    const cosT = Math.cos(TILT);
    const sinT = Math.sin(TILT);

    const draw = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      const time = now / 1000;
      let target = STATE_PARAMS[stateRef.current];
      if (motionQuery.matches) target = reducedMotion(target);
      params = lerpParams(params, target, smoothingFactor(dt));
      angle += params.rotationSpeed * dt;

      const center = size / 2;
      const baseRadius = size * 0.33;
      ctx.clearRect(0, 0, size, size);

      const glow = ctx.createRadialGradient(center, center, 0, center, center, baseRadius * 1.5);
      glow.addColorStop(0, `hsla(28, ${100 * params.saturation}%, 55%, ${0.22 * params.brightness})`);
      glow.addColorStop(1, "hsla(28, 100%, 50%, 0)");
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, size, size);

      const cosA = Math.cos(angle);
      const sinA = Math.sin(angle);
      // Additive blending: overlapping particles brighten, like light rather than paint.
      ctx.globalCompositeOperation = "lighter";
      for (let i = 0; i < points.length; i++) {
        const { p, shell } = points[i];
        const [px, py, pz] = p;
        const r = particleRadius(params, i, time, levelRef.current) * shell;
        // Rotate around Y, then tilt around X.
        const x1 = px * cosA + pz * sinA;
        const z1 = -px * sinA + pz * cosA;
        const y2 = py * cosT - z1 * sinT;
        const z2 = py * sinT + z1 * cosT;
        const depth = (z2 + 1) / 2;
        const perspective = 0.75 + 0.25 * depth;
        const sx = center + x1 * r * baseRadius * perspective;
        const sy = center + y2 * r * baseRadius * perspective;
        ctx.fillStyle = particleColor(params, shell < 1 ? depth * 0.5 : depth);
        ctx.beginPath();
        ctx.arc(sx, sy, (0.5 + 1.2 * depth) * sizes[i] * shell, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalCompositeOperation = "source-over";
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [size]);

  return (
    <canvas
      ref={canvasRef}
      className="orb"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`Estado do sistema: ${STATE_LABELS[state]}`}
    />
  );
}

export const STATE_LABELS: Record<OrbState, string> = {
  IDLE: "ocioso",
  LISTENING: "ouvindo",
  THINKING: "pensando",
  SPEAKING: "falando",
  INTERRUPTED: "interrompido",
  DISCONNECTED: "desconectado",
};
