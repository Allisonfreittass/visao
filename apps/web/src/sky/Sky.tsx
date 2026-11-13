import { useEffect, useRef } from "react";

import { createSkyRenderer, cssGradient, localHour, lookAt } from "./sky";

/** Clouds move slowly: a frame every 1/20 s is smooth enough and keeps the fan quiet. */
const FRAME_MS = 50;
/** Rendered smaller than the screen and stretched: the sky has no sharp edges to lose. */
const RESOLUTION = 0.5;
/** With reduced motion, the sky only follows the hour. */
const STILL_MS = 60_000;

/** The live sky behind the "Céu" appearance. Tells the page whether it is night (dark glass). */
export function Sky({ onNight }: { onNight?: (night: boolean) => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nightRef = useRef<boolean | null>(null);
  const onNightRef = useRef(onNight);
  onNightRef.current = onNight;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const renderer = createSkyRenderer(canvas);
    const started = performance.now();
    let frame = 0;
    let timer = 0;
    let last = 0;

    const tellNight = (night: number) => {
      const isNight = night > 0.5;
      if (nightRef.current !== isNight) {
        nightRef.current = isNight;
        onNightRef.current?.(isNight);
      }
    };

    const size = () => {
      const scale = Math.min(window.devicePixelRatio || 1, 2) * RESOLUTION;
      renderer?.resize(Math.max(1, Math.round(window.innerWidth * scale)), Math.max(1, Math.round(window.innerHeight * scale)));
    };

    const paint = (now: number) => {
      const look = lookAt(localHour());
      tellNight(look.night);
      canvas.style.background = cssGradient(look);
      renderer?.draw(look, (now - started) / 1000);
    };

    const loop = (now: number) => {
      frame = requestAnimationFrame(loop);
      if (document.hidden || now - last < FRAME_MS) return;
      last = now;
      paint(now);
    };

    size();
    paint(performance.now());
    if (renderer && !still) frame = requestAnimationFrame(loop);
    else timer = window.setInterval(() => paint(performance.now()), STILL_MS);

    const onResize = () => {
      size();
      paint(performance.now());
    };
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(frame);
      clearInterval(timer);
      window.removeEventListener("resize", onResize);
      renderer?.dispose();
    };
  }, []);

  return <canvas ref={canvasRef} className="sky" aria-hidden="true" />;
}
