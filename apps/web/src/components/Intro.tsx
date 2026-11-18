import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { Ciclope } from "../ciclope/Ciclope";
import { Critter, type CritterKind } from "../ciclope/Family";
import { loadPreference, savePreference } from "../session";

/** How long the opening lasts, end to end. */
export const INTRO_MS = 2400;
const DAY_KEY = "intro-day";
const SESSION_KEY = "visao.intro-ran";
const EASE = "cubic-bezier(.2, .8, .2, 1)";

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

const SENSORS: CritterKind[] = ["mac", "email", "caderno", "whatsapp"];
const ORBIT = 96; // px from the mascot's center
const WORD = "V.I.S.A.O.";

/** The opening, a boot sequence (≈2.4 s): the dark grid with the mascot off and shut; its LED
 * blinks twice; the lid opens mechanically and the eye lights up with the room's red glow; the
 * sensors come online in orbit, one by one, as a thin red ring sweeps once; they fold into the
 * mascot, it slides left and the name is typed beside it, the last dot lit red; then the lockup
 * flies to the side bar's logo as Início fades in. A click or a key skips it. */
export function Intro({ onDone }: { onDone: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  const [awake, setAwake] = useState(false);

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

    // 2. The LED blinks twice.
    run(q(".intro-led"), [{ opacity: 0 }, { opacity: 1, offset: 0.2 }, { opacity: 0, offset: 0.45 }, { opacity: 1, offset: 0.7 }, { opacity: 0 }], { delay: 250, duration: 300, easing: "steps(1, end)" });
    // 3. The lid opens (the mascot leaves "offline") and the eye lights up with the glow.
    const wake = window.setTimeout(() => setAwake(true), 550);
    run(q(".intro-glow"), [{ opacity: 0 }, { opacity: 1.0, offset: 0.7 }, { opacity: 0.8 }], { delay: 550, duration: 350, easing: EASE });
    run(q(".intro-hero"), [{ transform: "scale(1)" }, { transform: "scale(1.04)", offset: 0.6 }, { transform: "scale(1)" }], { delay: 600, duration: 300, easing: EASE });

    // 4. The sensors come online in orbit, one every 120 ms; a red ring sweeps once.
    all<HTMLElement>(".intro-sensor").forEach((node, i) => {
      const angle = -Math.PI / 2 + (i / SENSORS.length) * Math.PI * 2;
      const x = Math.cos(angle) * ORBIT;
      const y = Math.sin(angle) * ORBIT;
      run(node, [
        { transform: `translate(${x}px, ${y}px) scale(.3)`, opacity: 0 },
        { transform: `translate(${x}px, ${y}px) scale(1.08)`, opacity: 1, offset: 0.7 },
        { transform: `translate(${x}px, ${y}px) scale(1)`, opacity: 1 },
      ], { delay: 900 + i * 120, duration: 240, easing: EASE });
      run(node.querySelector(".intro-sensor-on"), [{ opacity: 0 }, { opacity: 1 }], { delay: 1000 + i * 120, duration: 120, easing: "linear" });
      // 5. …and fold into the mascot.
      run(node, [
        { transform: `translate(${x}px, ${y}px) scale(1)`, opacity: 1 },
        { transform: "translate(0, 0) scale(.2)", opacity: 0 },
      ], { delay: 1500, duration: 220, easing: "cubic-bezier(.6, 0, .2, 1)", fill: "forwards" });
    });
    const ring = q<SVGCircleElement>(".intro-ring circle");
    if (ring) {
      const length = 2 * Math.PI * 76;
      ring.style.strokeDasharray = `${length * 0.18} ${length}`;
      run(q(".intro-ring"), [{ transform: "rotate(0deg)", opacity: 0 }, { opacity: 1, offset: 0.1 }, { opacity: 1, offset: 0.85 }, { transform: "rotate(360deg)", opacity: 0 }], { delay: 950, duration: 550, easing: "cubic-bezier(.4, 0, .2, 1)" });
    }

    // 5. The mascot slides left and the name is typed, 40 ms a letter; the last dot lights red.
    const lockup = q<HTMLElement>(".intro-lockup");
    const word = q<HTMLElement>(".intro-word");
    const shift = word ? (word.offsetWidth + 20) / 2 : 0;
    if (lockup) lockup.style.transform = `translateX(${shift}px)`;
    run(lockup, [{ transform: `translateX(${shift}px)` }, { transform: "translateX(0)" }], { delay: 1500, duration: 400, easing: EASE });
    all<HTMLElement>(".intro-word > span").forEach((letter, i) => {
      run(letter, [{ opacity: 0 }, { opacity: 1 }], { delay: 1520 + i * 40, duration: 1, easing: "linear" });
    });

    // 6. The lockup flies to the side bar's logo; the app shows through.
    const fly = window.setTimeout(() => {
      if (!lockup) return;
      const from = lockup.getBoundingClientRect();
      const target = Array.from(document.querySelectorAll<HTMLElement>("[data-lockup]")).find((n) => n.offsetParent !== null);
      const to = target?.getBoundingClientRect() ?? new DOMRect(24, 20, 140, 28);
      const scale = to.height / from.height;
      lockup.style.transformOrigin = "0 0";
      run(lockup, [{ transform: "translate(0, 0) scale(1)" }, { transform: `translate(${to.left - from.left}px, ${to.top - from.top}px) scale(${scale})` }], { duration: 420, easing: EASE, fill: "forwards" });
    }, 1920);
    run(el, [{ opacity: 1 }, { opacity: 0 }], { delay: 2020, duration: 380, easing: "ease-in", fill: "forwards" });
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
  }, [onDone]);

  // On <body>, so no app layout rule can pull it out of full screen.
  return createPortal(
    <div className="intro" ref={root} onClick={onDone} aria-hidden="true">
      <span className="intro-grid" />
      <span className="intro-glow" />
      <div className="intro-stage">
        <div className="intro-lockup">
          <div className="intro-hero">
            <svg className="intro-ring" viewBox="-80 -80 160 160" width="168" height="168">
              <circle r="76" fill="none" stroke="#FF3B30" strokeWidth="1.5" strokeLinecap="round" transform="rotate(-90)" />
            </svg>
            {SENSORS.map((kind) => (
              <span className="intro-sensor" key={kind}>
                <Critter kind={kind} size={36} asleep />
                <span className="intro-sensor-on"><Critter kind={kind} size={36} /></span>
              </span>
            ))}
            <Ciclope state={awake ? "idle" : "offline"} size={112} decorative />
            <span className="intro-led" />
          </div>
          <span className="intro-word">
            {WORD.split("").map((c, i) => (c === "." ? <span key={i}><b>.</b></span> : <span key={i}>{c}</span>))}
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
