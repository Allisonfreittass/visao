import { useEffect, useRef } from "react";

import {
  ART,
  CHEST,
  EYE,
  MARKS,
  RING,
  T,
  chestDot,
  eyeProgress,
  gapFlash,
  litHour,
  markAngle,
  markProgress,
  revealProgress,
  strokeProgress,
  strokeStart,
  thinkingBoost,
} from "./genesis";

// Colours of DESIGN.md §2, read from the scoped tokens so the canvas follows the CSS.
interface Palette {
  tinta: string;
  papel: string;
  cinza: string;
  linha: string;
  ambar: string;
}

interface Spark {
  x: number;
  y: number;
  vx: number;
  vy: number;
  born: number;
  life: number;
  amber: boolean;
}

interface Stroke {
  pts: number[];
  /** Cumulative length at each point, for drawing a stroke part of the way. */
  len: number[];
  total: number;
}

const STROKES_URL = "/muninn/strokes.json";
/** The plate at the resolution the screen needs: 720 px up to that, 1024 px for retina desktops. */
const artUrl = (devicePixels: number) => (devicePixels > 720 ? "/muninn/muninn-1024.webp" : "/muninn/muninn-720.webp");
/** If the assets are slow, the ring still closes and the form never waits on them. */
const ASSET_WAIT_MS = 2500;

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

function prepare(raw: number[][]): Stroke[] {
  return raw.map((pts) => {
    const len = [0];
    for (let k = 2; k < pts.length; k += 2) len.push(len[len.length - 1] + Math.hypot(pts[k] - pts[k - 2], pts[k + 1] - pts[k - 1]));
    return { pts, len, total: len[len.length - 1] };
  });
}

function readPalette(el: Element): Palette {
  const s = getComputedStyle(el);
  const v = (name: string, fallback: string) => s.getPropertyValue(name).trim() || fallback;
  return {
    tinta: v("--tinta", "#101214"),
    papel: v("--papel", "#F3F1EC"),
    cinza: v("--cinza", "#9AA1A8"),
    linha: v("--linha", "#2C3136"),
    ambar: v("--ambar", "#F0A23B"),
  };
}

/** Muninn inside the ring of traces. Plays the genesis once on mount (the final frame alone with
 * reduced motion), then stays still; `thinking` runs a trace round the ring while it is true. */
