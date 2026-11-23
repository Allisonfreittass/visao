import { useEffect, useId, useRef } from "react";

import {
  BLINK_MS,
  LID_HIDDEN,
  POSES,
  type Pose,
  SLIT,
  WANDER_MAX,
  approach,
  blinkAmount,
  errorFlicker,
  ledOpacity,
  lookOffset,
  nextBlinkDelay,
  shake,
  shutBy,
  springStep,
  withLevel,
} from "./model";
import { CICLOPE_LABELS, type CiclopeState } from "./state";

export type LookTarget = { x: number; y: number } | "pointer";

interface CiclopeProps {
  state: CiclopeState;
  /** px, 20 to 240. */
  size?: number;
  /** A point on screen (client px) the iris follows, or "pointer" for the cursor / last touch. */
  lookAt?: LookTarget;
  /** Voice level 0..1 (speaking, listening): a number, or a getter read every frame. */
  level?: number | (() => number);
  /** false: one still pose per state, no loop (many small avatars at once). */
  animated?: boolean;
  /** "Fresta": nearly shut on purpose (the login while the password is typed). */
  eyesClosed?: boolean;
  /** Hidden from screen readers when the text beside it already says it. */
  decorative?: boolean;
  label?: string;
  className?: string;
}

// One shared pointer, so a screen full of mascots adds one listener.
const pointer = { x: -1, y: -1, seen: false };
let pointerListeners = 0;
function onPointer(e: PointerEvent) {
  pointer.x = e.clientX;
  pointer.y = e.clientY;
  pointer.seen = true;
}
function watchPointer(): () => void {
  if (pointerListeners++ === 0) {
    window.addEventListener("pointermove", onPointer, { passive: true });
    window.addEventListener("pointerdown", onPointer, { passive: true });
  }
  return () => {
    if (--pointerListeners === 0) {
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("pointerdown", onPointer);
    }
  };
}

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

interface Parts {
  body: SVGGElement;
  led: SVGCircleElement;
  iris: SVGGElement;
  glow: SVGCircleElement;
  ring: SVGCircleElement;
  core: SVGCircleElement;
  lid: SVGPolygonElement;
  lidEdge: SVGPolylineElement;
  lower: SVGPolygonElement;
  lowerEdge: SVGPolylineElement;
  grilleLit: SVGPathElement | null;
  outer: SVGCircleElement;
}

interface Frame {
  pose: Pose;
  look: { x: number; y: number };
  grille: number;
  led: number;
  flicker: number;
  shakeX: number;
  spin: number;
  thinking: boolean;
}

/** Writes one frame to the SVG: transforms, opacity and SVG attributes only. */
function paint(p: Parts, f: Frame) {
  const { pose } = f;
  p.body.setAttribute("transform", `translate(${f.shakeX} 0)`);
  p.body.style.opacity = String(pose.body);
  p.led.style.opacity = String(f.led);
  p.iris.setAttribute("transform", `translate(${pose.irisX + f.look.x} ${pose.irisY + f.look.y})`);
  p.iris.style.opacity = String(pose.iris * f.flicker);
  p.glow.style.opacity = String(pose.glow);
  p.ring.setAttribute("transform", `rotate(${f.thinking ? (f.spin * 4) / 3 : 0} 50 47) translate(50 47) scale(${pose.ring}) translate(-50 -47)`);
  p.ring.setAttribute("stroke-dasharray", f.thinking ? "12 6" : "none");
  p.core.setAttribute("transform", `translate(50 47) scale(${pose.core}) translate(-50 -47)`);
  const s = pose.lidSide.toFixed(2);
  const m = pose.lidMid.toFixed(2);
  p.lid.setAttribute("points", `22,18 78,18 78,${s} 50,${m} 22,${s}`);
  p.lidEdge.setAttribute("points", `27,${s} 50,${m} 73,${s}`);
  const low = pose.lowerLid.toFixed(2);
  p.lower.setAttribute("points", `22,${low} 78,${low} 78,76 22,76`);
  p.lowerEdge.setAttribute("points", `27,${low} 73,${low}`);
  p.lowerEdge.style.opacity = pose.lowerLid < LID_HIDDEN - 6 ? "1" : "0";
  if (p.grilleLit) p.grilleLit.style.opacity = String(f.grille);
  p.outer.style.opacity = String(pose.outer);
  p.outer.setAttribute("transform", `rotate(${f.spin} 50 50)`);
}

