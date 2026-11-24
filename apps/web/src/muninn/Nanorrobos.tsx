import { useEffect, useRef } from "react";

import { ART, EYE, easeOutCubic } from "./genesis";
import { type Palette, STROKES_URL, artUrl, readPalette } from "./Genesis";
import {
  DESENHOS,
  FERRAMENTAS,
  type Forma,
  MAX_DELAY_S,
  MORPH_S,
  TREMOR_PX,
  ambar,
  amostrar,
  mulberry32,
  nuvem,
  particleCount,
  voo,
} from "./nanorrobos";
import "./nanorrobos.css";

/** Illustration in and out, and the eye, once the particles are in the crow (s). */
const PLATE_IN_S = 0.8;
const PLATE_OUT_S = 0.3;
const EYE_S = 0.3;

function rgb(hex: string, fallback: [number, number, number]): [number, number, number] {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return fallback;
  const v = parseInt(m[1], 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

/** The illustration as light only: its lines tinted papel → cinza from top to bottom (the one
 * gradient DESIGN.md allows), the black around them transparent, so it lies over the particles. */
function plate(art: HTMLImageElement, px: number, palette: Palette): HTMLCanvasElement | null {
  const off = document.createElement("canvas");
  off.width = off.height = px;
  const o = off.getContext("2d", { willReadFrequently: true });
  if (!o) return null;
  o.drawImage(art, 0, 0, px, px);
  let image: ImageData;
  try {
    image = o.getImageData(0, 0, px, px);
  } catch {
    return null;
  }
  const d = image.data;
  const top = rgb(palette.papel, [243, 241, 236]);
  const bottom = rgb(palette.cinza, [154, 161, 168]);
  for (let y = 0; y < px; y++) {
    const f = y / Math.max(1, px - 1);
    const r = top[0] + (bottom[0] - top[0]) * f;
    const g = top[1] + (bottom[1] - top[1]) * f;
    const b = top[2] + (bottom[2] - top[2]) * f;
    for (let x = 0; x < px; x++) {
      const i = (y * px + x) * 4;
      const light = Math.max(d[i], d[i + 1], d[i + 2]);
      d[i] = r;
      d[i + 1] = g;
      d[i + 2] = b;
      d[i + 3] = (light * d[i + 3]) / 255;
    }
  }
  o.putImageData(image, 0, 0);
  return off;
}

/** Strokes as polylines in ring space. */
const linesOf = (raw: number[][]) => raw.filter((pts) => pts.length >= 4);

interface NanorrobosProps {
  forma: Forma;
}

/** Muninn as particles, inside the call's ring (DESIGN.md §6, "Nanorrobôs"). Each change of
 * `forma` sends every particle to its point in the new shape; in the crow the illustration comes
 * back over them and the eye lights. One canvas, one requestAnimationFrame, still at rest. */
export function Nanorrobos({ forma }: NanorrobosProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const formaRef = useRef(forma);
  const changeRef = useRef<(f: Forma) => void>(() => {});

  useEffect(() => {
    formaRef.current = forma;
    changeRef.current(forma);
  }, [forma]);

  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!wrap || !canvas || !ctx) return;

    const palette = readPalette(wrap);
    const n = particleCount(window.innerWidth);
    const rand = mulberry32(24);
    const bend = new Float32Array(n);
    const phase = new Float32Array(n * 2);
    for (let i = 0; i < n; i++) {
      bend[i] = rand() * 2 - 1;
      phase[i * 2] = rand() * Math.PI * 2;
      phase[i * 2 + 1] = rand() * Math.PI * 2;
    }
    const amber = ambar(n, rand);
    const shapes = {} as Record<Forma, Float32Array>;
    FERRAMENTAS.forEach((f, k) => (shapes[f] = amostrar(DESENHOS[f], n, mulberry32(100 + k))));
    shapes.corvo = nuvem(n, rand);

    // Each particle flies from `from` to `to`, leaving `delay` s after `start`.
    const from = shapes.corvo.slice();
    const to = shapes.corvo.slice();
    const delay = new Float32Array(n);
    let start = -Infinity;
    let maxDelay = 0;
    let current: Forma = "corvo";
    let art: HTMLImageElement | null = null;
    let lit: HTMLCanvasElement | null = null;
    // Without the illustration the crow at rest is the particles themselves.
    let artFailed = false;
    // The crow at rest: the illustration over the particles and the eye lit.
    let plateShown = 1;
    let eyeShown = 1;
    let last = performance.now();
    let raf = 0;
    let alive = true;
    let size = 0;
    let dpr = 1;

    const settled = (now: number) => now >= start + (MORPH_S + maxDelay) * 1000;

    const where = (i: number, now: number): [number, number] => {
      const u = ((now - start) / 1000 - delay[i]) / MORPH_S;
      if (u >= 1) return [to[i * 2], to[i * 2 + 1]];
      if (u <= 0) return [from[i * 2], from[i * 2 + 1]];
      return voo(from[i * 2], from[i * 2 + 1], to[i * 2], to[i * 2 + 1], u, bend[i]);
    };

    const change = (next: Forma) => {
      if (next === current || !alive) return;
      const now = performance.now();
      for (let i = 0; i < n; i++) {
        const [x, y] = where(i, now);
        from[i * 2] = x;
        from[i * 2 + 1] = y;
      }
      to.set(shapes[next]);
      maxDelay = 0;
      for (let i = 0; i < n; i++) {
        delay[i] = Math.random() * MAX_DELAY_S;
        if (delay[i] > maxDelay) maxDelay = delay[i];
      }
      start = now;
      current = next;
      wake();
    };
    changeRef.current = change;

    const draw = (now: number) => {
      // Fades follow the clock, not the frame count: a slow phone gets them on time. The loop
      // restarts with `last` reset, so a pause never counts.
      const dt = Math.min(1, (now - last) / 1000);
      last = now;
      const crowDone = current === "corvo" && settled(now);
      const plateTarget = crowDone && !artFailed ? 1 : 0;
      plateShown = plateTarget > plateShown ? Math.min(1, plateShown + dt / PLATE_IN_S) : Math.max(0, plateShown - dt / PLATE_OUT_S);
      const eyeTarget = plateTarget && plateShown > 0.6 ? 1 : 0;
      eyeShown = eyeTarget > eyeShown ? Math.min(1, eyeShown + dt / EYE_S) : Math.max(0, eyeShown - dt / PLATE_OUT_S);

      const W = size * dpr;
      const k = W / 1000;
      ctx.clearRect(0, 0, W, W);

      // The particles fade as the illustration arrives over them, as in the genesis.
      const reveal = easeOutCubic(plateShown);
      const particles = 1 - reveal;
      if (particles > 0.01) {
        const tremor = (TREMOR_PX * dpr) / k; // ring units
        const s = Math.max(1, (size / 200) * dpr) * 0.9;
        const half = s / 2;
        const t = now / 1000;
        const paths = [new Path2D(), new Path2D()];
        for (let i = 0; i < n; i++) {
          let [x, y] = where(i, now);
          if (((now - start) / 1000 - delay[i]) / MORPH_S >= 1) {
            x += Math.sin(t * 7 + phase[i * 2]) * tremor;
            y += Math.cos(t * 6 + phase[i * 2 + 1]) * tremor;
          }
          paths[amber[i]].rect(x * k - half, y * k - half, s, s);
        }
        ctx.globalAlpha = 0.9 * particles;
        ctx.fillStyle = palette.papel;
        ctx.fill(paths[0]);
        ctx.globalAlpha = particles;
        ctx.fillStyle = palette.ambar;
        ctx.fill(paths[1]);
      }

      // Until the illustration loads it is not drawn, and the particles wait hidden under it.
      if (lit && reveal > 0) {
        const side = 1000 * ART.scale * k;
        ctx.globalAlpha = reveal;
        ctx.drawImage(lit, ((1000 - 1000 * ART.scale) / 2) * k, ((1000 - 1000 * ART.scale) / 2 + ART.offsetY) * k, side, side);
      }
      if (eyeShown > 0) {
        ctx.globalAlpha = easeOutCubic(eyeShown);
        ctx.fillStyle = palette.ambar;
        ctx.beginPath();
        ctx.arc(EYE.x * k, EYE.y * k, 11 * k, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      // At rest in the crow nothing moves; in a tool's shape the particles tremble.
      return particles > 0.01 || plateShown !== plateTarget || eyeShown !== eyeTarget;
    };

    const frame = (now: number) => {
      raf = 0;
      if (!alive) return;
      if (draw(now)) raf = requestAnimationFrame(frame);
    };
    function wake() {
      if (!raf && alive) {
        last = performance.now();
        raf = requestAnimationFrame(frame);
      }
    }

    const tint = () => {
      if (art && size) lit = plate(art, Math.round(size * dpr * ART.scale), palette);
    };
    const resize = () => {
      const next = Math.round(wrap.clientWidth);
      const nextDpr = Math.min(window.devicePixelRatio || 1, 2);
      if (next === size && nextDpr === dpr) return;
      size = next;
      dpr = nextDpr;
      canvas.width = canvas.height = Math.max(1, Math.round(size * dpr));
      tint();
      wake();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(wrap);
    resize();

    fetch(STROKES_URL)
      .then((r) => (r.ok ? r.json() : []))
      .then((raw: number[][]) => {
        if (!alive || !Array.isArray(raw) || !raw.length) return;
        shapes.corvo = amostrar(linesOf(raw), n, mulberry32(7), 1.5);
        if (current !== "corvo") return;
        if (settled(performance.now())) from.set(shapes.corvo);
        to.set(shapes.corvo);
        wake();
      })
      .catch(() => {});
    const img = new Image();
    img.decoding = "async";
    img.onload = () => {
      art = img;
      tint();
      wake();
    };
    img.onerror = () => {
      artFailed = true;
      wake();
    };
    img.src = artUrl(size * dpr * ART.scale);

    // The shape may have changed before the canvas was ready.
    change(formaRef.current);
    wake();

    return () => {
      alive = false;
      cancelAnimationFrame(raf);
      observer.disconnect();
      changeRef.current = () => {};
    };
  }, []);

  return (
    <div ref={wrapRef} className="nano-canvas" aria-hidden="true">
      <canvas ref={canvasRef} />
    </div>
  );
}
