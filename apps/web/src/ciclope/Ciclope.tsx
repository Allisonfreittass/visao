import { useEffect, useId, useRef } from "react";

import {
  BLINK_MS,
  POSES,
  type Pose,
  WANDER_MAX,
  approach,
  blinkAmount,
  breathe,
  lookOffset,
  nextBlinkDelay,
  shake,
  springStep,
  withLevel,
} from "./model";
import { CICLOPE_LABELS, type CiclopeState } from "./state";

export type LookTarget = { x: number; y: number } | "pointer";

interface CiclopeProps {
  state: CiclopeState;
  /** px, 24 to 240. */
  size?: number;
  /** A point on screen (client px) the pupil follows, or "pointer" for the cursor / last touch. */
  lookAt?: LookTarget;
  /** Voice level 0..1 (speaking, listening): a number, or a getter read every frame. */
  level?: number | (() => number);
  /** false: one still pose per state, no loop (many small avatars at once). */
  animated?: boolean;
  /** Closes the eye on purpose (the login while you type your password). */
  eyesClosed?: boolean;
  /** Hidden from screen readers when the text beside it already says it. */
  decorative?: boolean;
  label?: string;
  className?: string;
}

// One shared pointer, so a screen full of Ciclopes adds one listener.
const pointer = { x: -1, y: -1, seen: false };
let pointerListeners = 0;
function onPointer(e: PointerEvent) {
  pointer.x = e.clientX;
  pointer.y = e.clientY;
  pointer.seen = true;
}
function watchPointer(): () => void {
  if (pointerListeners++ === 0) window.addEventListener("pointermove", onPointer, { passive: true });
  if (pointerListeners === 1) window.addEventListener("pointerdown", onPointer, { passive: true });
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
  gray: SVGRectElement;
  eye: SVGGElement;
  iris: SVGGElement;
  pupil: SVGCircleElement;
  lid: SVGGElement;
  closed: SVGPathElement;
  eyeShadow: SVGCircleElement;
  smile: SVGPathElement;
  lidShade: SVGLinearGradientElement;
  mouth: SVGEllipseElement;
  ring: SVGGElement;
  ringSpin: SVGCircleElement;
}

interface Frame {
  pose: Pose;
  look: { x: number; y: number };
  blink: number;
  mouth: number;
  scale: number;
  rotate: number;
  shakeX: number;
  spin: number;
}

/** Writes one frame to the SVG: transforms and opacity only. */
function paint(p: Parts, f: Frame) {
  const { pose } = f;
  p.body.setAttribute("transform", `translate(${f.shakeX} 0) rotate(${f.rotate} 50 50) translate(50 50) scale(${f.scale}) translate(-50 -50)`);
  p.gray.style.opacity = String(pose.gray / 0.6);
  p.eye.setAttribute("transform", `translate(50 46) scale(${pose.sclera}) translate(-50 -46)`);
  const ix = pose.irisX + f.look.x;
  const iy = pose.irisY + f.look.y;
  p.iris.setAttribute("transform", `translate(${ix} ${iy}) translate(53 43) scale(${pose.iris}) translate(-53 -43)`);
  p.pupil.setAttribute("transform", `translate(53 43) scale(${pose.pupil}) translate(-53 -43)`);
  const lid = Math.max(pose.lid, f.blink);
  p.lid.setAttribute("transform", `rotate(${pose.lidTilt * (1 - lid)} 50 46) translate(0 ${lid * 54})`);
  // The lid's shading stays put while the lid moves, so it matches the body behind it.
  p.lidShade.setAttribute("gradientTransform", `translate(0 ${-lid * 54})`);
  p.smile.setAttribute("transform", `translate(0 79.5) scale(1 ${pose.smile}) translate(0 -79.5)`);
  p.closed.style.opacity = String(Math.max(0, (lid - 0.92) / 0.08));
  // Fully shut, the eye itself fades out so no rim of white shows around the lid.
  const eyeOpacity = 1 - Math.max(0, (lid - 0.86) / 0.14);
  p.eye.style.opacity = String(eyeOpacity);
  p.eye.style.visibility = eyeOpacity < 0.02 ? "hidden" : "visible";
  p.eyeShadow.style.opacity = String(0.2 * (1 - Math.max(0, (lid - 0.8) / 0.2)));
  p.mouth.setAttribute("transform", `translate(50 78) scale(1 ${Math.max(0.001, f.mouth)}) translate(-50 -78)`);
  p.mouth.style.opacity = f.mouth > 0.02 ? "1" : "0";
  p.ring.style.opacity = String(pose.ring);
  p.ringSpin.setAttribute("transform", `rotate(${f.spin} 50 50)`);
}