function target(state: CiclopeState, slit: boolean): Pose {
  return slit ? { ...POSES[state], ...SLIT } : POSES[state];
}

/** The mascot, "Ciclope Sentinela": a graphite block with one red sensor eye under a metal lid.
 * It is the assistant's presence and shows its state with the eye (brand/README.md). */
export function Ciclope({ state, size = 96, lookAt, level, animated = true, eyesClosed = false, decorative, label, className }: CiclopeProps) {
  const uid = useId().replace(/:/g, "");
  const svgRef = useRef<SVGSVGElement>(null);
  const parts = useRef<Parts | null>(null);
  // The loop reads these refs, so prop changes never restart it.
  const live = useRef({ state, lookAt, level, eyesClosed, size });
  live.current = { state, lookAt, level, eyesClosed, size };

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const q = <T extends Element>(name: string) => svg.querySelector(`[data-part="${name}"]`) as T;
    parts.current = {
      body: q("body"), led: q("led"), iris: q("iris"), glow: q("glow"), ring: q("ring"), core: q("core"), lid: q("lid"),
      lidEdge: q("lid-edge"), lower: q("lower"), lowerEdge: q("lower-edge"), grilleLit: svg.querySelector<SVGPathElement>(`[data-part="grille-lit"]`), outer: q("outer"),
    };
  }, []);

  // Still mode: paint the pose of the state, once per change.
  useEffect(() => {
    if (animated || !parts.current) return;
    paint(parts.current, { pose: target(state, eyesClosed), look: { x: 0, y: 0 }, grille: 0, led: ledOpacity(state, 0, true), flicker: 1, shakeX: 0, spin: 0, thinking: false });
  }, [animated, state, eyesClosed]);

  useEffect(() => {
    if (!animated) return;
    const stopPointer = watchPointer();
    let pose: Pose = { ...target(live.current.state, live.current.eyesClosed) };
    let shownState = live.current.state;
    let stateSince = performance.now();
    let nextBlink = performance.now() + nextBlinkDelay(Math.random());
    let blinkAt = -Infinity;
    let wander = { x: 0, y: 0 };
    let nextWander = performance.now() + 4000 + Math.random() * 2000;
    let lookX = { x: 0, v: 0 };
    let lookY = { x: 0, v: 0 };
    let rect = svgRef.current?.getBoundingClientRect() ?? null;
    let rectAt = 0;
    let last = performance.now();
    let frame = 0;

    const tick = (now: number) => {
      const p = parts.current;
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      const { state: current, lookAt: aim, level: lv, eyesClosed: slit, size: px } = live.current;
      const still = reducedMotion();
      if (current !== shownState) {
        shownState = current;
        stateSince = now;
        if (current === "interrupted" && !still) blinkAt = now; // one mechanical blink
      }
      const since = now - stateSince;
      const levelNow = still ? 0 : typeof lv === "function" ? lv() : lv ?? 0;
      const voiced = withLevel(target(current, slit), current, levelNow);
      pose = still ? { ...voiced.pose } : approach(pose, voiced.pose, dt);

      // The mechanical blink, at rest only, never with reduced motion.
      if (!still && !slit && current === "idle" && now >= nextBlink) {
        blinkAt = now;
        nextBlink = now + BLINK_MS + nextBlinkDelay(Math.random());
      }
      const shown = still ? pose : shutBy(pose, blinkAmount(now - blinkAt));

      if (!still && current === "idle" && now >= nextWander) {
        wander = { x: (Math.random() * 2 - 1) * WANDER_MAX, y: (Math.random() * 2 - 1) * WANDER_MAX * 0.6 };
        nextWander = now + 4000 + Math.random() * 2000;
      }
      if (current !== "idle") wander = { x: 0, y: 0 };

      // Following a point: the cursor, a touch, or a given spot. Fixed at work and failing.
      let goal = wander;
      const follows = !still && aim && !slit && current !== "thinking" && current !== "offline" && current !== "working" && current !== "error";
      if (follows && svgRef.current) {
        if (now - rectAt > 500) {
          rect = svgRef.current.getBoundingClientRect();
          rectAt = now;
        }
        const point = aim === "pointer" ? (pointer.seen ? pointer : null) : aim;
        if (point && rect) {
          const cx = rect.left + rect.width * 0.5;
          const cy = rect.top + rect.height * 0.46;
          goal = lookOffset(point.x - cx, point.y - cy, Math.max(px, 120));
        }
      }
      lookX = still ? { x: 0, v: 0 } : springStep(lookX, goal.x, dt);
      lookY = still ? { x: 0, v: 0 } : springStep(lookY, goal.y, dt);

      const t = now / 1000;
      if (p) {
        paint(p, {
          pose: shown,
          look: { x: lookX.x, y: lookY.x },
          grille: voiced.grille,
          led: ledOpacity(current, t, still),
          flicker: !still && current === "error" ? errorFlicker(since) : 1,
          shakeX: !still && current === "error" ? shake(since) : 0,
          spin: still ? 0 : ((t / 1.6) * 360) % 360,
          thinking: !still && current === "thinking",
        });
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      stopPointer();
    };
  }, [animated]);

  const clip = `sentinela-clip-${uid}`;
  const glow = `sentinela-glow-${uid}`;
  const hl = `sentinela-hl-${uid}`;
  const name = label ?? `V.I.S.A.O., ${CICLOPE_LABELS[state]}`;
  // Tiny (sidebar, tab bar, avatars): no LED, no grille, no blur, so the eye stays legible.
  const tiny = size < 32;
  return (
    <svg
      ref={svgRef}
      className={`ciclope${className ? ` ${className}` : ""}`}
      viewBox="-8 -8 116 116"
      width={size}
      height={size}
      data-state={state}
      role={decorative ? undefined : "img"}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : name}
      focusable="false"
      style={{ overflow: "visible" }}
    >
      <defs>
        <clipPath id={clip}>
          <circle cx="50" cy="46" r="23" />
        </clipPath>
        <filter id={glow} x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="3.5" />
        </filter>
        <linearGradient id={hl} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity=".12" />
          <stop offset=".5" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* working: the outer ring turning, 1.6 s */}
      <circle data-part="outer" cx="50" cy="50" r="55" fill="none" stroke="#F0A23B" strokeWidth="5" strokeLinecap="round" strokeDasharray="110 248" style={{ opacity: 0 }} />
      <g data-part="body">
        <rect width="100" height="100" rx="30" fill="#2B2E34" />
        <rect width="100" height="100" rx="30" fill={`url(#${hl})`} />
        <rect x="1" y="1" width="98" height="98" rx="29" fill="none" stroke="#454952" strokeWidth="1.5" />
        {/* power LED */}
        <circle data-part="led" cx="83" cy="17" r="2.6" fill="#F0A23B" style={tiny ? { display: "none" } : undefined} />
        {/* the eye */}
        <circle cx="50" cy="46" r="23" fill="#050506" stroke="#3E424A" strokeWidth="2" />
        <g data-part="iris">
          <circle data-part="glow" cx="50" cy="47" r="13" fill="#F0A23B" style={{ opacity: 0.7 }} filter={tiny ? undefined : `url(#${glow})`} />
          <circle data-part="ring" cx="50" cy="47" r="10.5" fill="none" stroke="#F0A23B" strokeWidth="3" />
          <circle data-part="core" cx="50" cy="47" r="4.5" fill="#F0A23B" />
          <circle cx="50" cy="47" r="1.7" fill="#FFF1DC" />
        </g>
        {/* the lids (metal), cut by the eye */}
        <g clipPath={`url(#${clip})`}>
          <polygon data-part="lid" points="22,18 78,18 78,35 50,35 22,35" fill="#2B2E34" />
          <polyline data-part="lid-edge" points="27,35 50,35 73,35" fill="none" stroke="#5A5F69" strokeWidth="1.6" strokeLinejoin="round" />
          <polygon data-part="lower" points="22,76 78,76 78,76 22,76" fill="#2B2E34" />
          <polyline data-part="lower-edge" points="27,76 73,76" fill="none" stroke="#5A5F69" strokeWidth="1.6" style={{ opacity: 0 }} />
        </g>
        {/* speaker grille, where a mouth would be; it lights up with the voice */}
        {!tiny && (
          <>
            <path d="M41 79 H59 M44 84 H56" stroke="#15171A" strokeWidth="2.6" strokeLinecap="round" fill="none" />
            <path data-part="grille-lit" d="M41 79 H59 M44 84 H56" stroke="#F0A23B" strokeWidth="2.6" strokeLinecap="round" fill="none" style={{ opacity: 0 }} />
          </>
        )}
      </g>
    </svg>
  );
}
