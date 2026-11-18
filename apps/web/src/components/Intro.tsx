import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { Ciclope } from "../ciclope/Ciclope";
import { Critter, type CritterKind, FAMILY_COLORS } from "../ciclope/Family";
import { loadPreference, savePreference } from "../session";

/** How long the opening lasts, end to end. */
export const INTRO_MS = 2600;
const DAY_KEY = "intro-day";
const SESSION_KEY = "visao.intro-ran";
const EASE = "cubic-bezier(.2, .8, .2, 1)";
const SPRING = "cubic-bezier(.3, 1.45, .5, 1)";

/** "Bom dia" / "Boa tarde" / "Boa noite", by the hour on this device. */
export function greeting(hour: number): string {
  if (hour >= 5 && hour < 12) return "Bom dia";
  if (hour >= 12 && hour < 18) return "Boa tarde";
  return "Boa noite";
}

function localDay(now: Date): string {
  return `${now.getFullYear()}-${now.getMonth() + 1}-${now.getDate()}`;
}

function ranThisSession(): boolean {
  try {
    return sessionStorage.getItem(SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

function reducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

/** The opening plays on the first open of the day (once per tab session), and never for
 * someone who asked the system for less motion. */
export function shouldPlayIntro(now: Date, lastDay: string | null, reduced: boolean, ranInSession = false): boolean {
  return !reduced && !ranInSession && lastDay !== localDay(now);
}

export function introDue(now = new Date()): boolean {
  return shouldPlayIntro(now, loadPreference(DAY_KEY), reducedMotion(), ranThisSession());
}

/** Right after logging in it plays too, unless it already did in this tab. */
export function introAfterLogin(): boolean {
  return !reducedMotion() && !ranThisSession();
}

const FAMILY: CritterKind[] = ["mac", "whatsapp", "email", "caderno"];
// Where each one comes from (vw/vh from the center) and where it lands around the Ciclope (px).
const ENTRIES = [
  { from: [-60, -40], land: [-92, -58] },
  { from: [62, -36], land: [92, -58] },
  { from: [-58, 44], land: [-92, 58] },
  { from: [60, 42], land: [92, 58] },
];
const CONFETTI = [...Object.values(FAMILY_COLORS), "#FF6A1A"];

/** The opening (≈2.6 s): the Ciclope wakes up on a dark floor that turns light, its family
 * bounces in from the edges and joins it, a ring draws around it and pops confetti, the name
 * slides in beside it, and the lockup flies to its place on the side bar as Início fades in.
 * A click or a key skips it. */
export function Intro({ onDone }: { onDone: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  const [awake, setAwake] = useState(false);
  const confetti = useMemo(
    () => Array.from({ length: 16 }, (_, i) => {
      const angle = (i / 16) * Math.PI * 2 + Math.random() * 0.3;
      const reach = 110 + Math.random() * 70;
      return { x: Math.cos(angle) * reach, y: Math.sin(angle) * reach, color: CONFETTI[i % CONFETTI.length], size: 6 + Math.random() * 5 };
    }),
    [],
  );

  useEffect(() => {
    savePreference(DAY_KEY, localDay(new Date()));
    try {
      sessionStorage.setItem(SESSION_KEY, "1");
    } catch {
      // Without storage it may play again in this tab; harmless.
    }
    const el = root.current;
    if (!el) return;
    const q = <T extends Element>(s: string) => el.querySelector(s) as T;
    const all = <T extends Element>(s: string) => Array.from(el.querySelectorAll(s)) as T[];
    const anims: Animation[] = [];
    const run = (node: Element | null, frames: Keyframe[], options: KeyframeAnimationOptions) => {
      if (!node) return;
      anims.push(node.animate(frames, { fill: "both", ...options }));
    };

    // 1–2. Dark floor, the light one fades in; the Ciclope grows a little and opens its eye.
    run(q(".intro-light"), [{ opacity: 0 }, { opacity: 1 }], { delay: 300, duration: 400, easing: "ease-in-out" });
    run(q(".intro-hero"), [{ transform: "scale(.55)" }, { transform: "scale(1)" }], { delay: 300, duration: 450, easing: SPRING });
    const wake = window.setTimeout(() => setAwake(true), 320);

    // 3. The family comes in from the edges in arcs and bounces into place.
    all<HTMLElement>(".intro-critter").forEach((node, i) => {
      const { from, land } = ENTRIES[i];
      const fx = `${from[0]}vw`, fy = `${from[1]}vh`;
      run(node, [
        { transform: `translate(${fx}, ${fy}) scale(.6) rotate(${from[0] > 0 ? 40 : -40}deg)`, opacity: 0 },
        { transform: `translate(calc(${fx} * .45), calc(${fy} * .9)) scale(.9) rotate(0deg)`, opacity: 1, offset: 0.45 },
        { transform: `translate(${land[0]}px, ${land[1]}px) scale(1)`, opacity: 1 },
      ], { delay: 700 + i * 50, duration: 600 - i * 50, easing: SPRING });
      // 4. …and join the Ciclope.
      run(node, [
        { transform: `translate(${land[0]}px, ${land[1]}px) scale(1)`, opacity: 1 },
        { transform: "translate(0, 0) scale(.2)", opacity: 0 },
      ], { delay: 1300, duration: 260, easing: "cubic-bezier(.5, 0, .9, .4)", fill: "forwards" });
    });
    // 4. A thin orange ring draws itself around it, then confetti.
    const ring = q<SVGCircleElement>(".intro-ring circle");
    if (ring) {
      const length = 2 * Math.PI * 76;
      ring.style.strokeDasharray = `${length}`;
      run(ring, [{ strokeDashoffset: length }, { strokeDashoffset: 0 }], { delay: 1400, duration: 300, easing: EASE });
      run(q(".intro-ring"), [{ opacity: 1 }, { opacity: 1, offset: 0.6 }, { opacity: 0, transform: "scale(1.15)" }], { delay: 1400, duration: 600, easing: "ease-out" });
    }
    run(q(".intro-hero"), [{ transform: "scale(1)" }, { transform: "scale(1.08)" }, { transform: "scale(1)" }], { delay: 1560, duration: 260, easing: EASE, fill: "forwards" });
    all<HTMLElement>(".intro-confetti").forEach((node, i) => {
      const c = confetti[i];
      run(node, [
        { transform: "translate(0, 0) scale(.4)", opacity: 0 },
        { transform: `translate(${c.x * 0.7}px, ${c.y * 0.7}px) scale(1)`, opacity: 1, offset: 0.35 },
        { transform: `translate(${c.x}px, ${c.y + 30}px) scale(.8)`, opacity: 0 },
      ], { delay: 1560 + (i % 4) * 20, duration: 640, easing: "cubic-bezier(.1, .7, .3, 1)" });
    });

    // 5. The Ciclope slides left and the name comes in beside it.
    const lockup = q<HTMLElement>(".intro-lockup");
    const word = q<HTMLElement>(".intro-word");
    const shift = word ? (word.offsetWidth + 20) / 2 : 0;
    if (lockup) lockup.style.transform = `translateX(${shift}px)`;
    run(lockup, [{ transform: `translateX(${shift}px)` }, { transform: "translateX(0)" }], { delay: 1700, duration: 500, easing: EASE });
    run(word, [{ opacity: 0, transform: "translateX(-16px)" }, { opacity: 1, transform: "translateX(0)" }], { delay: 1780, duration: 420, easing: EASE });

    // 6. The lockup shrinks and flies to the side bar's logo; the app shows through.
    const fly = window.setTimeout(() => {
      if (!lockup) return;
      const from = lockup.getBoundingClientRect();
      const target = Array.from(document.querySelectorAll<HTMLElement>("[data-lockup]")).find((n) => n.offsetParent !== null);
      const to = target?.getBoundingClientRect() ?? new DOMRect(24, 20, 140, 28);
      const scale = to.height / from.height;
      const dx = to.left - from.left;
      const dy = to.top - from.top;
      lockup.style.transformOrigin = "0 0";
      run(lockup, [{ transform: "translate(0, 0) scale(1)" }, { transform: `translate(${dx}px, ${dy}px) scale(${scale})` }], { duration: 400, easing: EASE, fill: "forwards" });
    }, 2200);
    run(el, [{ opacity: 1 }, { opacity: 0 }], { delay: 2280, duration: 320, easing: "ease-in", fill: "forwards" });
    const done = window.setTimeout(onDone, INTRO_MS);

    const skip = () => onDone();
    window.addEventListener("keydown", skip);
    return () => {
      window.clearTimeout(wake);
      window.clearTimeout(fly);
      window.clearTimeout(done);
      window.removeEventListener("keydown", skip);
      anims.forEach((a) => a.cancel());
    };
  }, [onDone, confetti]);

  // On <body>, so no app layout rule can pull it out of full screen.
  return createPortal(
    <div className="intro" ref={root} onClick={onDone} aria-hidden="true">
      <div className="intro-light">
        <span className="ambient-blob ambient-blob--1" />
        <span className="ambient-blob ambient-blob--2" />
        <span className="ambient-blob ambient-blob--3" />
      </div>
      <div className="intro-stage">
        <div className="intro-lockup">
          <div className="intro-hero">
            <svg className="intro-ring" viewBox="-80 -80 160 160" width="168" height="168">
              <circle r="76" fill="none" stroke="#FF6A1A" strokeWidth="2.5" strokeLinecap="round" transform="rotate(-90)" />
            </svg>
            {FAMILY.map((kind) => (
              <span className="intro-critter" key={kind}><Critter kind={kind} size={44} /></span>
            ))}
            {confetti.map((c, i) => (
              <span className="intro-confetti" key={i} style={{ background: c.color, width: c.size, height: c.size }} />
            ))}
            <Ciclope state="idle" size={112} eyesClosed={!awake} decorative />
          </div>
          <span className="intro-word">V<b>.</b>I<b>.</b>S<b>.</b>A<b>.</b>O<b>.</b></span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