export function Genesis({ thinking = false }: { thinking?: boolean }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const thinkingRef = useRef(thinking);
  const wakeRef = useRef<() => void>(() => {});

  thinkingRef.current = thinking;
  useEffect(() => wakeRef.current(), [thinking]);

  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!wrap || !canvas || !ctx) return;

    const still = reducedMotion();
    const palette = readPalette(wrap);
    let strokes: Stroke[] = [];
    let art: HTMLImageElement | null = null;
    let tinted: HTMLCanvasElement | null = null;
    let sparks: Spark[] = [];
    let fired = new Uint8Array(0);
    let started: number | null = null;
    let raf = 0;
    let alive = true;
    let size = 0;
    let dpr = 1;

    const start = () => {
      if (started !== null || !alive) return;
      started = performance.now();
      fired = new Uint8Array(strokes.length);
      wake();
    };

    // The illustration tinted papel → cinza from top to bottom: the one gradient DESIGN.md allows.
    const tint = () => {
      if (!art || !size) return;
      const px = Math.round(size * dpr * ART.scale);
      const off = document.createElement("canvas");
      off.width = off.height = px;
      const o = off.getContext("2d");
      if (!o) return;
      const g = o.createLinearGradient(0, 0, 0, px);
      g.addColorStop(0, palette.papel);
      g.addColorStop(1, palette.cinza);
      o.fillStyle = g;
      o.fillRect(0, 0, px, px);
      o.globalCompositeOperation = "multiply";
      o.drawImage(art, 0, 0, px, px);
      tinted = off;
    };

    const draw = (now: number) => {
      const t = started === null ? 0 : still ? T.total : (now - started) / 1000;
      const k = (size / 1000) * dpr;
      const W = size * dpr;
      ctx.globalCompositeOperation = "source-over";
      ctx.globalAlpha = 1;
      ctx.fillStyle = palette.tinta;
      ctx.fillRect(0, 0, W, W);
      if (started === null) return false;

      // 1. The first amber dot, at the chest.
      const dot = chestDot(t);
      if (dot > 0) {
        ctx.globalAlpha = dot;
        ctx.fillStyle = palette.ambar;
        ctx.beginPath();
        ctx.arc(CHEST.x * k, CHEST.y * k, 6 * k * (0.6 + 0.4 * dot), 0, Math.PI * 2);
        ctx.fill();
      }

      // 2. The strokes, in the order trace.py gave them, fading out as the illustration arrives.
      const reveal = tinted ? revealProgress(t) : 0;
      const strokeAlpha = 1 - reveal;
      if (strokes.length && strokeAlpha > 0.01 && t > T.strokesStart) {
        ctx.globalAlpha = 0.85 * strokeAlpha;
        ctx.strokeStyle = palette.papel;
        ctx.lineWidth = Math.max(0.7, size / 700) * dpr;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.beginPath();
        const n = strokes.length;
        for (let i = 0; i < n; i++) {
          if (t < strokeStart(i, n)) break; // in order: none after this has started
          const p = strokeProgress(t, i, n);
          const { pts, len, total } = strokes[i];
          const upTo = total * p;
          ctx.moveTo(pts[0] * k, pts[1] * k);
          let tipX = pts[0];
          let tipY = pts[1];
          for (let j = 1; j < len.length; j++) {
            if (len[j] <= upTo) {
              tipX = pts[j * 2];
              tipY = pts[j * 2 + 1];
              ctx.lineTo(tipX * k, tipY * k);
            } else {
              const f = (upTo - len[j - 1]) / (len[j] - len[j - 1] || 1);
              tipX = pts[j * 2 - 2] + (pts[j * 2] - pts[j * 2 - 2]) * f;
              tipY = pts[j * 2 - 1] + (pts[j * 2 + 1] - pts[j * 2 - 1]) * f;
              ctx.lineTo(tipX * k, tipY * k);
              break;
            }
          }
          // A finished stroke throws a spark from its tip 7 % of the time; 15 % of those amber.
          if (p >= 1 && !fired[i] && !still) {
            fired[i] = 1;
            if (Math.random() < 0.07) {
              const a = Math.random() * Math.PI * 2;
              const v = 20 + Math.random() * 50;
              sparks.push({ x: tipX, y: tipY, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 15, born: t, life: 0.5 + Math.random() * 0.6, amber: Math.random() < 0.15 });
            }
          }
        }
        ctx.stroke();
      }

      // Sparks drift and fade.
      if (sparks.length) {
        sparks = sparks.filter((s) => t - s.born < s.life);
        for (const s of sparks) {
          const age = (t - s.born) / s.life;
          ctx.globalAlpha = (1 - age) * 0.9;
          ctx.fillStyle = s.amber ? palette.ambar : palette.papel;
          ctx.beginPath();
          ctx.arc((s.x + s.vx * (t - s.born)) * k, (s.y + s.vy * (t - s.born)) * k, 1.6 * k * (1 - age * 0.5), 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // 3. The illustration, over the strokes; then the eye.
      if (tinted && reveal > 0) {
        const s = 1000 * ART.scale * k;
        const x = (1000 - 1000 * ART.scale) / 2 * k;
        const y = ((1000 - 1000 * ART.scale) / 2 + ART.offsetY) * k;
        ctx.globalAlpha = reveal;
        ctx.globalCompositeOperation = "screen";
        ctx.drawImage(tinted, x, y, s, s);
        ctx.globalCompositeOperation = "source-over";
      }
      const eye = tinted || strokes.length ? eyeProgress(t) : 0;
      if (eye > 0) {
        ctx.globalAlpha = eye;
        ctx.fillStyle = palette.ambar;
        ctx.beginPath();
        ctx.arc(EYE.x * k, EYE.y * k, 6.5 * k, 0, Math.PI * 2);
        ctx.fill();
      }

      // 4. The ring closes mark by mark from the gap; the gap flashes amber, then stays empty.
      const lit = litHour(new Date());
      const thinkingNow = thinkingRef.current;
      ctx.lineCap = "round";
      for (let h = 1; h < MARKS; h++) {
        const m = markProgress(t, h);
        if (m <= 0) continue;
        const boost = thinkingNow && !still ? thinkingBoost(h, now / 1000) : 0;
        const isLit = h === lit;
        const inner = isLit ? RING.litInner : RING.inner;
        const a = markAngle(h);
        const cos = Math.cos(a);
        const sin = Math.sin(a);
        const from = RING.outer - (RING.outer - inner) * m;
        // "Pensando" (§2, §6): one rastro runs the ring, an amber head with a papel tail.
        const head = boost > 0.8;
        ctx.globalAlpha = m * (isLit || head ? 1 : 0.5 + 0.5 * boost);
        ctx.strokeStyle = head ? palette.ambar : isLit || boost > 0.4 ? palette.papel : palette.cinza;
        ctx.lineWidth = (isLit ? 3 : 2.2) * k;
        ctx.beginPath();
        ctx.moveTo((500 + cos * RING.outer) * k, (500 + sin * RING.outer) * k);
        ctx.lineTo((500 + cos * from) * k, (500 + sin * from) * k);
        ctx.stroke();
      }
      const fl = still ? 0 : gapFlash(t);
      if (fl > 0) {
        const r = (RING.inner + RING.outer) / 2;
        ctx.globalAlpha = fl;
        ctx.strokeStyle = palette.ambar;
        ctx.lineWidth = 2.2 * k;
        ctx.beginPath();
        ctx.arc(500 * k, 500 * k, r * k, -Math.PI / 2 - Math.PI / 30, -Math.PI / 2 + Math.PI / 30);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;

      return t < T.total || sparks.length > 0 || (thinkingNow && !still);
    };

    const frame = (now: number) => {
      raf = 0;
      if (!alive) return;
      if (draw(now)) raf = requestAnimationFrame(frame);
    };

    function wake() {
      if (!raf && alive) raf = requestAnimationFrame(frame);
    }
    wakeRef.current = wake;

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

    // The lit hour changes on the hour: a still frame redraws once a minute to follow it.
    const minute = window.setInterval(wake, 60_000);

    const loadStrokes = fetch(STROKES_URL)
      .then((r) => (r.ok ? r.json() : []))
      .then((raw: number[][]) => {
        strokes = prepare(raw);
        fired = new Uint8Array(strokes.length);
      })
      .catch(() => {});
    const loadArt = new Promise<void>((resolve) => {
      const img = new Image();
      img.decoding = "async";
      img.onload = () => {
        art = img;
        tint();
        resolve();
      };
      img.onerror = () => resolve();
      img.src = artUrl(size * dpr * ART.scale);
    });
    void Promise.all([loadStrokes, loadArt]).then(start);
    const fallback = window.setTimeout(start, ASSET_WAIT_MS);

    return () => {
      alive = false;
      cancelAnimationFrame(raf);
      observer.disconnect();
      window.clearInterval(minute);
      window.clearTimeout(fallback);
      wakeRef.current = () => {};
    };
  }, []);

  return (
    <div ref={wrapRef} className="genesis" aria-hidden="true">
      <canvas ref={canvasRef} />
    </div>
  );
}
