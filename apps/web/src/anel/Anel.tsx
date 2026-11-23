import { useEffect, useId, useRef, useState } from "react";

import { ART, EYE, MARKS, RING, litHour, markAngle } from "../muninn/genesis";
import { ANEL_LABELS, type AnelEstado } from "./state";
import "./anel.css";

interface AnelProps {
  estado: AnelEstado;
  /** px. Above 120 the ring holds Muninn; from 32 to 120 it is the ring alone; below 32 the dim
   * marks drop out and a thin circle carries the shape (DESIGN.md §5). */
  size?: number;
  /** Voice level 0..1 (the owner's or his own): the "ouvindo" wave follows it. A number, or a
   * getter read every frame. */
  level?: number | (() => number);
  /** false: the pose of the state, no loop (a row of avatars in the history). */
  animated?: boolean;
  /** Hidden from screen readers when the text beside it already says it. */
  decorative?: boolean;
  label?: string;
  className?: string;
}

// One clock for every ring on screen: the lit mark is the local hour (DESIGN.md §6, "ocioso").
const clockListeners = new Set<(d: Date) => void>();
let clockTimer: number | undefined;
function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    clockListeners.add(setNow);
    if (clockTimer === undefined) {
      clockTimer = window.setInterval(() => {
        const d = new Date();
        clockListeners.forEach((fn) => fn(d));
      }, 30_000);
    }
    return () => {
      clockListeners.delete(setNow);
      if (!clockListeners.size && clockTimer !== undefined) {
        window.clearInterval(clockTimer);
        clockTimer = undefined;
      }
    };
  }, []);
  return now;
}

/** Ring space (0..1000, centre 500) to this SVG's (-50..50). */
const u = (v: number) => (v - 500) / 10;
const R = { outer: RING.outer / 10, inner: RING.inner / 10, lit: RING.litInner / 10 };
/** The ring alone draws longer marks than around Muninn, so they still read at 36 px. */
const SMALL = { outer: 47, inner: 40, lit: 35 };
const GAP_HALF = Math.PI / MARKS / 1.4;

/** The brand's ring of traces (DESIGN.md §1, §5, §6): 24 hour marks with the empty gap at the top,
 * the local hour lit, and the amber dot that is the call to the model. The state (§6) shows as
 * motion: a wave while listening, a trace running round while thinking, the dot rising to the gap
 * when he speaks first, the gap lit while a yes is waiting, a hollow dot when paused, all dark in
 * silence. SVG and CSS, so a row of them costs no script; one frame loop only for a voice level. */
export function Anel({ estado, size = 36, level, animated = true, decorative = false, label, className }: AnelProps) {
  const id = useId().replace(/:/g, "");
  const root = useRef<SVGSVGElement>(null);
  const now = useNow();
  const muninn = size > 120;
  const tiny = size < 32;
  const geo = muninn ? R : SMALL;
  const lit = estado === "silencio" ? null : litHour(now);
  const voiced = estado === "ouvindo";

  // Voice level as a CSS variable: the dot (speaking) and the wave (listening) follow it.
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    if (!voiced || level === undefined) {
      el.style.removeProperty("--nivel");
      return;
    }
    if (typeof level === "number") {
      el.style.setProperty("--nivel", level.toFixed(3));
      return;
    }
    let raf = 0;
    const tick = () => {
      el.style.setProperty("--nivel", Math.max(0, Math.min(1, level())).toFixed(3));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [voiced, level]);

  const rest = muninn ? { x: u(EYE.x), y: u(EYE.y) } : { x: 0, y: 0 };
  const gapY = -(geo.outer + geo.inner) / 2;
  const dotR = muninn ? 1.1 : tiny ? 7 : 5.5;
  // Around Muninn the eye stays put; the dot that rises to the gap is a second light.
  const plate = { w: ART.scale * 100, y: (-ART.scale * 1000) / 20 + ART.offsetY / 10 };

  return (
    <svg
      ref={root}
      className={`anel${tiny ? " anel--mini" : ""}${muninn ? " anel--muninn" : ""}${className ? ` ${className}` : ""}`}
      data-estado={estado}
      data-animado={animated ? undefined : "nao"}
      viewBox="-50 -50 100 100"
      width={size}
      height={size}
      role={decorative ? undefined : "img"}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : label ?? `V.I.S.A.O., ${ANEL_LABELS[estado]}`}
      focusable="false"
      style={{ ["--ponto-x" as string]: `${rest.x}px`, ["--ponto-y" as string]: `${rest.y}px`, ["--falha-y" as string]: `${gapY}px` }}
    >
      {muninn && (
        <>
          <defs>
            <linearGradient id={`${id}-tinta`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="var(--papel)" />
              <stop offset="1" stopColor="var(--cinza)" />
            </linearGradient>
            <mask id={`${id}-traco`} maskUnits="userSpaceOnUse" x="-50" y="-50" width="100" height="100">
              <image href="/muninn/muninn-720.webp" x={-plate.w / 2} y={plate.y} width={plate.w} height={plate.w} />
            </mask>
          </defs>
          <rect className="anel-muninn" x="-50" y="-50" width="100" height="100" fill={`url(#${id}-tinta)`} mask={`url(#${id}-traco)`} />
        </>
      )}
      {tiny && (
        <path
          className="anel-contorno"
          d={`M ${Math.sin(GAP_HALF * 2) * 43} ${-Math.cos(GAP_HALF * 2) * 43} A 43 43 0 1 1 ${-Math.sin(GAP_HALF * 2) * 43} ${-Math.cos(GAP_HALF * 2) * 43}`}
          vectorEffect="non-scaling-stroke"
        />
      )}
      <g className="anel-marcas">
        {Array.from({ length: MARKS - 1 }, (_, i) => {
          const h = i + 1;
          const a = markAngle(h);
          const on = h === lit;
          const inner = on ? geo.lit : geo.inner;
          return (
            <line
              key={h}
              className={`anel-marca${on ? " anel-marca--hora" : ""}`}
              style={{ ["--h" as string]: h }}
              x1={Math.cos(a) * inner}
              y1={Math.sin(a) * inner}
              x2={Math.cos(a) * geo.outer}
              y2={Math.sin(a) * geo.outer}
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </g>
      <path
        className="anel-falha"
        d={`M ${-Math.sin(GAP_HALF) * -gapY} ${gapY * Math.cos(GAP_HALF)} A ${-gapY} ${-gapY} 0 0 1 ${Math.sin(GAP_HALF) * -gapY} ${gapY * Math.cos(GAP_HALF)}`}
        vectorEffect="non-scaling-stroke"
      />
      {muninn && <circle className="anel-olho" cx={u(EYE.x)} cy={u(EYE.y)} r={dotR} vectorEffect="non-scaling-stroke" />}
      <g className="anel-ponto">
        <circle className="anel-ponto-forma" r={dotR} vectorEffect="non-scaling-stroke" />
      </g>
    </svg>
  );
}