/** The Ciclope: the orange block with one big eye. It is the assistant's presence and shows
 * its state with the eye (docs/MARCA.md). */
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
      body: q("body"), gray: q("gray"), eye: q("eye"), iris: q("iris"), pupil: q("pupil"), lid: q("lid"),
      closed: q("closed"), eyeShadow: q("eye-shadow"), smile: q("smile"), lidShade: q("lid-shade"), mouth: q("mouth"), ring: q("ring"), ringSpin: q("ring-spin"),
    };
  }, []);

  // Still mode: paint the pose of the state, once per change.
  useEffect(() => {
    if (animated || !parts.current) return;
    const pose = eyesClosed ? { ...POSES[state], lid: 1 } : POSES[state];
    paint(parts.current, { pose, look: { x: 0, y: 0 }, blink: 0, mouth: 0, scale: 1, rotate: 0, shakeX: 0, spin: 0 });
  }, [animated, state, eyesClosed]);

  useEffect(() => {
    if (!animated) return;
    const stopPointer = watchPointer();
    let pose: Pose = { ...POSES[live.current.state] };
    let shownState = live.current.state;
    let stateSince = performance.now();
    let nextBlink = performance.now() + nextBlinkDelay(Math.random());
    let blinkAt = -Infinity;
    let wander = { x: 0, y: 0 };
    let nextWander = performance.now() + 4000;
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
      const { state: current, lookAt: target, level: lv, eyesClosed: closed, size: px } = live.current;
      const still = reducedMotion();
      if (current !== shownState) {
        shownState = current;
        stateSince = now;
        if (current === "interrupted" && !still) blinkAt = now; // a quick blink of surprise
      }
      const since = now - stateSince;

      let targetPose = POSES[current];
      if (closed) targetPose = { ...targetPose, lid: 1 };
      const levelNow = still ? 0 : typeof lv === "function" ? lv() : lv ?? 0;
      const voiced = withLevel(targetPose, current, levelNow);
      targetPose = voiced.pose;
      pose = still ? { ...targetPose } : approach(pose, targetPose, dt);

      // Blinking and looking around: only at rest-ish, never with reduced motion.
      const canBlink = !still && !closed && current !== "offline" && current !== "thinking";
      if (canBlink && now >= nextBlink) {
        blinkAt = now;
        nextBlink = now + BLINK_MS + nextBlinkDelay(Math.random());
      }
      const blink = still ? 0 : blinkAmount(now - blinkAt);
      if (!still && current === "idle" && now >= nextWander) {
        wander = { x: (Math.random() * 2 - 1) * WANDER_MAX, y: (Math.random() * 2 - 1) * WANDER_MAX * 0.7 };
        nextWander = now + 3200 + Math.random() * 1600;
      }
      if (current !== "idle") wander = { x: 0, y: 0 };

      // Following a point: the cursor, a touch, or a given spot.
      let goal = wander;
      const follows = !still && target && current !== "thinking" && current !== "offline" && !closed;
      if (follows && svgRef.current) {
        if (now - rectAt > 500) {
          rect = svgRef.current.getBoundingClientRect();
          rectAt = now;
        }
        const point = target === "pointer" ? (pointer.seen ? pointer : null) : target;
        if (point && rect) {
          const cx = rect.left + rect.width * 0.5;
          const cy = rect.top + rect.height * 0.46;
          goal = lookOffset(point.x - cx, point.y - cy, Math.max(px, 120));
        }
      }
      lookX = still ? { x: 0, v: 0 } : springStep(lookX, goal.x, dt);
      lookY = still ? { x: 0, v: 0 } : springStep(lookY, goal.y, dt);

      const t = now / 1000;
      const scale = !still && (current === "listening" || current === "interrupted") ? breathe(t) : 1;
      const rotate = !still && current === "thinking" ? 2 * Math.sin((t / 2.4) * Math.PI * 2) : 0;
      const shakeX = !still && current === "error" ? shake(since) : 0;
      const spin = still ? 0 : ((t / 1.6) * 360) % 360;
      if (p) paint(p, { pose, look: { x: lookX.x, y: lookY.x }, blink, mouth: voiced.mouth, scale, rotate, shakeX, spin });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      stopPointer();
    };
  }, [animated]);

  const shade = `ciclope-shade-${uid}`;
  const sclera = `ciclope-sclera-${uid}`;
  const clip = `ciclope-eye-${uid}`;
  const name = label ?? `V.I.S.A.O., ${CICLOPE_LABELS[state]}`;
  return (
    <svg
      ref={svgRef}
      className={`ciclope${className ? ` ${className}` : ""}`}
      viewBox="0 0 100 100"
      width={size}
      height={size}
      data-state={state}
      role={decorative ? undefined : "img"}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : name}
      focusable="false"
      overflow="visible"
      style={{ overflow: "visible" }}
    >
      <defs>
        <linearGradient id={shade} x1="0" y1="0" x2="0" y2="100" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#fff" stopOpacity=".32" />
          <stop offset=".45" stopColor="#fff" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity=".32" />
        </linearGradient>
        <radialGradient id={sclera} cx=".42" cy=".38" r=".65">
          <stop offset=".6" stopColor="#000" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity=".18" />
        </radialGradient>
        <linearGradient data-part="lid-shade" id={`${shade}-lid`} x1="0" y1="0" x2="0" y2="100" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#fff" stopOpacity=".32" />
          <stop offset=".45" stopColor="#fff" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity=".32" />
        </linearGradient>
        <clipPath id={clip}>
          <circle cx="50" cy="46" r="22" />
        </clipPath>
      </defs>
      {/* Working: a thin orange ring turning around the body. */}
      <g data-part="ring" style={{ opacity: 0 }}>
        <circle data-part="ring-spin" cx="50" cy="50" r="62" fill="none" stroke="#FF6A1A" strokeWidth="2.5" strokeLinecap="round" strokeDasharray="70 320" />
      </g>
      <g data-part="body">
        <rect width="100" height="100" rx="23" fill="#FF6A1A" />
        {/* offline: the body at 40% saturation, faded in over the orange */}
        <rect data-part="gray" width="100" height="100" rx="23" fill="#BA7E5E" style={{ opacity: 0 }} />
        <rect width="100" height="100" rx="23" fill={`url(#${shade})`} />
        {/* eye */}
        <circle data-part="eye-shadow" cx="50" cy="49" r="22" fill="#000" opacity=".2" />
        <g data-part="eye">
          <circle cx="50" cy="46" r="22" fill="#fff" />
          <circle cx="50" cy="46" r="22" fill={`url(#${sclera})`} />
          <g clipPath={`url(#${clip})`}>
            <g data-part="iris">
              <circle cx="53" cy="43" r="11.5" fill="#1B1E3A" />
              <circle cx="53" cy="43" r="10.5" fill="none" stroke="#3E4890" strokeWidth="2" />
              <circle data-part="pupil" cx="53" cy="43" r="5" fill="#05060C" />
              <circle cx="57" cy="39" r="3" fill="#fff" />
            </g>
            {/* eyelid: body-colored, it comes down over the eye to blink, squint and sleep */}
            <g data-part="lid">
              <path d="M20 -40 H80 V14 Q50 22 20 14 Z" fill="#FF6A1A" />
              <path d="M20 -40 H80 V14 Q50 22 20 14 Z" fill={`url(#${shade}-lid)`} />
              <path d="M24 14.6 Q50 22 76 14.6" fill="none" stroke="#000" strokeOpacity=".28" strokeWidth="2" />
            </g>
          </g>
        </g>
        {/* asleep: the closed eye is a curved line */}
        <path data-part="closed" d="M31 47 Q50 59 69 47" fill="none" stroke="#000" strokeOpacity=".5" strokeWidth="3" strokeLinecap="round" style={{ opacity: 0 }} />
        {/* mouth */}
        <path data-part="smile" d="M42 77 Q50 82 58 77" fill="none" stroke="#000" strokeOpacity=".45" strokeWidth="3.2" strokeLinecap="round" />
        <ellipse data-part="mouth" cx="50" cy="78" rx="6" ry="4" fill="#000" fillOpacity=".45" style={{ opacity: 0 }} />
        <rect x=".75" y=".75" width="98.5" height="98.5" rx="22.4" fill="none" stroke="#fff" strokeOpacity=".16" strokeWidth="1.5" />
      </g>
    </svg>
  );
}
